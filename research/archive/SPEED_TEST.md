# Archive download: speed test

Own name `RegWatchBot/0.1`, one request at a time. Gap = pause from the end of one request to the start of the next. Avg file time = time the server took to send the file.

| Start (BDT) | Gap (s) | Planned | Done | OK | Rejected | Failed | Challenge pages | Avg file time (s) | Wall time (min) | Result |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-11-13T17:57:33 | 5 | 100 | 100 | 99 | 1 | 0 | 0 | 1.04 | 10.0 | clean |
| 2026-11-13T18:07:32 | 3 | 100 | 100 | 99 | 1 | 0 | 0 | 0.77 | 6.3 | clean |
| 2026-11-13T18:13:50 | 2 | 100 | 100 | 99 | 1 | 0 | 0 | 0.82 | 4.7 | clean |

## Result (13 Nov 2026)
- 300 files in three stages, one request at a time, own name `RegWatchBot/0.1`: no challenge page at 5 s, 3 s or 2 s.
  The one "Request Rejected" file per stage is a single refused URL (skipped), not a block.
- Parallel requests were not tried. The full download is one request at a time anyway (shared lock), so
  parallel would only add risk to the live detection test for no gain.
- Rate rule: last fully clean rate (2 s) plus one step of margin = **3 s between requests**. Never below 2 s.
- Time per file is about 0.8-1.0 s, so one file takes roughly 4 s from request to request at 3 s.
- Sharing the request lock: scripts in this repo share `research/.bb_request.lock`. The detection poll on this PC
  (`E:/regwatch-research/detect/poll.py`) does not use that lock; it keeps its own `poll.lock`. The download waits
  whenever `poll.lock` is fresh, and stays quiet 02:00-02:06 BDT during the nightly check.
