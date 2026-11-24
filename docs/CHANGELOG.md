# Amar Circular: what changed

A plain record of the changes, newest first, so anyone can see what the app went through and why. Technical detail
is in the commits (`git log`) and the linked documents.

---

## 24 November 2026 (evening): home page

- **New home page at amarcircular.com.** A headline ("Know what updates came today"), one line on what
  the site does, an **Open the library — free** button, and three live numbers: circulars in the library, issued
  this month, and shown points without a page cite (0). The picture beside it is a real point from BRPD-1 Circular
  Letter No. 40, linked to its highlighted sentence on page 1; clicking it opens that circular.
- Under the headline are the **Today / This week / This month / Read later** cards and **Ask a question**. A card
  opens the dashboard with that filter on. Ask answers right on the home page.
- **The dashboard moved to /dashboard** and works as before. Old links such as `/?doc=…` (emails, alerts, bookmarks)
  still open the right circular there.
- **Card look** on both pages: every card is white. The card whose filter is on turns solid green with a
  "✓ Selected" tag, so it is clear what the list is showing. Today shows a red NEW tag and a red number when
  something was issued today. (An earlier version gave each card its own colour; readers could not tell which one
  was selected.)

---

## 24 November 2026: go-live day

### Hosting and setup
- **Live at https://amarcircular.com.** One Spaceship VPS in Singapore (Standard 1: 1 core, 2 GB RAM, 25 GB
  disk), on the yearly plan ($42.44/year after the 7-day free trial). It runs the backend (FastAPI), the website
  (Next.js), the SQLite database and every PDF. Caddy gives HTTPS automatically.
- **Domain and DNS** are on Spaceship: `amarcircular.com` points to `104.207.77.129`, and `www` redirects to it.
- **Server security:** SSH only with a key, on port 22022 (Spaceship's port), with password login off. Firewall
  allows SSH, 80 and 443 only. fail2ban, automatic security updates and a 2 GB swap file are on.
- **Data moved from the laptop:** the database (4,791 circulars) and 1.7 GB of PDFs, integrity checked.
- **Demo logins:** all 22 demo and test logins (passwords were in the code) are switched off.
- **Backups:** a nightly copy at 02:30 Dhaka time to Cloudflare R2 (bucket `amarcircular-backup`), encrypted
  before upload. A restore was tested. The encryption passwords are with the owner.
- **Gemini:** Google refuses Gemini calls from the server's location, so they go through a small Cloudflare Worker
  relay that only the server may use. Page reading and "Ask a question" work through it.
- **The hourly bb.org.bd check runs on the server** (9:00 to 19:00 Dhaka). On its first day it found 4 new
  circulars by itself.

### Name and access
- **RegWatch is now Amar Circular** everywhere a user looks: name, logo, app icons, emails. Internal names in the
  code and server stay as they were.
- **Sign-up and sign-in:** visitors can read the dashboard and **3 circulars free**. After that, any click asks
  them to register. Register asks for name, email, phone, company, designation and password; next time they sign
  in with email and password. Readers stay signed in for 30 days.
- **Admin:** sign in at `/admin/login`. The admin console has a **Sign-ups** tab (everyone who registered, with
  search and a CSV download).

### What readers see on a circular
- **No hidden points.** Before, about 40% of summary points were hidden behind "N points are not shown here".
  Now every point is shown. Points confirmed against the page say "Page N · Checked"; the rest say **"Check page N"**,
  which opens the highlighted lines.
- **Fewer false failures** in the second page reading (Gemini reads the page image again and must agree with our
  text):
  - the strip read around a sentence is now wide enough (it often missed the sentence);
  - when it does miss, the whole page is read instead;
  - Bangla spelling variants (hasant, ি/ী, ু/ূ, । and .) no longer count as differences.
  Numbers, "not" words and circular numbers are still compared exactly.
- **Automatic number correction.** When both independent readings agree on a number and ours differs (for example
  ১৭৭ against ৭১৭), ours is corrected automatically, in the point and in its quote. The same number in the same
  place elsewhere in that circular is corrected too. 31 sentences were corrected on day one. Nothing here needs a
  person.
- Full review of the 10 cases behind these changes: `docs/review-2026-11-24-hidden-points.md`.

### Dashboard
- **Today / This week / This month / Read later cards:** clicking one jumps to the list and shows a chip such as
  "Since Sunday ✕" with the count. Click ✕ or the card again to show all.
- **Circular numbers for new departments:** new circulars from departments the checker did not know (BRD, FDIPP, …)
  now get their number, e.g. "BRD Circular No. 04".

### History & links (now automatic)
- **How it works:** when a circular is analysed, every other circular it mentions becomes a link (amends,
  repeals, supersedes, replaces, clarifies, implements or references). The app finds that circular in the library.
  It shows the links under "History & links" and marks older circulars as "Amended", "Replaced" or "Repealed".
- **Before:** every amends/repeals/supersedes link waited for a person, so no circular was ever marked as
  changed. Many cited circulars were not found because citations write the number differently.
- **Now, matching:** a citation that leaves out the department's section number ("ACD Circular No. 03" for
  "ACD-1 Circular No. 03/2026") or uses the old department name ("FE" for "FEPD") is matched when the date it gives
  agrees. The date also picks between two candidates. Never a guess.
- **Now, confirmation:** a change link is confirmed by the machine when the quote uses change words (also
  "replaced by", "extended", "relaxed", প্রতিস্থাপিত, বর্ধিত, শিথিল) and names the circular, exactly one older
  library circular matches, and the cited date agrees. The older circular's status changes by itself.
- **Live result:** 172 more citations matched; 68 change links confirmed (from 0); 63 circulars now show
  "Amended by" / "Replaced by" / "Repealed by" with a link to the newer circular; 172 circulars show links
  (from 66). Example: BRPD Circular No. 14/2012 shows "Amended by BRPD Circular No. 15/2024".
- **Still mentions only:** links whose quote is not yet confirmed by the page reading, whose quote has no
  change words, or whose cited circular is not in the library (very old circulars, GFET guidelines). They become
  confirmed by themselves when the page reading or the library catches up.

### Fixes along the way
- "Ask a question" no longer gives a server error when the answer service is unavailable; it lists the matching
  pages instead.
- A circular opened by a visitor no longer shows a red "sign in" error.

### Decisions
- **Summaries for new circulars (Phase 1):** run by hand on the laptop. Anthropic's consumer terms do not allow a
  scheduled, unattended Pro login for a commercial service. Phase 2 (Claude Sonnet through the API, about $10 a
  month) starts with the first paying bank.
- **Minimal human involvement:** no step should wait for a person by default.

### Known open items
- About 270 sentences where the two page readings disagree with each other stay "Check page N".
- Add a card to Spaceship before the trial ends, or the server stops.
