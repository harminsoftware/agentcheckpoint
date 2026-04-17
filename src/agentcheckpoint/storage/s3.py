"""S3-compatible storage adapter (AWS S3, Cloudflare R2, MinIO).

Uses boto3 with support for custom endpoints. Writes use a temp-key
pattern for atomic commits.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Optional

from agentcheckpoint.state import RunInfo, StepInfo
from agentcheckpoint.storage import StorageBackend


class S3StorageBackend(StorageBackend):
    """S3-compatible storage backend. Works with AWS S3, Cloudflare R2, MinIO.

    Requires: pip install agentcheckpoint[s3]
    """

    def __init__(
        self,
        bucket: str,
        prefix: str = "checkpoints",
        endpoint_url: str | None = None,
        region_name: str | None = None,
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
    ):
        try:
            import boto3
        except ImportError:
            raise ImportError(
                "boto3 is required for S3 storage. "
                "Install with: pip install agentcheckpoint[s3]"
            )

        self.bucket = bucket
        self.prefix = prefix.strip("/")

        session_kwargs = {}
        if region_name:
            session_kwargs["region_name"] = region_name
        if aws_access_key_id:
            session_kwargs["aws_access_key_id"] = aws_access_key_id
        if aws_secret_access_key:
            session_kwargs["aws_secret_access_key"] = aws_secret_access_key

        client_kwargs = {}
        if endpoint_url:
            client_kwargs["endpoint_url"] = endpoint_url

        session = boto3.Session(**session_kwargs)
        self._s3 = session.client("s3", **client_kwargs)

    def _key(self, run_id: str, step: int) -> str:
        return f"{self.prefix}/{run_id}/step_{step:06d}.ckpt"

    def _tmp_key(self, run_id: str, step: int) -> str:
        return f"{self.prefix}/{run_id}/.tmp_step_{step:06d}.ckpt"

    def _meta_key(self, run_id: str) -> str:
        return f"{self.prefix}/{run_id}/run_meta.json"

    def save(self, run_id: str, step: int, data: bytes, metadata: dict | None = None) -> None:
        """Two-phase commit: write to temp key, then copy to final key."""
        tmp_key = self._tmp_key(run_id, step)
        final_key = self._key(run_id, step)

        extra_args = {}
        if metadata:
            import json
            extra_args["Metadata"] = {k: str(v) for k, v in metadata.items()}

        # Phase 1: Write to temp key
        self._s3.put_object(Bucket=self.bucket, Key=tmp_key, Body=data, **extra_args)

        # Phase 2: Copy to final key
        self._s3.copy_object(
            Bucket=self.bucket,
            Key=final_key,
            CopySource={"Bucket": self.bucket, "Key": tmp_key},
        )

        # Cleanup temp
        self._s3.delete_object(Bucket=self.bucket, Key=tmp_key)

    def load(self, run_id: str, step: int) -> bytes:
        key = self._key(run_id, step)
        try:
            response = self._s3.get_object(Bucket=self.bucket, Key=key)
            return response["Body"].read()
        except self._s3.exceptions.NoSuchKey:
            raise FileNotFoundError(f"Checkpoint not found: run={run_id}, step={step}")
        except Exception as e:
            if "NoSuchKey" in str(type(e).__name__) or "404" in str(e):
                raise FileNotFoundError(f"Checkpoint not found: run={run_id}, step={step}")
            raise

    def list_runs(self) -> list[RunInfo]:
        runs = []
        paginator = self._s3.get_paginator("list_objects_v2")
        pages = paginator.paginate(
            Bucket=self.bucket, Prefix=f"{self.prefix}/", Delimiter="/"
        )

        for page in pages:
            for prefix_obj in page.get("CommonPrefixes", []):
                run_id = prefix_obj["Prefix"].rstrip("/").split("/")[-1]
                meta = self.load_run_meta(run_id)
                if meta:
                    runs.append(meta)
                else:
                    steps = self.list_steps(run_id)
                    if steps:
                        runs.append(
                            RunInfo(
                                run_id=run_id,
                                created_at=steps[0].timestamp,
                                updated_at=steps[-1].timestamp,
                                total_steps=len(steps),
                                status="unknown",
                            )
                        )
        return runs

    def list_steps(self, run_id: str) -> list[StepInfo]:
        steps = []
        prefix = f"{self.prefix}/{run_id}/step_"
        paginator = self._s3.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=self.bucket, Prefix=prefix)

        for page in pages:
            for obj in page.get("Contents", []):
                key = obj["Key"]
                filename = key.split("/")[-1]
                if not filename.endswith(".ckpt") or filename.startswith(".tmp"):
                    continue
                try:
                    step_num = int(filename.replace("step_", "").replace(".ckpt", ""))
                except ValueError:
                    continue

                steps.append(
                    StepInfo(
                        step_number=step_num,
                        timestamp=obj["LastModified"].isoformat(),
                        checksum=obj.get("ETag", "").strip('"')[:16],
                        size_bytes=obj["Size"],
                    )
                )
        return sorted(steps, key=lambda s: s.step_number)

    def delete_run(self, run_id: str) -> None:
        prefix = f"{self.prefix}/{run_id}/"
        paginator = self._s3.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=self.bucket, Prefix=prefix)

        for page in pages:
            objects = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
            if objects:
                self._s3.delete_objects(
                    Bucket=self.bucket, Delete={"Objects": objects}
                )

    def delete_step(self, run_id: str, step: int) -> None:
        key = self._key(run_id, step)
        self._s3.delete_object(Bucket=self.bucket, Key=key)

    def save_run_meta(self, run_info: RunInfo) -> None:
        import json
        from dataclasses import asdict

        data = json.dumps(asdict(run_info), indent=2, default=str).encode("utf-8")
        self._s3.put_object(
            Bucket=self.bucket, Key=self._meta_key(run_info.run_id), Body=data
        )

    def load_run_meta(self, run_id: str) -> Optional[RunInfo]:
        import json

        try:
            response = self._s3.get_object(
                Bucket=self.bucket, Key=self._meta_key(run_id)
            )
            data = json.loads(response["Body"].read())
            return RunInfo(**data)
        except Exception:
            return None
