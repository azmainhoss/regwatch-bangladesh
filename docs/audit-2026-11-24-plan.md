# Product audit: verification matrix and plan (started 24 Nov 2026)

The running checklist for the owner's audit brief. Each finding was checked against the code on 24 Nov 2026.
Status key: **Done** = implemented and verified · **Partial** · **Not done** · **Can't verify**.

Note: the brief mentions "a detailed product audit" as a separate document. Only the brief itself was received, so
the matrix covers the findings the brief lists. Send the full audit if it has more items.

---

## 1. Verification matrix

### P1

| # | Finding | Status | What the code does today | Files | Plan |
|---|---|---|---|---|---|
| A1 | Open newest circular first | **Done** | Desktop opens the first (newest) circular automatically. Phones show the list. | `app/dashboard/page.tsx` (loadData) | Keep. |
| A2 | Pending analysis shows a real loading state | **Partial** | A skeleton shows while the points load, and "Analysing…" shows only to an admin who pressed Run. A circular that is only EXTRACTED (not analysed) shows a "Not checked yet" badge and an empty analysis area, with no progress shown. | `components/CircularDetail.tsx` ~600–670, 1128 | Add a clear "Summary not ready yet: the original pages are below" state, without presenting an empty analysis as finished. |
| B1 | Replace "Checked" / "Not checked yet" with "AI draft" / "AI-verified" plus tooltips | **Not done** | Labels in `StatusBadge.tsx` and `claimWords.ts`. HUMAN_REVIEWED and MACHINE_VERIFIED both show "Checked", so automated and human checks look the same. The home hero shows "Checked". | `components/StatusBadge.tsx`, `services/claimWords.ts`, `app/search/page.tsx:37`, `app/page.tsx` | Needs approval of the exact wording (Approval 2). |
| C1 | "Back links" → "Cites" | **Done 24 Nov** | `Backtrail.tsx` says "Back links:" for the older circulars this one cites. | `components/Backtrail.tsx:70` | Fix now. |
| C2 | "Cited by" section | **Done 24 Nov** (checked live: FEPD 31/2025 shows 19) | Shows "Amended / Replaced / Repealed / Clarified by" for newer circulars. Newer circulars that only *reference* or *implement* this one are not shown. The data exists (`status.verified_incoming`). | `components/Backtrail.tsx` | Add "Cited by" from the other incoming link types. Fix now. |
| D1 | Registration in 3 steps (account after step 1) | **Not done** | One 6-field form, posted to `POST /auth/quick-register`. | `components/RegisterModal.tsx`, `backend/app/modules/identity` | Needs a backend change (create account with email + password, then PATCH profile). Wording needs approval (Approval 4). |
| E1 | First 3 days unrestricted, no meter; register only for Read later / lists / assign | **Not done** | Today: 3 free circulars per device (`freeViews.ts`), then every click opens Register. | `services/freeViews.ts`, `components/RegisterModal.tsx` (RegisterGate), `CircularDetail.tsx` | What happens on **day 4** is not specified (Approval 1). |
| F1 | "Register free to ask" text with a "Sign in" button | **Fixed 24 Nov** (reader, dashboard Ask, Search page) | Confirmed: the circular's Ask section says "Register free to ask…" but its button says "Sign in". | `components/CircularDetail.tsx:963` | Fix now: primary "Register free", secondary "Sign in". |
| G1 | Circular URLs `/circular/<dept>/<number>-<slug>` | **Not done** | Circulars open only as `/dashboard?doc=<uuid>`. Only `/circular/<id>/links` exists. | `app/` | New server-rendered route (Section 3). |
| G2 | Server-rendered content, titles, descriptions, canonical, OG | **Not done** | Every page is a client component behind `AuthGate`, which renders a spinner until JavaScript runs. Google sees no circular text. No `generateMetadata` anywhere. | `app/layout.tsx`, `components/AuthGate.tsx` | Section 3. |
| G3 | sitemap.xml, robots.txt | **Not done** | Neither exists. | — | Section 3. |
| G4 | Old URLs and redirects | **Partial** | `/?doc=` already forwards to `/dashboard?doc=`. | `app/page.tsx` | Make `/dashboard?doc=` links canonicalise to the new URL. |
| G5 | Branded 404 with search and recent circulars | **Done 24 Nov** (checked live, HTTP 404) | | `app/not-found.tsx` | |

### P2

| # | Finding | Status | Today | Plan |
|---|---|---|---|---|
| Dash-1 | Top 5 departments as pills + searchable "More" | **Not done** | 14 code-only chips (`slice(0,14)`), no full names. | Build; full names come from `institution_departments`. |
| Dash-2 | Searchable category dropdown, mobile bottom sheet | **Not done** | Category chips. | Build. |
| Dash-3 | Load more, 30 at a time, "Showing 30 of N" | **Partial** | Load more with `PAGE_SIZE = 30` exists. Check the count wording. | Small fix. |
| Dash-4 | Keep scroll position on return | **Not done** | — | Build. |
| Dash-5 | Filters in URL | **Partial** | Only `box`, `doc`, `page`, `version` are in the URL. Department, category and search words are not. | Build. |
| Dash-6 | Simpler cards (ref, title, date, one trust mark) | **Not done** | Cards carry several tags and badges. | Needs a preview (visual change). |
| Search-1 | Ranking | **Partial** | Newest first, with number/title matches lifted to the top (`feed.py`, `documents/search.py`). There is no relevance score. English→Bangla matching exists. | Add a relevance option, measured on a test set of real queries before switching the default. |
| Search-2 | Sort: Relevance / Newest | **Not done** | — | Build with Search-1. |
| Search-3 | Year presets (Last 12 months) instead of free-text years | **Not done** | Free-text `year_from` / `year_to`. | Build. |
| Search-4 | Filter counts, better empty state | **Not done** | — | Build. |
| Cmd-1 | One command bar with Search / Ask, Cmd/Ctrl+K | **Not done** | Three separate places: dashboard Ask, dashboard search, the Search page. No Cmd+K. | Needs approval (it changes navigation). |
| Reader-1 | Action order (Source pages, Mind map, History, Assign; then Save, Email; PDF in overflow) | **Not done** | Original PDF is the first action. | Build; preview first. |
| Reader-2 | One Save menu (Read later, Favourites, lists) | **Partial** | Star, bookmark and "Add to list" are separate controls. | Build. |
| Ref-1 | Real circular numbers instead of "References a circular" | **Confirmed** | Seen live on FEPD 31/2025: the "Cites" row shows a chip labelled "References a circular" instead of the cited number. The label comes from the analysis data, not the UI code. | Use the cited reference number (or "not in library" + number). |
| Ref-2 | Citation chips "Page 1 ✓" / pending | **Partial** | Chips exist as "Page N · Checked" and "Check page N". | Restyle with the terminology change. |
| Polish-1 | Nav highlight on History & links page | **Not done** | `/circular/...` highlights nothing (no nav item starts with `/circular`). | Fix. |
| Polish-2 | Mind-map zoom and pan | **Not done** | Canvas draws at a fixed scale. | Build. |
| Polish-3 | Install prompt only after the 3rd visit or a save | **Done 24 Nov** (code; can't be triggered from a desktop browser test) | | |

### P3

| Finding | Status |
|---|---|
| J/K next/previous | **Done** (dashboard) |
| S save, P source pages | **Not done** |
| Hover previews of references, transitions, empty states, list-card hierarchy | **Not done** |
| Consistent trust marks everywhere | **Not done**; depends on Approval 2 |

### Email (Section 3 of the brief)

| Item | Status | Today |
|---|---|---|
| Brevo connected to the app | **Not done** | The app sends by SMTP (`modules/alerts/mailer.py`), and `SMTP_*` in the server `.env` is **empty**, so no email is sent at all. There is no Brevo API code. |
| Domain authentication | **Done (24 Nov)** | Brevo DKIM ×2, brevo-code and DMARC `p=none` are added in Cloudflare, and Brevo shows the domain as **Authenticated**. |
| Receiving at insights@ | **Done (24 Nov)** | Cloudflare Email Routing forwards it to the owner's Gmail. |
| Outbox, retries, duplicate-send guard | **Done** | `email_outbox` (unique `dedupe_key`), `email_delivery_attempts`, retry with backoff in `worker.py`. |
| Delivery / bounce / complaint tracking | **Not done** | Only SMTP acceptance is recorded. No Brevo webhook. |
| One-click unsubscribe (RFC 8058) | **Not done** | The `List-Unsubscribe` header points at the settings page, which needs a sign-in. Gmail and Yahoo bulk rules need a one-click link. |
| Preferences | **Partial** | `alert_preferences`: per-group channel (OFF / INSTANT / DIGEST), global email on/off, library filters by department, document type and keywords. |
| Followed departments / topics alerts | **Partial** | Library alerts filter by department and keywords. There are no topic follows and no per-circular follow. |
| Saved circular amended / replaced / repealed | **Partial** | Exists only for circulars in a bank's register (`source_change`), not for personal saves. |
| Daily digest | **Done** | One per person per Dhaka day at `ALERTS_DIGEST_TIME`. |
| Weekly digest "This Week at Bangladesh Bank" + public page | **Not done** | — |
| Welcome email, password reset | **Not done** | There is no password-reset flow at all. |
| Team invitation / assignment emails | **Done** | `assigned`, `review_waiting` and other groups. |
| ⚠ Default consent | **Risk** | The "New circulars" group defaults to **email DIGEST for everyone**. As soon as SMTP is filled in, every registered user starts getting daily emails without being asked. |

### Admin

| Need | Status |
|---|---|
| Sign-ups list + CSV | Done |
| Email history / failed sends | Partial: data exists in `email_outbox`; check whether the admin screen shows it |
| Pending / failed analyses | Partial: Status page (`/summary`) |
| SEO / index status, digest runs, search monitoring | Not done |

---

## 2. Highest-risk P1 issues

1. **Google cannot read any circular.** Every page waits for JavaScript behind a spinner, and there are no circular URLs, sitemap or metadata. This is the biggest growth blocker.
2. **Trust wording hides the difference between automated and human checks.** "Checked" is used for both, and the home page and badges say "Checked" for machine checks.
3. **Email consent.** When SMTP is switched on, the default sends daily digests to all users. Also, there is no password reset, so users who forget their password are locked out.
4. **The visitor gate (3 free reads) is the opposite of the brief** (3 free days with no meter).

## 3. SEO architecture (proposal)

- New server component route `app/circular/[dept]/[slug]/page.tsx`, where slug is `<number>-<title-slug>` (for example `/circular/brpd/40-borrowers-with-court-stay-orders`). It renders the reference, title, date, status and the checked summary points with their page numbers, as HTML. It does not use `AuthGate`.
- `generateMetadata`: title "BRPD Circular Letter No. 40 (2026): <title> | Amar Circular", the summary as the description, a canonical URL, and OpenGraph/Twitter tags.
- **Indexable:** only circulars with a checked analysis (PUBLISHED_*). Circulars that are only extracted get `noindex`, to avoid thousands of thin pages.
- `app/sitemap.ts` (indexable circulars, home, weekly digests) and `app/robots.ts` (allow the public pages; block `/admin`, `/workspace`, `/alerts`, `/api`).
- `/dashboard?doc=<id>` and `/?doc=` keep working. Links in the app move to the new URLs over time, and the old URLs point to them with `rel=canonical`.
- The interactive reader (source page panel, Ask, mind map) still loads on the client, on top of the server HTML.
- Backend: add a slug and a department-code lookup endpoint (`GET /public/circulars/{dept}/{slug}`), with no login needed and only published, shared circulars.

## 4. Decisions needing the owner's approval

1. **Visitor access after day 3.** The brief says days 1–3 are unrestricted and registration is asked only for Read later, lists and assign. *Recommended:* from day 4, circulars stay readable, but the analysis (summary, requirements, dates) asks for a free registration. *Alternatives:* (a) stay unrestricted forever and gate only the account features; (b) keep today's 3-free-circulars meter.
2. **Trust words.** *Recommended:* "AI-verified" (tooltip: "Every point shown passed automated checks against the original page; not reviewed by a person"), "AI draft" (tooltip: "Not yet checked against the page; open the page to confirm"), and "Reviewed by our team" only for human-reviewed circulars. Page chips: "Page 1 ✓" / "Page 1 ·". *Alternative:* "Machine-checked" / "Unchecked".
3. **SEO: which circulars Google may index.** *Recommended:* only circulars with a checked analysis (659 today: 652 AI-checked + 7 human-reviewed; 4,129 have no analysis yet), with the summary shown openly on those pages. That is the content Google indexes; visitors see the same, so it is not cloaking. *Alternative:* index all 4,786 with the original text only.
4. **3-step registration wording.** A preview will be sent before release.
5. **Email consent (conflicts with an earlier decision).** On 24 Nov you said sign-up = opted in to marketing. The brief says "never silently subscribe existing users". Today the code would email every user a daily "new circulars" digest as soon as SMTP is switched on. *Recommended:* new users get alerts off by default plus one tick-box "Send me the weekly digest" (ticked) at registration; existing 29 users get a one-time email asking them to choose. *Alternative:* keep "sign-up = opted in" with a one-click unsubscribe in every email.
6. **Sender identity.** *Recommended:* "Amar Circular <insights@amarcircular.com>" for the digest and marketing, "Amar Circular Alerts <alerts@amarcircular.com>" for notifications and password resets.
7. **Deploying.** *Recommended:* verified bug fixes go live straight away (as so far); visible design changes go live only after you have seen a preview.

## 5. Proposed order

1. Quick P1 fixes that need no decision: Cites / Cited by, the Register CTA, the 404 page, install-prompt timing, the pending-analysis state.
2. SEO routes, sitemap and robots (after Approval 3).
3. Visitor access change (after Approval 1).
4. Trust terminology (after Approval 2), used everywhere at once.
5. 3-step registration (after Approval 4).
6. Email: one-click unsubscribe, password reset, Brevo webhook, consent defaults, then the weekly digest (after the email approvals).
7. P2 dashboard and search, then reader actions and the command bar, each with a preview.
8. P3 polish; separate plans for the calendar, redline compare and time machine.

## 6. Change log for this plan

- 24 Nov 2026: matrix written; Brevo domain authenticated; insights@ forwarding live.
- 24 Nov 2026: deployed C1, C2, F1, G5, Polish-3.
