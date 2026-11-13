import hashlib
import os
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO, Optional, Tuple
from backend.app.core.config import settings
from backend.app.core.logging import logger


class BaseStorageService(ABC):
    @abstractmethod
    def store_file(
        self,
        namespace: str,
        filename_prefix: str,
        content: bytes,
        extension: str = ".pdf",
        fanout: int = 2,
    ) -> Tuple[str, str, int]:
        """
        Stores file content immutably.
        Returns: (storage_path, sha256_hash, file_size_bytes)
        """
        pass

    @abstractmethod
    def get_file_bytes(self, storage_path: str) -> bytes:
        """Retrieves raw file content by storage path."""
        pass

    @abstractmethod
    def file_exists(self, storage_path: str) -> bool:
        """Checks if a file exists at the given storage path."""
        pass


class LocalStorageService(BaseStorageService):
    def __init__(self, root_dir: Optional[str] = None):
        self.root_dir = Path(root_dir or settings.STORAGE_LOCAL_ROOT).resolve()
        self.originals_dir = self.root_dir / settings.ORIGINALS_STORAGE_NAMESPACE
        self.evidence_dir = self.root_dir / settings.EVIDENCE_STORAGE_NAMESPACE
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        self.originals_dir.mkdir(parents=True, exist_ok=True)
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def compute_sha256(content: bytes) -> str:
        hasher = hashlib.sha256()
        hasher.update(content)
        return hasher.hexdigest()

    def store_file(
        self,
        namespace: str,
        filename_prefix: str,
        content: bytes,
        extension: str = ".pdf",
        fanout: int = 2,
    ) -> Tuple[str, str, int]:
        sha256_hash = self.compute_sha256(content)
        file_size = len(content)

        # Structure path: <namespace>/<first 2 chars of hash>/<next 2 chars>/<hash><extension>
        # (fanout=1 keeps only the first folder level, for short paths on Windows).
        target_dir = self.root_dir / namespace / sha256_hash[:2]
        if fanout >= 2:
            target_dir = target_dir / sha256_hash[2:4]
        target_dir.mkdir(parents=True, exist_ok=True)

        target_file = target_dir / f"{sha256_hash}{extension}"
        rel_path = str(target_file.relative_to(self.root_dir))

        if not target_file.exists():
            with open(target_file, "wb") as f:
                f.write(content)
            logger.info(f"Stored immutable file in {namespace}: {rel_path} ({file_size} bytes, SHA-256: {sha256_hash})")
        else:
            logger.debug(f"File already exists in storage: {rel_path} (identical SHA-256)")

        return rel_path, sha256_hash, file_size

    def get_file_bytes(self, storage_path: str) -> bytes:
        full_path = (self.root_dir / storage_path).resolve()
        if not full_path.is_relative_to(self.root_dir):
            raise PermissionError("Access outside storage boundary prohibited.")
        if not full_path.exists():
            raise FileNotFoundError(f"Storage file not found: {storage_path}")
        with open(full_path, "rb") as f:
            return f.read()

    def get_absolute_path(self, storage_path: str) -> Path:
        full_path = (self.root_dir / storage_path).resolve()
        if not full_path.is_relative_to(self.root_dir):
            raise PermissionError("Access outside storage boundary prohibited.")
        return full_path

    def file_exists(self, storage_path: str) -> bool:
        try:
            full_path = (self.root_dir / storage_path).resolve()
            return full_path.is_relative_to(self.root_dir) and full_path.exists()
        except Exception:
            return False


def get_storage_service() -> BaseStorageService:
    # Pluggable for S3 in cloud deployments
    return LocalStorageService()


storage_service = get_storage_service()
