"""Generate private development ingress credentials; never print their values."""

import argparse
import secrets
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values, set_key


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    target = root / "backend/.env"
    check = subprocess.run(["git", "check-ignore", "--quiet", "backend/.env"], cwd=root)
    if check.returncode != 0:
        raise SystemExit("Refusing to write credentials to a file not ignored by git")
    parser = argparse.ArgumentParser()
    parser.add_argument("--copy", choices=["byol", "webhook"])
    parser.add_argument(
        "--rotate",
        choices=["byol", "webhook"],
        help="Explicitly rotate one local development credential; update the vendor/staging too",
    )
    args = parser.parse_args()
    values = dotenv_values(target)
    for name in ("VAANI_BYOL_TOKEN", "VAANI_WEBHOOK_SECRET"):
        existing = values.get(name) or ""
        rotate = args.rotate == ("byol" if name == "VAANI_BYOL_TOKEN" else "webhook")
        if existing and len(existing) < 32 and not rotate:
            raise SystemExit(
                "Existing provider credential is too short; explicit rotation required"
            )
        if not existing or rotate:
            set_key(str(target), name, secrets.token_urlsafe(48))
    if args.copy:
        if sys.platform != "win32":
            raise SystemExit(
                "Clipboard helper is Windows-only; use the private server secret store"
            )
        name = "VAANI_BYOL_TOKEN" if args.copy == "byol" else "VAANI_WEBHOOK_SECRET"
        token = str(dotenv_values(target)[name])
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "Set-Clipboard -Value ([Console]::In.ReadToEnd())",
            ],
            input=token,
            text=True,
            capture_output=True,
        )
        if result.returncode:
            raise SystemExit("Clipboard update failed; no credential was printed")
        print("Selected development credential copied privately to clipboard.")
    else:
        print("Development BYOL and webhook credentials configured privately. Flags unchanged.")


if __name__ == "__main__":
    main()
