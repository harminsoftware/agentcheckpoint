"""Tests for serializers."""

import pytest

from agentcheckpoint.serializer import (
    AutoSerializer,
    CompressedSerializer,
    JSONSerializer,
    PickleSerializer,
    SerializationError,
    get_serializer,
)


class TestPickleSerializer:
    def test_round_trip_dict(self):
        s = PickleSerializer()
        data = {"key": "value", "nested": {"a": 1}}
        result = s.deserialize(s.serialize(data))
        assert result == data

    def test_round_trip_complex(self):
        s = PickleSerializer()
        data = {"set": {1, 2, 3}, "bytes": b"hello", "tuple": (1, 2)}
        result = s.deserialize(s.serialize(data))
        assert result == data

    def test_format_id(self):
        assert PickleSerializer().format_id == "pickle"


class TestJSONSerializer:
    def test_round_trip_dict(self):
        s = JSONSerializer()
        data = {"key": "value", "number": 42, "list": [1, 2, 3]}
        result = s.deserialize(s.serialize(data))
        assert result == data

    def test_non_serializable_uses_default_str(self):
        s = JSONSerializer()
        # Sets get converted to strings via default=str
        data = s.serialize({"set": {1, 2, 3}})
        result = s.deserialize(data)
        assert "set" in result
        assert isinstance(result["set"], str)  # Set becomes its string repr

    def test_format_id(self):
        assert JSONSerializer().format_id == "json"


class TestCompressedSerializer:
    def test_round_trip(self):
        s = CompressedSerializer(PickleSerializer())
        data = {"key": "value" * 100}  # Repetitive data compresses well
        result = s.deserialize(s.serialize(data))
        assert result == data

    def test_compression_reduces_size(self):
        inner = PickleSerializer()
        s = CompressedSerializer(inner)
        data = {"key": "value" * 1000}
        raw = inner.serialize(data)
        compressed = s.serialize(data)
        assert len(compressed) < len(raw)

    def test_format_id(self):
        s = CompressedSerializer(JSONSerializer())
        assert "json" in s.format_id


class TestAutoSerializer:
    def test_json_serializable_uses_json(self):
        s = AutoSerializer()
        data = {"key": "value"}
        serialized = s.serialize(data)
        assert serialized[0:1] == b"J"  # JSON marker

    def test_non_json_uses_default_str(self):
        s = AutoSerializer()
        data = {"set": {1, 2, 3}}
        serialized = s.serialize(data)
        # JSON serializer handles sets via default=str, so it stays JSON
        assert serialized[0:1] == b"J"

    def test_round_trip_json(self):
        s = AutoSerializer()
        data = {"key": "value"}
        assert s.deserialize(s.serialize(data)) == data

    def test_round_trip_set_as_string(self):
        s = AutoSerializer()
        data = {"set": {1, 2, 3}}
        result = s.deserialize(s.serialize(data))
        # Sets are converted to string repr via JSON default=str
        assert isinstance(result["set"], str)

    def test_empty_data_raises(self):
        s = AutoSerializer()
        with pytest.raises(SerializationError):
            s.deserialize(b"")


class TestGetSerializer:
    def test_auto(self):
        assert isinstance(get_serializer("auto"), AutoSerializer)

    def test_json(self):
        assert isinstance(get_serializer("json"), JSONSerializer)

    def test_pickle(self):
        assert isinstance(get_serializer("pickle"), PickleSerializer)

    def test_compressed(self):
        assert isinstance(get_serializer("compressed"), CompressedSerializer)

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown serializer"):
            get_serializer("unknown")
