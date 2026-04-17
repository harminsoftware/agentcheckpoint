"""Serialization engine with strategy pattern — Pickle, JSON, and compressed variants."""

from __future__ import annotations

import io
import json
import pickle
from abc import ABC, abstractmethod
from typing import Any


class SerializationError(Exception):
    """Raised when serialization or deserialization fails."""


class Serializer(ABC):
    """Abstract base for all serializers."""

    @abstractmethod
    def serialize(self, obj: Any) -> bytes:
        """Serialize an object to bytes."""

    @abstractmethod
    def deserialize(self, data: bytes) -> Any:
        """Deserialize bytes back to an object."""

    @property
    @abstractmethod
    def format_id(self) -> str:
        """Short identifier for this format (stored in checkpoint metadata)."""


class PickleSerializer(Serializer):
    """Fast serializer using Python's pickle. Handles arbitrary objects.

    WARNING: pickle can execute arbitrary code during deserialization.
    Only deserialize data you trust.
    """

    PROTOCOL = pickle.HIGHEST_PROTOCOL

    def serialize(self, obj: Any) -> bytes:
        try:
            return pickle.dumps(obj, protocol=self.PROTOCOL)
        except Exception as e:
            raise SerializationError(f"Pickle serialization failed: {e}") from e

    def deserialize(self, data: bytes) -> Any:
        try:
            return pickle.loads(data)  # noqa: S301
        except Exception as e:
            raise SerializationError(f"Pickle deserialization failed: {e}") from e

    @property
    def format_id(self) -> str:
        return "pickle"


class JSONSerializer(Serializer):
    """Safe, human-readable serializer. Requires JSON-serializable objects."""

    def serialize(self, obj: Any) -> bytes:
        try:
            return json.dumps(obj, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
        except Exception as e:
            raise SerializationError(f"JSON serialization failed: {e}") from e

    def deserialize(self, data: bytes) -> Any:
        try:
            return json.loads(data.decode("utf-8"))
        except Exception as e:
            raise SerializationError(f"JSON deserialization failed: {e}") from e

    @property
    def format_id(self) -> str:
        return "json"


class CompressedSerializer(Serializer):
    """Wraps any serializer with zstd compression for large states.

    Falls back to zlib if zstandard is not installed.
    """

    def __init__(self, inner: Serializer | None = None):
        self._inner = inner or PickleSerializer()
        self._compressor = self._get_compressor()

    def _get_compressor(self) -> str:
        try:
            import zstandard  # noqa: F401

            return "zstd"
        except ImportError:
            return "zlib"

    def _compress(self, data: bytes) -> bytes:
        if self._compressor == "zstd":
            import zstandard

            cctx = zstandard.ZstdCompressor(level=3)
            return cctx.compress(data)
        else:
            import zlib

            return zlib.compress(data, level=6)

    def _decompress(self, data: bytes) -> bytes:
        if self._compressor == "zstd":
            import zstandard

            dctx = zstandard.ZstdDecompressor()
            return dctx.decompress(data)
        else:
            import zlib

            return zlib.decompress(data)

    def serialize(self, obj: Any) -> bytes:
        try:
            raw = self._inner.serialize(obj)
            return self._compress(raw)
        except SerializationError:
            raise
        except Exception as e:
            raise SerializationError(f"Compressed serialization failed: {e}") from e

    def deserialize(self, data: bytes) -> Any:
        try:
            raw = self._decompress(data)
            return self._inner.deserialize(raw)
        except SerializationError:
            raise
        except Exception as e:
            raise SerializationError(f"Compressed deserialization failed: {e}") from e

    @property
    def format_id(self) -> str:
        return f"{self._compressor}+{self._inner.format_id}"


class AutoSerializer(Serializer):
    """Tries JSON first, falls back to Pickle. Best of both worlds."""

    def __init__(self):
        self._json = JSONSerializer()
        self._pickle = PickleSerializer()

    def serialize(self, obj: Any) -> bytes:
        # Try JSON first (safer, human-readable)
        try:
            data = self._json.serialize(obj)
            # Prefix with format marker
            return b"J" + data
        except SerializationError:
            pass
        # Fall back to pickle
        data = self._pickle.serialize(obj)
        return b"P" + data

    def deserialize(self, data: bytes) -> Any:
        if not data:
            raise SerializationError("Cannot deserialize empty data")
        marker = data[0:1]
        payload = data[1:]
        if marker == b"J":
            return self._json.deserialize(payload)
        elif marker == b"P":
            return self._pickle.deserialize(payload)
        else:
            # Legacy format — try pickle
            return self._pickle.deserialize(data)

    @property
    def format_id(self) -> str:
        return "auto"


def get_serializer(format: str = "auto") -> Serializer:
    """Factory function to get a serializer by format name."""
    serializers = {
        "auto": AutoSerializer,
        "json": JSONSerializer,
        "pickle": PickleSerializer,
        "compressed": CompressedSerializer,
        "zstd": lambda: CompressedSerializer(PickleSerializer()),
        "zstd+json": lambda: CompressedSerializer(JSONSerializer()),
    }
    factory = serializers.get(format)
    if factory is None:
        raise ValueError(f"Unknown serializer format: {format!r}. Choose from: {list(serializers)}")
    return factory()
