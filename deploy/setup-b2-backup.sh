#!/usr/bin/env bash
# One-time: connect the nightly backup to Backblaze B2, encrypted before upload (rclone crypt).
# Run on the server as root, interactively (from the Mac: ssh -t amarcircular 'bash /opt/regwatch/app/deploy/setup-b2-backup.sh').
# It asks for the B2 application key ID and key (the key is typed hidden), creates two rclone remotes for the
# app user (b2 = the bucket, offsite = encrypted folder inside it) and prints the encryption passwords ONCE.
# Save those passwords in your password manager: without them the backups cannot be read, by anyone.
set -euo pipefail

[ "$(id -u)" = 0 ] || { echo "Run as root."; exit 1; }
APP_USER=regwatch
RC=(sudo -u "$APP_USER" -H rclone)

read -r -p "B2 bucket name [amarcircular-backup]: " BUCKET
BUCKET=${BUCKET:-amarcircular-backup}
read -r -p "B2 application keyID: " KEY_ID
read -r -s -p "B2 application key (hidden): " APP_KEY; echo
[ -n "$KEY_ID" ] && [ -n "$APP_KEY" ] || { echo "Both the keyID and the key are needed."; exit 1; }

"${RC[@]}" config delete b2 >/dev/null 2>&1 || true
"${RC[@]}" config create b2 b2 account="$KEY_ID" key="$APP_KEY" hard_delete=false >/dev/null
unset APP_KEY

echo "== Checking the key can see bucket $BUCKET"
"${RC[@]}" lsf "b2:$BUCKET" --max-depth 1 >/dev/null

PASS_FILE=/root/amarcircular-backup-crypt.txt
if "${RC[@]}" listremotes | grep -qx 'offsite:'; then
  echo "== Remote 'offsite' already exists: keeping its encryption passwords."
else
  P1=$(openssl rand -base64 33 | tr -d '\n'); P2=$(openssl rand -base64 33 | tr -d '\n')
  "${RC[@]}" config create offsite crypt remote="b2:$BUCKET/amarcircular" password="$P1" password2="$P2" \
    filename_encryption=standard directory_name_encryption=true --obscure >/dev/null
  umask 077
  printf 'Amar Circular backup encryption (rclone crypt, remote b2:%s/amarcircular)\npassword=%s\npassword2=%s\n' \
    "$BUCKET" "$P1" "$P2" > "$PASS_FILE"
  cat <<EOF

================ SAVE THESE NOW (password manager) ================
Backups are encrypted with these. Lose them and the backups are useless.
  password  = $P1
  password2 = $P2
(A copy is in $PASS_FILE on this server, root only. The server can die, so keep your own copy.)
===================================================================

EOF
  unset P1 P2
fi

echo "== Test: write, read back and delete a small file through the encrypted remote"
probe=$(mktemp); echo "amarcircular $(date -u +%FT%TZ)" > "$probe"; chmod 644 "$probe"
"${RC[@]}" copyto "$probe" offsite:_probe.txt
"${RC[@]}" cat offsite:_probe.txt | cmp -s - "$probe" && echo "   encrypted round trip OK"
"${RC[@]}" deletefile offsite:_probe.txt; rm -f "$probe"
echo "Done. Run the first backup now: sudo -u $APP_USER /opt/regwatch/app/deploy/backup.sh"
