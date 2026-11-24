#!/usr/bin/env bash
# Copies the database and the PDFs from this computer to the server, once, before go-live.
# Run from the repo folder on the Mac or laptop (Git Bash or WSL on Windows):
#   SERVER=root@203.0.113.10 deploy/upload-data.sh
# The backend on the server is stopped during the copy so the database is never half-written.
set -euo pipefail

SERVER="${SERVER:?Set SERVER, e.g. SERVER=root@203.0.113.10}"
APP=/opt/regwatch/app
cd "$(dirname "$0")/.."

[ -f data/regwatch.db ] || { echo "No data/regwatch.db here."; exit 1; }
echo "== Consistent copy of the local database"
sqlite3 data/regwatch.db ".backup data/regwatch.upload.db"
sqlite3 data/regwatch.upload.db "pragma quick_check;" | grep -qx ok

echo "== Stop the backend on the server"
ssh "$SERVER" "systemctl stop regwatch-backend || true"

echo "== Database ($(du -h data/regwatch.upload.db | cut -f1))"
rsync -az --progress data/regwatch.upload.db "$SERVER:$APP/data/regwatch.db"
ssh "$SERVER" "rm -f $APP/data/regwatch.db-wal $APP/data/regwatch.db-shm"

echo "== PDFs and page images ($(du -sh storage | cut -f1))"
rsync -az --progress storage/originals storage/evidence "$SERVER:$APP/storage/"

ssh "$SERVER" "chown -R regwatch:regwatch $APP/data $APP/storage && chmod 700 $APP/data && chmod 600 $APP/data/regwatch.db"
rm -f data/regwatch.upload.db
echo "Done. Start it on the server: sudo -u regwatch $APP/deploy/deploy.sh"
