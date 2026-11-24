# Going live on one server

RegWatch runs on one Spaceship VPS (Ubuntu 24.04, 2 GB RAM): the backend, the frontend, the SQLite database, the PDFs,
the hourly bb.org.bd checker and the page reader, behind Caddy for HTTPS. About 1 hour end to end.
Everything below is copy-paste. `amarcircular.com` and `SERVER_IP` stand for your domain and the server's address.

| File | What it does |
| --- | --- |
| `setup-server.sh` | One-time server setup: firewall, fail2ban, updates, swap, Node, Caddy, app user, services |
| `regwatch.env.example` | Production settings template (copied to `/opt/regwatch/app/.env`) |
| `upload-data.sh` | One-time copy of the database and PDFs from the laptop or Mac |
| `deploy.sh` | Every release: pull `main`, migrate, build, restart, health check |
| `backup.sh` + `systemd/regwatch-backup.*` | Nightly database copy (14 days on the server) and copy to Cloudflare R2 |
| `Caddyfile` | HTTPS, security headers, `/api/` to the backend, the rest to the frontend |
| `systemd/*.service` | Backend and frontend as services that restart by themselves |

## 1. Buy and point

1. Buy Spaceship VPS Standard 1 in Singapore (Ubuntu 24.04) and the domain. Add your SSH public key while buying.
2. Domain DNS on Cloudflare: an `A` record `@` → `SERVER_IP` and a `CNAME` `www` → `amarcircular.com`.
   Set both to **DNS only** (grey cloud) for the first day so Caddy can get its certificate; switching to proxied later is fine.

## 2. Set up the server (as root)

```bash
scp deploy/setup-server.sh root@SERVER_IP:
ssh root@SERVER_IP 'DOMAIN=amarcircular.com bash setup-server.sh'
```

The repo is private: when git asks, the username is `azmainhoss` and the password is a GitHub token with read access to
the repo (GitHub, Settings, Developer settings, Fine-grained tokens, this repo only, Contents: read).

The script writes `/opt/regwatch/app/.env` with a fresh `SECRET_KEY` and `ANALYSIS_UPLOAD_TOKEN`. Fill the rest:

```bash
ssh root@SERVER_IP
nano /opt/regwatch/app/.env      # GEMINI_API_KEY (and GEMINI_EXTRA_API_KEYS), later the SMTP_* lines
grep ANALYSIS_UPLOAD_TOKEN /opt/regwatch/app/.env   # copy this value to the laptop (step 6)
```

## 3. Copy the database and PDFs (from the Mac or laptop, repo folder)

```bash
SERVER=root@SERVER_IP deploy/upload-data.sh
```

It stops the backend, copies `data/regwatch.db` (a consistent copy, checked) and `storage/`, and sets the owner and
permissions. Do this once. After go-live the server's database is the real one: never copy a database over it again.

## 4. Start it

```bash
ssh root@SERVER_IP
sudo -u regwatch /opt/regwatch/app/deploy/deploy.sh
systemctl reload caddy
curl -fsS https://amarcircular.com/api/v1/health
```

## 5. Accounts (on the server)

The laptop database still has demo and test logins whose passwords are in this repo. Switch them off, then create the
real ones. Each new password is printed once.

```bash
cd /opt/regwatch/app
sudo -u regwatch .venv/bin/python backend/scripts/manage_accounts.py disable-demo --yes
sudo -u regwatch .venv/bin/python backend/scripts/manage_accounts.py create-admin --email you@amarcircular.com --name "Your Name"
sudo -u regwatch .venv/bin/python backend/scripts/manage_accounts.py create-bank-user --email cco@bank.com --name "Name" --bank "Bank PLC"
sudo -u regwatch .venv/bin/python backend/scripts/manage_accounts.py list
```

## 6. Phase 1 analysis from the laptop

New circulars appear on the site at once with "Not checked yet". The server does not analyse them (`ANALYSIS_AUTO_ENABLED=false`,
no analysis model). Twice a day the laptop queues them for the Claude runs and uploads the finished analyses.

On the laptop, in `F:\side-income\regwatch-bangladesh\.env`, add:

```
REGWATCH_SERVER_URL=https://amarcircular.com
REGWATCH_UPLOAD_TOKEN=<the ANALYSIS_UPLOAD_TOKEN from the server>
```

Then in PowerShell, in that folder: `git pull`, then `powershell -File backend\scripts\register_phase1_sync.ps1`.
Turn off the old laptop jobs that wrote to the laptop's own database: `RegWatchLiveChecker`, `RegWatchPageReader`,
`RegWatchAnalysisSync` (`schtasks /change /tn <name> /disable`). The server now does the checking and the page reading.

The admin gets an alert when no analysis has been uploaded for a day while new circulars wait, and when no check of
bb.org.bd has succeeded for 3 hours inside the 09:00-19:00 window.

## 7. Email (Brevo, free)

1. Create a Brevo account, add the domain, and add the DNS records Brevo shows (DKIM `TXT`, the Brevo code `TXT`).
2. SPF: one `TXT` on `@`: `v=spf1 include:spf.brevo.com ~all`. DMARC: `TXT` on `_dmarc`: `v=DMARC1; p=none; rua=mailto:you@amarcircular.com`.
3. In `.env`: `SMTP_HOST=smtp-relay.brevo.com`, `SMTP_PORT=587`, `SMTP_USERNAME` and `SMTP_PASSWORD` from Brevo's SMTP page,
   `SMTP_FROM=alerts@amarcircular.com`. Then `systemctl restart regwatch-backend`. Admin console, Alerts: "Send me a test email".

## 8. Backups to Cloudflare R2

1. Cloudflare, R2: create the bucket `regwatch-backup`, then an API token with Object Read & Write on that bucket.
2. On the server: `sudo -u regwatch rclone config` → new remote named `r2`, type `s3`, provider `Cloudflare`, the access key,
   secret and endpoint from Cloudflare.
3. Test now: `sudo -u regwatch /opt/regwatch/app/deploy/backup.sh`. The timer then runs it every night at 02:30 Bangladesh time.

Restore: stop the backend, `gunzip` a copy from `/var/backups/regwatch/` (or download it from R2), put it at
`/opt/regwatch/app/data/regwatch.db`, owner `regwatch`, start the backend.

## 9. Last checks before telling banks

- Sign in as a bank user on the live site, open a circular, its source page and mind map, search, email it to yourself, assign it.
- `journalctl -u regwatch-backend --since today | grep -i "finished\|error"`: the hourly check runs and finds the list.
- After you can log in with your SSH key: `echo "PasswordAuthentication no" > /etc/ssh/sshd_config.d/50-regwatch.conf && systemctl reload ssh`.

## Every later release

```bash
ssh root@SERVER_IP 'sudo -u regwatch /opt/regwatch/app/deploy/deploy.sh'
```

It takes a database safety copy (`data/regwatch.before-deploy.db`) before migrations and only restarts after a good build.
Logs: `journalctl -u regwatch-backend -f`, `journalctl -u regwatch-frontend -f`, `/var/log/caddy/regwatch.log`.
