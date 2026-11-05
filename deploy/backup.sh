#!/usr/bin/env bash
# Stream directly into authenticated public-key encryption; never persist a plaintext dump.
set -Eeuo pipefail
umask 077
: "${PGHOST:?Set PGHOST}"
: "${PGDATABASE:?Set PGDATABASE}"
: "${PGUSER:?Set PGUSER}"
: "${BACKUP_RECIPIENT:?Set an age public recipient}"
if [[ "${PGSSLMODE:-}" != "verify-full" ]]; then
  echo 'Backup requires verified database TLS.' >&2
  exit 1
fi
if [[ ! "$BACKUP_RECIPIENT" =~ ^age1[a-z0-9]+$ ]]; then
  echo 'Backup requires a native age public recipient.' >&2
  exit 1
fi
# A mounted .pgpass/PGPASSFILE is preferable; neither credentials nor errors are logged.
backup_dir=/backups
temporary=$(mktemp "$backup_dir/.assurely-XXXXXXXX.age")
trap 'rm -f -- "$temporary"' EXIT
if ! pg_dump --format=custom --no-password 2>/dev/null |
     age --recipient "$BACKUP_RECIPIENT" 2>/dev/null > "$temporary"; then
  echo 'Encrypted backup failed; no completed backup was recorded.' >&2
  exit 1
fi
if [[ ! -s "$temporary" ]]; then
  echo 'Encrypted backup is empty.' >&2
  exit 1
fi
# Hard-link publication is atomic and refuses an existing filename.
backup_name="assurely-$(date -u +%Y%m%dT%H%M%SZ)-${temporary##*-}"
ln -- "$temporary" "$backup_dir/$backup_name"
printf 'Encrypted backup completed: %s\n' "$backup_name"
