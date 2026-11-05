#!/usr/bin/env bash
# Run only in a disposable backup image with a tmpfs mounted at /backups.
set -Eeuo pipefail
test_dir=$(mktemp -d /tmp/backup-test-XXXXXXXX)
mkdir "$test_dir/bin"
age-keygen -o "$test_dir/identity" 2>/dev/null
export BACKUP_RECIPIENT
BACKUP_RECIPIENT=$(age-keygen -y "$test_dir/identity")
export PGHOST=synthetic.invalid PGUSER=synthetic PGDATABASE=synthetic PGSSLMODE=verify-full
export PATH="$test_dir/bin:$PATH"
printf '#!/bin/sh\nprintf synthetic-archive-bytes\n' > "$test_dir/bin/pg_dump"
chmod 700 "$test_dir/bin/pg_dump"
assurely-backup
archives=(/backups/assurely-*.age)
[[ ${#archives[@]} == 1 ]]
[[ $(age --decrypt -i "$test_dir/identity" "${archives[0]}") == synthetic-archive-bytes ]]
[[ $(stat -c '%a' "${archives[0]}") == 600 ]]
printf '#!/bin/sh\nprintf incomplete\nexit 42\n' > "$test_dir/bin/pg_dump"
if assurely-backup; then echo 'Upstream failure was accepted' >&2; exit 1; fi
archives=(/backups/assurely-*.age)
[[ ${#archives[@]} == 1 ]]
[[ $(find /backups -maxdepth 1 -name '.assurely-*' | wc -l) == 0 ]]
if PGSSLMODE=disable assurely-backup; then echo 'Unverified TLS was accepted' >&2; exit 1; fi
echo 'PASS: encrypted stream roundtrip, restrictive permissions, failed-dump cleanup, TLS requirement'
