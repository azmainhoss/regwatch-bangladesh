# RegWatch: request to pay for the Gemini API (14 November 2026)

RegWatch is the app we are building that reads Bangladesh Bank circulars and tells each bank what it now has to do and by when. It uses Google's Gemini models to read the pages and to write the analysis. Until now it has run on Gemini's free tier. I'm asking to move it to the paid tier.

## The ask
About US$100 once, on a Google Cloud billing account with a spending alert at $100. After that, about $3-5 a month to keep the app running.

The one-time money covers reading every old circular in the archive and analysing all of them. Any international card works, and it only needs one Google account.

## Why we need it now
The free tier is too small for this job. One free key allows only about 17 analysis calls a day. A single test of the analysis on 40 circulars needs about 42 calls, so each test takes a day or more. The archive holds about 4,800 circulars.

Spreading the work over many free projects breaks Google's rules. On 14 November Google suspended 7 projects on one of our accounts for "repeated Terms of Service violations", because extra free projects had been made to get more quota. We have stopped using them. Paying is the only safe way to go faster.

Bank data also has to stay off the free tier. Google's price page says it uses free-tier content to improve its products and does not use paid-tier content. Banks will upload their own documents, so we would need the paid tier before launch in any case.

## What it costs
These prices come from Google's own price page, checked on 14 Nov 2026. Google charges per token, and a token is roughly three quarters of a word. Gemini Flash, the model that writes the analysis, costs $0.75 per million tokens sent in and $3.75 per million tokens it writes, until 31 December 2026. From 1 January 2027 those double to $1.50 and $7.50.

Batch mode means sending the work in one go and getting the results back within a day. It costs half. Flash-Lite, the cheaper model that reads scanned and Bangla pages, costs $0.30 in and $2.50 out, also half in batch mode.

The Flash version we tested on the free tier (3.5) is no longer on the price page. The paid run would use Flash 3.6 or 3.8, after a quick re-test.

| Job | Size | Cost before 31 Dec 2026 |
|---|---|---|
| Analyse every circular in the archive | 4,784 circulars, about 9,300 tokens each | about $55 in batch mode ($110 without) |
| Read the remaining scanned and Bangla pages | about 7,200 pages | about $11-21 (estimate) |
| Test the main paid models against our answer key (optional) | 40 circulars per model | about $20-35 |
| One-time total | | about $85-100 |
| Running costs after that | about 10 new circulars a week, page reading, and questions | about $3-5 a month |

Doing the archive before 31 December costs half what it will cost after.

## Where the work stands
We now have an answer key for 40 test circulars: the correct requirements, deadlines and links for each one, spot-checked against the page images. A script scores the app's analysis against it automatically.

I tuned the analysis against that key one change at a time. A change stayed only if the score went up and no more wrong statements reached the customer. Here is what changed:

- The overall score went from 12.8 to 29.3 out of 100. About 3 of those points came from a fairer way of scoring deadlines written in words, which I changed partway through. The rest is real improvement.
- The requirements score went from 11% to 42%. It counts a requirement as right only when its type, who it applies to, and its deadline are all correct, and it weighs what was found against what was missed.
- Wrong statements fell from 18.5% to 15.7% of what a customer sees. Anything that fails a check is held back for a person, as the product promises.
- The app can now show a deadline written in words, such as "within 1 month of the circular date". Before, it could only show calendar dates.
- 4,784 past circulars are in the library. About 11,500 of their 18,700 pages are already read.

The biggest gains left need more model calls than the free tier allows. Next I would test the stronger paid models on the same answer key and pick one.

## What I need from you
1. A yes to the budget: about $100 once, then $3-5 a month.
2. Either set up billing on one Google Cloud account, or share a card so I can. I will set the $100 spending alert at the same time.
