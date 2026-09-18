from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from fieldwise.storage import LocalStorage, S3Storage, storage_from_url


def test_local_storage_round_trip(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path / "store")
    storage.put("documents/1/original.pdf", b"%PDF", "application/pdf")
    assert storage.exists("documents/1/original.pdf")
    assert storage.get("documents/1/original.pdf") == b"%PDF"
    storage.delete("documents/1/original.pdf")
    assert not storage.exists("documents/1/original.pdf")
    storage.delete("documents/1/original.pdf")  # idempotent


def test_local_storage_refuses_path_escape(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path / "store")
    with pytest.raises(ValueError, match="escapes"):
        storage.put("../outside", b"x", "text/plain")


@mock_aws
def test_s3_storage_round_trip() -> None:
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="fieldwise-test")
    storage = S3Storage("fieldwise-test", prefix="/dev/", client=client)
    storage.put("documents/1/pages/1.jpg", b"jpeg", "image/jpeg")
    assert storage.exists("documents/1/pages/1.jpg")
    assert storage.get("documents/1/pages/1.jpg") == b"jpeg"
    assert client.head_object(Bucket="fieldwise-test", Key="dev/documents/1/pages/1.jpg")
    storage.delete("documents/1/pages/1.jpg")
    assert not storage.exists("documents/1/pages/1.jpg")


def test_storage_from_url(tmp_path: Path) -> None:
    local = storage_from_url(f"file://{tmp_path}/blobs")
    assert isinstance(local, LocalStorage)
    assert local.root == tmp_path / "blobs"
    relative = storage_from_url("file://./data/storage")
    assert isinstance(relative, LocalStorage)
    assert relative.root == Path("./data/storage")
    with mock_aws():
        s3 = storage_from_url("s3://bucket/prefix")
        assert isinstance(s3, S3Storage)
        assert (s3.bucket, s3.prefix) == ("bucket", "prefix")
    with pytest.raises(ValueError, match="scheme"):
        storage_from_url("ftp://x")
