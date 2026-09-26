#!/usr/bin/env bash
# deploy/backup.sh
#
# Nightly logical backup of the production 'planner' database. Installed
# by deploy/bootstrap.sh at /usr/local/bin/gantt-planner-backup.sh and run
# by /etc/cron.d/gantt-planner-backup at 03:15 every day. Dumps older than
# RETENTION_DAYS are pruned on every run.
set -euo pipefail

APP_DIR=/opt/gantt-planner
COMPOSE_FILE="$APP_DIR/compose.prod.yml"
BACKUP_DIR=/var/backups/gantt-planner
RETENTION_DAYS=7

mkdir -p "$BACKUP_DIR"

dump_file="$BACKUP_DIR/$(date +%F).dump"
tmp_file="${dump_file}.tmp"

# A failed or interrupted pg_dump must not leave a partial file behind.
trap 'rm -f "$tmp_file"' EXIT

docker compose -f "$COMPOSE_FILE" exec -T db pg_dump -U planner_owner -Fc planner > "$tmp_file"
mv "$tmp_file" "$dump_file"
chmod 0600 "$dump_file"

find "$BACKUP_DIR" -maxdepth 1 -name '*.dump' -mtime "+${RETENTION_DAYS}" -delete
# Leftovers of runs killed hard enough to skip the trap (SIGKILL, power loss);
# older than an hour, so a dump still being written is never touched.
find "$BACKUP_DIR" -maxdepth 1 -name '*.dump.tmp' -mmin +60 -delete

echo "gantt-planner backup: wrote $dump_file, pruned dumps older than ${RETENTION_DAYS} days"
