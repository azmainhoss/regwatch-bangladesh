# RegWatch Bangladesh

Start with `HANDOFF.md` for current work, and `DECISIONS.md` for older decisions.

## Live (2026-11-24)

- Brand is **Amar Circular** (amarcircular.com). Internal names (`regwatch` user, services, `regwatch_` storage keys, the laptop's `RegWatchPhase1Sync` task) stay.
- Access (owner, 24 Nov): a device's **first 7 days are completely open** (no meter, no prompts); from day 8, **5 more circulars free**, then any click opens Register / Sign in (`frontend/services/freeViews.ts`). Read later, lists and assigning always need an account. Reader trust words are only **AI verified** / **AI draft** (no tooltips). Register = name, email, phone, company, designation, **password** (`POST /auth/quick-register`); sign in with email + password (`/auth/login`). Readers get 30-day sessions, admins 1 day. Shared circulars are readable without an account on the API (`get_document_reader`); private ones stay with their owner. Admin console: `/admin/login`, Sign-ups tab.
- Server: Spaceship VPS `104.207.77.129`, Singapore, yearly trial. SSH port 22022, key only (`ssh amarcircular` on the Mac). Domain registered at Spaceship; **DNS on Cloudflare** (nameservers frida/lamar.ns.cloudflare.com, account 20hozaifa02) with the proxy on and SSL Full (strict). Caddy trusts Cloudflare's IP ranges and passes CF-Connecting-IP to the backend; refresh the ranges in `deploy/Caddyfile` if Cloudflare changes them. Deploy: `ssh amarcircular 'sudo -u regwatch /opt/regwatch/app/deploy/deploy.sh'`.
- **Gemini via relay:** Google refuses the server's location ("User location is not supported"), so every Gemini call goes through the Cloudflare Worker `quiet-leaf-88d1.20hozaifa02.workers.dev` (Cloudflare account 20hozaifa02, worker only accepts requests from 104.207.77.129 and only `/v1beta/models/*`). Set by `GEMINI_API_BASE` in the server `.env`. If the server IP changes, edit the IP in the worker.
- Phase 1 analysis: **manual runs only** (no laptop schedule). Anthropic consumer terms s.3(7) bar scripted/unattended Pro use for a commercial service.
- History & links are automatic: better citation matching (section number left out, FE = FEPD, date must agree) and machine-confirmed change links (`claims/checks.py` `link_shown_type`, `AUTO_CONFIRM_CHECKS`). Re-apply to the library with `backend/scripts/relink_all.py`.
- Off-server backups: nightly to Cloudflare R2 bucket `amarcircular-backup`, encrypted with rclone crypt (remote `offsite`; passwords in /root/amarcircular-backup-crypt.txt and the owner's password manager). Token is limited to that bucket and the server IP. Restore tested 2026-11-24.

## Go-live decisions (as of 2026-11-24)

The checklist lives in the Claude Doc "RegWatch go-live checklist": https://claude.ai/artifact/C5EBxUcvJKnsFawf42Yrew

Decided:
- **Phase 1, until revenue:** the server checks bb.org.bd hourly and shows new circulars straight away with a "Not checked yet" badge. The laptop runs Claude analysis with the owner's Pro account twice a day and uploads the results through a protected endpoint, one circular at a time. Never copy the database file over the server's. Running cost is the server only. Move to Phase 2 at the first paying bank, if the laptop misses more than a day, or if a bank asks for same-day summaries.
- **Phase 2, summaries for new circulars:** Claude Sonnet 5.5 through the Batch API, about $10/month. This replaces the earlier choice of Opus 5.5 (about $21/month with Batch) to save cost. Before fully switching, compare Sonnet with Opus on 20–30 circulars that are already analysed.
- **Page reading:** Gemini 3.5 Flash-Lite (`gemini-flash-lite-latest`). The free tier is acceptable because the PDFs are public. Paid is $0.30 in / $2.50 out per million tokens.
- **Don't use free Gemini for summaries**, and don't use Vercel Hobby: its terms forbid commercial use.
- **Server (final, 2026-11-24):** Spaceship VPS Standard 1 in Singapore: 1 AMD core, 2 GB RAM, 25 GB NVMe, 1 TB transfer. Prepaid yearly at $42.44/year (about $3.54/month), with a 7-day free trial. Spaceship also registers the domain.
  - Only port 25 is closed, so Brevo over port 587 works.
  - Rejected: OVH VPS-1 (no Asia location available on 2026-11-24, and $5.35/month without commitment); DigitalOcean (2 GB is $12/month).
- **Planned setup:** one server runs the backend, the frontend (Next.js `output: "standalone"`), the database (SQLite on disk) and the PDFs, with Caddy for the domain and HTTPS. Turn on `SCHEDULER_ENABLED` on that one server only.
- **Checking bb.org.bd:** it works from cloud servers. A test on 2026-11-24 from GitHub Actions (Microsoft, US) got the full circular list and PDFs 16 out of 16 times, using the checker's own headers (`NoticeIndexBot/0.1`, with cookies kept). Requests that pretend to be a Chrome browser get a captcha, even from a Bangladeshi IP. The 7-day date-filter search was not tested. Keep the laptop as a backup, and for the 3 bank sites that block cloud IPs.
- **GitHub Actions** is free: unlimited in public repos, and $12 of compute a month in private repos (about 2,000 Linux minutes).
- **Target cost:** about $13.50/month: $3.54 server + about $10 Sonnet. Gemini and Brevo are free. The domain (about $10/year, from Spaceship or Porkbun, with DNS on Cloudflare) is not counted.

Still open:
- Whether the owner's dual-currency prepaid card works on Spaceship. Oracle rejected it.
- Real sizes of the database and the PDFs.
- Email: Brevo free over SMTP (port 587) works on the Spaceship VPS. Render Free blocks SMTP, so the code only sends over SMTP for now.
- A $0 fallback stack (Cloudflare Pages + Render Free + Neon + Backblaze B2 + GitHub Actions) was researched. It needs about a week of code changes: a static frontend export, an HTTPS email API, and moving jobs into a command-line script. Use it only if no card works anywhere.
