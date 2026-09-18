"""Blob storage behind one small protocol: a local directory by default, S3-compatible when
STORAGE_URL is s3://bucket[/prefix]. Keys are slash-separated paths."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Protocol
from urllib.parse import urlparse

import boto3

from fieldwise.config import get_settings

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


class Storage(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, key: str) -> Path:
        root = self.root.resolve()
        path = (root / key).resolve()
        if root not in path.parents:
            raise ValueError(f"key escapes the storage root: {key!r}")
        return path

    def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()


class S3Storage:
    def __init__(self, bucket: str, prefix: str = "", client: S3Client | None = None) -> None:
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.client: S3Client = client or boto3.client("s3")

    def _key(self, key: str) -> str:
        return f"{self.prefix}/{key}" if self.prefix else key

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(
            Bucket=self.bucket, Key=self._key(key), Body=data, ContentType=content_type
        )

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=self._key(key))["Body"].read()

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=self._key(key))
        except self.client.exceptions.ClientError:
            return False
        return True

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=self._key(key))


def storage_from_url(url: str) -> Storage:
    parsed = urlparse(url)
    if parsed.scheme == "file":
        # file://./data/storage → relative; file:///abs/path → absolute
        raw = (parsed.netloc + parsed.path) if parsed.netloc else parsed.path
        return LocalStorage(Path(raw).expanduser())
    if parsed.scheme == "s3":
        return S3Storage(bucket=parsed.netloc, prefix=parsed.path)
    raise ValueError(f"unsupported STORAGE_URL scheme: {parsed.scheme!r}")


@lru_cache
def get_storage() -> Storage:
    return storage_from_url(get_settings().storage_url)
