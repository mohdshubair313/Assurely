"""Independent recovery worker with a private, bounded-age health receipt."""

import argparse
import asyncio
import json
import os
import time
from pathlib import Path

from app.core.config import get_settings


def heartbeat(path: Path, healthy: bool) -> None:
    temporary = path.with_suffix(".pending")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump({"healthy": healthy, "at": time.time()}, stream)
    os.replace(temporary, path)


def healthy(path: Path, max_age: int) -> bool:
    try:
        value = json.loads(path.read_text())
        return value["healthy"] is True and 0 <= time.time() - value["at"] <= max_age
    except (OSError, ValueError, KeyError, TypeError):
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--healthcheck", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    path = Path(os.environ.get("VOICE_WORKER_HEARTBEAT_FILE", "/tmp/assurely-voice-worker.json"))
    if args.healthcheck:
        raise SystemExit(
            0 if healthy(path, max(30, settings.voice_recovery_interval_seconds * 3)) else 1
        )
    from app.db.session import AsyncSessionLocal
    from app.voice.recovery import recovery_loop

    heartbeat(path, False)
    try:
        asyncio.run(
            recovery_loop(AsyncSessionLocal, settings, lambda value: heartbeat(path, value))
        )
    finally:
        heartbeat(path, False)


if __name__ == "__main__":
    main()
