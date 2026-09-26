#!/usr/bin/env bash
# deploy/tests/test_backup.sh
#
# Exercises deploy/backup.sh against a throw-away copy whose BACKUP_DIR and
# APP_DIR point at a temp directory. 'docker' is stubbed via PATH, so no
# database is touched.
#
# Usage: bash deploy/tests/test_backup.sh
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
work="$(mktemp -d)"
cleanup() { rm -rf "$work"; }
trap cleanup EXIT

backups="$work/backups"
stub_dir="$work/bin"
mkdir -p "$backups" "$stub_dir"
sed -e "s|^APP_DIR=.*|APP_DIR=\"$work\"|" \
    -e "s|^BACKUP_DIR=.*|BACKUP_DIR=\"$backups\"|" \
    "$script_dir/../backup.sh" > "$work/backup.sh"

# docker stub: `pg_dump` writes a few bytes, then fails when DUMP_FAILS=1.
cat > "$stub_dir/docker" <<'STUB'
#!/usr/bin/env bash
printf 'PGDMP partial'
[ "${DUMP_FAILS:-0}" = 1 ] && exit 1
exit 0
STUB
chmod +x "$stub_dir/docker"

pass=0
fail=0
# check <desc> <test args...>
check() {
    desc="$1"
    shift
    if test "$@"; then
        echo "PASS: $desc"
        pass=$((pass + 1))
    else
        echo "FAIL: $desc"
        ls -la "$backups"
        fail=$((fail + 1))
    fi
}

today="$(date +%F)"

set +e
DUMP_FAILS=1 PATH="$stub_dir:$PATH" bash "$work/backup.sh" >/dev/null 2>&1
status=$?
set -e
check "failed pg_dump exits non-zero" "$status" -ne 0
leftover="$(find "$backups" -name '*.dump*' -print -quit)"
check "failed pg_dump leaves no .dump.tmp and no .dump" -z "$leftover"

touch -d '3 hours ago' "$backups/2000-01-01.dump.tmp"
touch -d '10 days ago' "$backups/2000-01-02.dump"
PATH="$stub_dir:$PATH" bash "$work/backup.sh" >/dev/null
check "successful run writes today's dump" -s "$backups/$today.dump"
check "prune removes a stray .dump.tmp from an interrupted run" \
    ! -e "$backups/2000-01-01.dump.tmp"
check "prune removes dumps past retention" ! -e "$backups/2000-01-02.dump"

echo
echo "test_backup.sh: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
