# RegWatch Bangladesh

Start with `HANDOFF.md` for current work, and `DECISIONS.md` for older decisions.

## Go-live decisions (as of 2026-11-24)

The checklist lives in the Claude Doc "RegWatch go-live checklist": https://claude.ai/artifact/C5EBxUcvJKnsFawf42Yrew

Decided:
- **Summaries for new circulars:** Claude Sonnet 5.5 through the Batch API, about $10/month. This replaces the earlier choice of Opus 5.5 (about $21/month with Batch) to save cost. Before fully switching, compare Sonnet with Opus on 20–30 circulars that are already analysed.
- **Page reading:** Gemini 3.5 Flash-Lite (`gemini-flash-lite-latest`). The free tier is acceptable because the PDFs are public. Paid is $0.30 in / $2.50 out per million tokens.
- **Don't use free Gemini for summaries**, and don't use Vercel Hobby: its terms forbid commercial use.
- **Backend server:** DigitalOcean Basic. The 1 GB size is $6/month; the 2 GB size at $12/month is safer if the frontend runs on the same server. Prices checked on DigitalOcean's pricing page on 2026-11-24. If DigitalOcean rejects the card, the fallback is Render Starter at $7/month.
- **Planned setup:** one server runs the backend, the frontend (Next.js `output: "standalone"`), the database (SQLite on disk) and the PDFs, with Caddy for the domain and HTTPS. Turn on `SCHEDULER_ENABLED` on that one server only.
- **Checking bb.org.bd:** it works from cloud servers. A test on 2026-11-24 from GitHub Actions (Microsoft, US) got the full circular list and PDFs 16 out of 16 times, using the checker's own headers (`NoticeIndexBot/0.1`, with cookies kept). Requests that pretend to be a Chrome browser get a captcha, even from a Bangladeshi IP. The 7-day date-filter search was not tested. Keep the laptop as a backup, and for the 3 bank sites that block cloud IPs.
- **GitHub Actions** is free: unlimited in public repos, and $12 of compute a month in private repos (about 2,000 Linux minutes).
- **Target cost:** about $16–19/month (server plus Sonnet, with Gemini free or paid). The domain (about $10/year, from Spaceship or Porkbun, with DNS on Cloudflare) is not counted.

Still open:
- Whether the owner's dual-currency prepaid card works on DigitalOcean. Oracle rejected it.
- Real sizes of the database and the PDFs.
- Email: Brevo free over SMTP works on DigitalOcean. Render Free blocks SMTP, so the code only sends over SMTP for now.
- A $0 fallback stack (Cloudflare Pages + Render Free + Neon + Backblaze B2 + GitHub Actions) was researched. It needs about a week of code changes: a static frontend export, an HTTPS email API, and moving jobs into a command-line script. Use it only if no card works anywhere.
