#!/usr/bin/env bash
# One-time setup of a fresh Ubuntu 24.04 server for RegWatch. Run as root:
#   curl -fsSL https://raw.githubusercontent.com/azmainhoss/regwatch-bangladesh/main/deploy/setup-server.sh -o setup-server.sh
#   (private repo: copy the file over with scp instead)
#   sudo DOMAIN=amarcircular.com REPO_URL=https://github.com/azmainhoss/regwatch-bangladesh.git bash setup-server.sh
# Safe to run again. It does not touch the database or the PDFs.
set -euo pipefail

DOMAIN="${DOMAIN:-amarcircular.com}"
REPO_URL="${REPO_URL:-https://github.com/azmainhoss/regwatch-bangladesh.git}"
APP=/opt/regwatch/app
WEB=/opt/regwatch/web

[ "$(id -u)" = 0 ] || { echo "Run as root (sudo)."; exit 1; }

echo "== System packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q ca-certificates curl gnupg git rsync sqlite3 ufw fail2ban unattended-upgrades \
  python3 python3-venv python3-dev build-essential libgl1 libglib2.0-0 debian-keyring debian-archive-keyring apt-transport-https

if ! command -v node >/dev/null || [ "$(node -v | cut -d. -f1 | tr -d v)" -lt 20 ]; then
  echo "== Node.js 20"
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y -q nodejs
fi

if ! command -v caddy >/dev/null; then
  echo "== Caddy"
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -q && apt-get install -y -q caddy
fi

if ! command -v rclone >/dev/null; then
  echo "== rclone (backups to Cloudflare R2)"
  curl -fsSL https://rclone.org/install.sh | bash
fi

echo "== Automatic security updates"
dpkg-reconfigure -f noninteractive unattended-upgrades

echo "== Firewall: SSH, HTTP, HTTPS only"
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo "== fail2ban for SSH"
cat > /etc/fail2ban/jail.d/sshd.local <<'EOF'
[sshd]
enabled = true
maxretry = 5
bantime = 1h
EOF
systemctl enable --now fail2ban

echo "== Swap (2 GB) so a frontend build never runs out of memory"
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  grep -q /swapfile /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

echo "== App user and folders"
id regwatch >/dev/null 2>&1 || useradd --system --create-home --home-dir /opt/regwatch --shell /bin/bash regwatch
mkdir -p /opt/regwatch "$WEB" /var/backups/regwatch /var/log/caddy
chown regwatch:regwatch /opt/regwatch "$WEB" /var/backups/regwatch

if [ ! -d "$APP/.git" ]; then
  echo "== Code from $REPO_URL (a private repo asks for a GitHub token as the password)"
  sudo -u regwatch git clone --branch main "$REPO_URL" "$APP"
fi
sudo -u regwatch mkdir -p "$APP/data" "$APP/storage/originals" "$APP/storage/evidence"

if [ ! -f "$APP/.env" ]; then
  echo "== Production settings: $APP/.env (fill every CHANGE_ME before starting)"
  install -o regwatch -g regwatch -m 600 "$APP/deploy/regwatch.env.example" "$APP/.env"
  secret=$(openssl rand -hex 48); token=$(openssl rand -hex 32)
  sed -i "s|^SECRET_KEY=CHANGE_ME|SECRET_KEY=$secret|; s|^ANALYSIS_UPLOAD_TOKEN=CHANGE_ME|ANALYSIS_UPLOAD_TOKEN=$token|" "$APP/.env"
  sed -i "s|amarcircular.com|$DOMAIN|g" "$APP/.env"
fi

echo "== Let the app user restart its own two services (deploy.sh), and nothing else"
cat > /etc/sudoers.d/regwatch <<'EOF'
regwatch ALL=(root) NOPASSWD: /usr/bin/systemctl restart regwatch-backend regwatch-frontend
EOF
chmod 440 /etc/sudoers.d/regwatch
visudo -cf /etc/sudoers.d/regwatch

echo "== Services"
install -m 644 "$APP"/deploy/systemd/*.service "$APP"/deploy/systemd/*.timer /etc/systemd/system/
sed "s|amarcircular.com|$DOMAIN|g" "$APP/deploy/Caddyfile" > /etc/caddy/Caddyfile
systemctl daemon-reload
systemctl enable regwatch-backend regwatch-frontend regwatch-backup.timer caddy

cat <<EOF

Setup done. Next steps (deploy/README.md has the details):
  1. Fill the remaining CHANGE_ME values in $APP/.env (GEMINI_API_KEY).
  2. Copy the database and PDFs:   deploy/upload-data.sh  (run on the laptop or Mac)
  3. Build and start:              sudo -u regwatch $APP/deploy/deploy.sh
  4. Point the domain's DNS A record at this server, then: systemctl reload caddy
  5. Only after you can log in with an SSH key: set "PasswordAuthentication no" in
     /etc/ssh/sshd_config.d/50-regwatch.conf and run: systemctl reload ssh
EOF
