#!/usr/bin/env bash
# Builds and (re)starts RegWatch from the main branch. Run on the server as the app user:
#   sudo -u regwatch /opt/regwatch/app/deploy/deploy.sh
# Steps: pull main, Python packages, database migrations, frontend build, restart, health check.
# A failed step stops the script before anything is restarted.
set -euo pipefail

APP=/opt/regwatch/app
WEB=/opt/regwatch/web
cd "$APP"

grep -q "CHANGE_ME" .env && { echo "Fill every CHANGE_ME in $APP/.env first."; exit 1; }
DOMAIN=$(sed -n 's|^APP_PUBLIC_URL=https\?://||p' .env | tr -d '/[:space:]')
[ -n "$DOMAIN" ] || { echo "APP_PUBLIC_URL is missing in .env"; exit 1; }

echo "== Code: main"
git fetch --quiet origin main
git checkout --quiet main
git reset --quiet --hard origin/main
echo "   at $(git log -1 --format='%h %s')"

echo "== Python packages"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r backend/requirements.txt

if [ -f data/regwatch.db ]; then
  echo "== Database: safety copy, then migrations"
  sqlite3 data/regwatch.db ".backup data/regwatch.before-deploy.db"
  .venv/bin/python -m alembic upgrade head
else
  echo "== No database yet (data/regwatch.db). Copy it with deploy/upload-data.sh, or a new empty one is created."
  .venv/bin/python -m alembic upgrade head
fi

echo "== Frontend build for https://$DOMAIN"
cd frontend
npm ci --no-fund --no-audit --loglevel=error
NEXT_PUBLIC_API_URL="https://$DOMAIN/api/v1" NEXT_TELEMETRY_DISABLED=1 npm run build
rm -rf "$WEB.new" && mkdir -p "$WEB.new"
cp -r .next/standalone/. "$WEB.new/"
mkdir -p "$WEB.new/.next" && cp -r .next/static "$WEB.new/.next/static"
[ -d public ] && cp -r public "$WEB.new/public"
cd "$APP"

echo "== Restart"
rm -rf "$WEB.old"; [ -d "$WEB" ] && mv "$WEB" "$WEB.old"; mv "$WEB.new" "$WEB"
sudo systemctl restart regwatch-backend regwatch-frontend

echo "== Health check"
for i in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8000/api/v1/health >/dev/null && curl -fsS -o /dev/null http://127.0.0.1:3000/; then
    echo "   backend and frontend are up"; rm -rf "$WEB.old"; exit 0
  fi
  sleep 2
done
echo "Not healthy after 60 s. Logs: journalctl -u regwatch-backend -u regwatch-frontend -n 100"
exit 1
