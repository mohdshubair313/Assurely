"""Encrypted checkpoint of the named local Docker database; never a production backup claim."""

import hashlib
import json
import os
import secrets
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    directory = (root / ".local" / "database-backups").resolve()
    if not directory.is_relative_to(root):
        raise SystemExit("Backup directory is outside the workspace")
    if subprocess.run(["git", "check-ignore", "--quiet", str(directory)], cwd=root).returncode:
        raise SystemExit("Backup directory must be ignored by Git")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name == "nt":
        owner = subprocess.run(
            ["whoami"], capture_output=True, text=True, check=True
        ).stdout.strip()
        permissions = subprocess.run(
            ["icacls", str(directory), "/inheritance:r", "/grant:r", f"{owner}:(OI)(CI)F"],
            capture_output=True,
        )
        if permissions.returncode:
            raise SystemExit("Private backup directory permissions could not be established")
    else:
        directory.chmod(0o700)
    result = subprocess.run(
        [
            "docker",
            "exec",
            "insurance-postgres",
            "pg_dump",
            "-U",
            "insurance",
            "-d",
            "insurance_db",
            "-Fc",
        ],
        capture_output=True,
        timeout=120,
    )
    if result.returncode or not result.stdout.startswith(b"PGDMP"):
        raise SystemExit("Local database backup failed; no credentials or database rows printed")
    key, nonce = secrets.token_bytes(32), secrets.token_bytes(12)
    aad = b"assurely-local-postgres-backup-v1"
    encrypted = nonce + AESGCM(key).encrypt(nonce, result.stdout, aad)
    # Readability check in memory; no plaintext archive is written to the host.
    restored = AESGCM(key).decrypt(encrypted[:12], encrypted[12:], aad)
    check = subprocess.run(
        ["docker", "exec", "-i", "insurance-postgres", "pg_restore", "--list"],
        input=restored,
        capture_output=True,
        timeout=30,
    )
    if check.returncode:
        raise SystemExit("Encrypted backup archive verification failed")
    stem = datetime.now(UTC).strftime("assurely-%Y%m%dT%H%M%SZ-") + secrets.token_hex(4)
    for suffix, value in [(".aesgcm", encrypted), (".key", key)]:
        fd = os.open(directory / (stem + suffix), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(value)
    manifest = {
        "format": "nonce12 + AES-256-GCM ciphertext/tag",
        "aad": aad.decode(),
        "encrypted_file": stem + ".aesgcm",
        "key_file": stem + ".key",
        "encrypted_sha256": hashlib.sha256(encrypted).hexdigest(),
        "plaintext_sha256": hashlib.sha256(restored).hexdigest(),
        "archive_readability_verified": True,
        "full_restore_drill": False,
    }
    (directory / (stem + ".json")).write_text(json.dumps(manifest, indent=2))
    print(
        json.dumps(
            {
                "encrypted_local_backup": True,
                "readability_verified": True,
                "manifest": str(directory / (stem + ".json")),
            }
        )
    )


if __name__ == "__main__":
    main()
