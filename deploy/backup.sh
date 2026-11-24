#!/usr/bin/env bash
# Nightly backup (regwatch-backup.timer). A consistent copy of the database is taken while the app runs
# (SQLite .backup), compressed, and kept for 14 days on the server. When an rclone remote named "r2"
# exists (Cloudflare R2), the copies and the storage/ PDFs are also sent there.
#   Set up R2 once:  sudo -u regwatch rclone config   (type s3, provider Cloudflare, name it r2)
#   Bucket name:     R2_BUCKET below (default regwatch-backup)
set -euo pipefail

APP=/opt/regwatch/app
OUT=/var/backups/regwatch
R2_BUCKET="${R2_BUCKET:-regwatch-backup}"
STAMP=$(date -u +%Y-%m-%dT%H%MZ)
# The copies hold password hashes and the banks' workspace data: readable by the app user only.
umask 077

mkdir -p "$OUT"
chmod 700 "$OUT" 2>/dev/null || true
sqlite3 "$APP/data/regwatch.db" ".backup $OUT/regwatch-$STAMP.db"
sqlite3 "$OUT/regwatch-$STAMP.db" "pragma quick_check;" | grep -qx ok || { echo "Backup copy failed its check"; exit 1; }
gzip -f "$OUT/regwatch-$STAMP.db"
find "$OUT" -name 'regwatch-*.db.gz' -mtime +14 -delete
echo "Database copy: $OUT/regwatch-$STAMP.db.gz ($(du -h "$OUT/regwatch-$STAMP.db.gz" | cut -f1))"

if rclone listremotes 2>/dev/null | grep -qx 'r2:'; then
  rclone copy "$OUT/regwatch-$STAMP.db.gz" "r2:$R2_BUCKET/db/" --quiet
  # PDFs never change once stored, so a copy (not a sync) never deletes anything in the bucket.
  rclone copy "$APP/storage/originals" "r2:$R2_BUCKET/storage/originals" --quiet --transfers 4
  rclone copy "$APP/storage/evidence" "r2:$R2_BUCKET/storage/evidence" --quiet --transfers 4
  rclone delete "r2:$R2_BUCKET/db/" --min-age 30d --quiet || true
  echo "Sent to R2 bucket $R2_BUCKET"
else
  echo "No rclone remote named r2 yet: the copy stays on this server only."
fi

# Disk check: warn in the log when the disk is 70% full (the point to move PDFs to R2).
used=$(df --output=pcent "$APP" | tail -1 | tr -dc '0-9')
[ "$used" -lt 70 ] || echo "WARNING: disk is ${used}% full"
