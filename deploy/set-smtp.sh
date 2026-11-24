#!/usr/bin/env bash
# Turns email on: writes the Brevo SMTP settings into /opt/regwatch/app/.env and restarts the backend.
# The SMTP key is typed at a hidden prompt, so it never appears on screen, in shell history or in a chat.
#
# Run from the Mac:   ssh -t amarcircular 'sudo bash /opt/regwatch/app/deploy/set-smtp.sh'
set -euo pipefail

ENV=/opt/regwatch/app/.env
LOGIN="c4f364001@smtp-brevo.com"   # Brevo SMTP login (not secret), from Brevo > SMTP & API

read -r -s -p "Paste the Brevo SMTP key, then press Enter: " KEY
echo
[ -n "$KEY" ] || { echo "No key given; nothing changed."; exit 1; }
case "$KEY" in *$'\n'*|*" "*) echo "That does not look like an SMTP key; nothing changed."; exit 1 ;; esac

set_var() {  # set_var NAME VALUE: replace the line if present, else add it
  local name="$1" value="$2" tmp
  tmp=$(mktemp)
  grep -v "^${name}=" "$ENV" > "$tmp" || true
  printf '%s=%s\n' "$name" "$value" >> "$tmp"
  cat "$tmp" > "$ENV"
  rm -f "$tmp"
}

set_var SMTP_HOST smtp-relay.brevo.com
set_var SMTP_PORT 587
set_var SMTP_TLS_MODE starttls
set_var SMTP_USERNAME "$LOGIN"
set_var SMTP_PASSWORD "$KEY"
set_var SMTP_FROM insights@amarcircular.com
set_var SMTP_FROM_NAME "Amar Circular"
set_var SMTP_ALERTS_FROM alerts@amarcircular.com
# The first daily digest covers only alerts from now on (not the days before email was switched on).
grep -q '^ALERTS_DIGEST_SINCE=' "$ENV" || set_var ALERTS_DIGEST_SINCE "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
unset KEY

chown regwatch:regwatch "$ENV"
chmod 600 "$ENV"
systemctl restart regwatch-backend
echo "Email settings saved and the backend restarted. Tell Claude it is done."
