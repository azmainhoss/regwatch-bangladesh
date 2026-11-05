import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path

BACKUP_DIR = Path("data/backups")
STORAGE_DIR = Path("storage")
DEFAULT_SQLITE_PATH = Path("data/regwatch.db")


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def create_backup(target_dir: Path = BACKUP_DIR) -> Path:
    """
    Creates an immutable cryptographic snapshot of database and private storage.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = target_dir / f"regwatch_backup_{timestamp}"
    backup_path.mkdir(parents=True, exist_ok=True)

    manifest = {
        "timestamp": timestamp,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "components": {}
    }

    # 1. Database backup
    if DEFAULT_SQLITE_PATH.exists():
        db_backup_file = backup_path / "database.db"
        # Safe SQLite snapshot with backup API
        src = sqlite3.connect(DEFAULT_SQLITE_PATH)
        dst = sqlite3.connect(db_backup_file)
        with dst:
            src.backup(dst)
        src.close()
        dst.close()
        manifest["components"]["database"] = {
            "type": "sqlite",
            "file": "database.db",
            "sha256": compute_sha256(db_backup_file),
            "size_bytes": db_backup_file.stat().st_size
        }

    # 2. Storage archive
    storage_archive = backup_path / "storage.tar.gz"
    file_count = 0
    with tarfile.open(storage_archive, "w:gz") as tar:
        if STORAGE_DIR.exists():
            for root, _, files in os.walk(STORAGE_DIR):
                for f in files:
                    file_path = Path(root) / f
                    arcname = file_path.relative_to(STORAGE_DIR)
                    tar.add(file_path, arcname=str(arcname))
                    file_count += 1

    manifest["components"]["storage"] = {
        "archive": "storage.tar.gz",
        "file_count": file_count,
        "sha256": compute_sha256(storage_archive),
        "size_bytes": storage_archive.stat().st_size
    }

    # 3. Write manifest
    manifest_file = backup_path / "manifest.json"
    manifest_file.write_text(json.dumps(manifest, indent=2))

    # Secure permissions
    os.chmod(backup_path, 0o700)
    for p in backup_path.glob("*"):
        os.chmod(p, 0o600)

    print(f"Backup created successfully at: {backup_path}")
    print(f"Database: {manifest['components'].get('database', {}).get('sha256')}")
    print(f"Storage files archived: {file_count}")
    return backup_path


def restore_backup(backup_path: Path, restore_storage_to: Path = STORAGE_DIR, restore_db_to: Path = DEFAULT_SQLITE_PATH) -> bool:
    """
    Validates manifest checksums and restores database and storage.
    """
    manifest_file = backup_path / "manifest.json"
    if not manifest_file.exists():
        raise FileNotFoundError(f"Missing manifest.json in {backup_path}")

    manifest = json.loads(manifest_file.read_text())

    # 1. Verify database integrity
    db_info = manifest["components"].get("database")
    if db_info:
        db_file = backup_path / db_info["file"]
        if compute_sha256(db_file) != db_info["sha256"]:
            raise ValueError("Database checksum mismatch! Aborting restoration.")
        restore_db_to.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(db_file, restore_db_to)
        os.chmod(restore_db_to, 0o600)
        print(f"Restored database to: {restore_db_to}")

    # 2. Verify storage integrity
    st_info = manifest["components"].get("storage")
    if st_info:
        st_archive = backup_path / st_info["archive"]
        if compute_sha256(st_archive) != st_info["sha256"]:
            raise ValueError("Storage archive checksum mismatch! Aborting restoration.")
        restore_storage_to.mkdir(parents=True, exist_ok=True)
        with tarfile.open(st_archive, "r:gz") as tar:
            tar.extractall(path=restore_storage_to)
        print(f"Restored {st_info['file_count']} storage files to: {restore_storage_to}")

    print("Restoration completed successfully and verified against manifest.")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RegWatch Bangladesh Backup & Restoration Utility")
    parser.add_argument("--action", choices=["backup", "restore"], default="backup")
    parser.add_argument("--path", type=str, help="Path for restore operation")
    args = parser.parse_args()

    if args.action == "backup":
        create_backup()
    elif args.action == "restore":
        if not args.path:
            raise ValueError("--path required for restore action.")
        restore_backup(Path(args.path))
