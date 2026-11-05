import pytest
from pathlib import Path
from backend.app.core.storage import LocalStorageService


def test_storage_immutability_and_sha256(tmp_path):
    storage = LocalStorageService(root_dir=str(tmp_path))
    content = b"PDF-1.4 Mock Bangladesh Bank Circular Content"
    
    path, sha256_hash, size = storage.store_file(
        namespace="originals",
        filename_prefix="bb_brpd",
        content=content,
        extension=".pdf"
    )

    assert path.startswith("originals/")
    assert len(sha256_hash) == 64
    assert size == len(content)

    # Read back and verify exact byte preservation
    retrieved = storage.get_file_bytes(path)
    assert retrieved == content

    # Verify duplicate store returns same path and hash without mutating
    path2, sha256_hash2, size2 = storage.store_file(
        namespace="originals",
        filename_prefix="bb_brpd_duplicate",
        content=content,
        extension=".pdf"
    )
    assert path2 == path
    assert sha256_hash2 == sha256_hash


def test_storage_security_path_traversal(tmp_path):
    storage = LocalStorageService(root_dir=str(tmp_path))
    with pytest.raises(PermissionError):
        storage.get_file_bytes("../../../etc/passwd")
