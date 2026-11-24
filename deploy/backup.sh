#!/usr/bin/env bash
# Nightly backup (regwatch-backup.timer). A consistent copy of the database is taken while the app runs
# (SQLite .backup), compressed, and kept for 14 days on the server. The copies and the storage/ PDFs are
# also sent off the server to the first rclone remote that exists:
#   offsite:  Cloudflare R2 (or Backblaze B2) behind rclone "crypt" (encrypted before upload). Set up with deploy/setup-offsite-backup.sh.
#   r2:       Cloudflare R2 (older option), bucket R2_BUCKET below.
set -euo pipefail

APP=/opt/regwatch/app
OUT=/var/backups/regwatch
R2_BUCKET="${R2_BUCKET:-regwatch-backup}"
STAMP=$(date -u +%Y-%m-%dT%H%MZ)
# The copies hold password hashes and the banks' workspace data: readable by the app user only.
umask 077
cd /  # run from anywhere (find needs a readable working directory)

mkdir -p "$OUT"
chmod 700 "$OUT" 2>/dev/null || true
sqlite3 "$APP/data/regwatch.db" ".backup $OUT/regwatch-$STAMP.db"
sqlite3 "$OUT/regwatch-$STAMP.db" "pragma quick_check;" | grep -qx ok || { echo "Backup copy failed its check"; exit 1; }
gzip -f "$OUT/regwatch-$STAMP.db"
find "$OUT" -name 'regwatch-*.db.gz' -mtime +14 -delete
echo "Database copy: $OUT/regwatch-$STAMP.db.gz ($(du -h "$OUT/regwatch-$STAMP.db.gz" | cut -f1))"

remotes=$(rclone listremotes 2>/dev/null || true)
if grep -qx 'offsite:' <<<"$remotes"; then
  DEST="offsite:"
elif grep -qx 'r2:' <<<"$remotes"; then
  DEST="r2:$R2_BUCKET/"
else
  DEST=""
fi

if [ -n "$DEST" ]; then
  rclone copy "$OUT/regwatch-$STAMP.db.gz" "${DEST}db/" --quiet
  # PDFs never change once stored, so a copy (not a sync) never deletes anything in the bucket.
  rclone copy "$APP/storage/originals" "${DEST}storage/originals" --quiet --transfers 4
  rclone copy "$APP/storage/evidence" "${DEST}storage/evidence" --quiet --transfers 4
  rclone delete "${DEST}db/" --min-age 30d --quiet || true
  echo "Sent off the server to ${DEST}"
else
  echo "No off-server rclone remote (offsite or r2) yet: the copy stays on this server only."
fi

# Disk check: warn in the log when the disk is 70% full (the point to move PDFs off the server).
used=$(df --output=pcent "$APP" | tail -1 | tr -dc '0-9')
[ "$used" -lt 70 ] || echo "WARNING: disk is ${used}% full"
