# app-ideas-30-days-extension

> Automated app-idea pipeline. Runs every 4 hours on GitHub Actions, mines Reddit / HN / X / YouTube / TikTok / GitHub / web for "I wish there was an app for X" signals over a rolling 30-day window, synthesizes the result with Claude Code, and opens a daily PR in your private ideas repo.

This repo is a refactor of [mvanhorn/last30days-skill](https://github.com/mvanhorn/last30days-skill) — the multi-source research engine — turned into a Claude-Code-only, GitHub-Actions-driven idea factory. You don't run it interactively. You let it run; it builds the briefs.

---

## What you get

A new draft PR in `abhishekdubey331/App-Ideas` (or wherever you point it) at 23:00 UTC every day, containing 3–7 ranked app ideas mined from real engagement signal, each one citing the source posts it came from.

Example shape of the daily brief:

```markdown
# App ideas — 2026-05-04

Honest assessment: signal moderate today. PAIN+WILL-PAY combo on idea #1; rest are PAIN-only.

## 1. Async meeting prep tool for therapists
- Unmet need: solo therapists are stitching Calendly + Notion + a paper notebook to prep client sessions
- Proposed app: lightweight pre-session prep doc auto-pulled from prior session notes, $20/mo
- Evidence:
  - [r/therapists thread, 412 upvotes](https://reddit.com/...)
  - [solo dev complaining about same workflow on X](https://x.com/...)
- Existing competitors: SimplePractice, Jane App — but neither is workflow-first
- Score signal: PAIN + WILL-PAY

## 2. Self-hosted screenshot annotator
…

## What to research next
Add `solo developer workflow tools` and `local-first writing apps` to topics.yml.
```

---

## How it works

```
topics.yml  ──►  batch.yml (every 4h)                ──►  data branch
   ▲             ├ 00 UTC: reddit + hackernews            ▲
   │             ├ 04 UTC: x + bluesky                    │ writes
   │             ├ 08 UTC: youtube                        │ JSON dumps
   │             ├ 12 UTC: tiktok + instagram             │ per seed
   │             ├ 16 UTC: github + polymarket            │
   │ you edit    └ 20 UTC: web + perplexity               │
   │                          ▲
   │                          │ deterministic seed rotation by (date, hour)
   │                          │
   │                                                                  ┌─► PR draft
   └────────────────────────────►  daily-brief.yml (23 UTC)            │   ideas/2026-05-04.md
                                   ├ aggregate 30d rolling pool       │
                                   ├ Claude Code synthesizes ideas.md │
                                   └ open cross-repo PR ──────────────┘   abhishekdubey331/App-Ideas
```

**Why batches?** Each 4-hour window restricts to one source group, which gives you per-batch token attribution in the Actions log and keeps any single source's rate limits from blocking the others. **Why a rolling 30-day window?** Yesterday's complaint is still today's idea. Pain doesn't expire on a daily reset.

**Why Claude Code instead of a raw API call?** The Max-plan OAuth token covers the synthesis cost — no separate Anthropic API billing.

---

## Setup (15 minutes)

### 1. Make this repo public

GitHub Actions are unmetered on public repos. The workflows hit the 2,000-min/month free tier within ~5 days on a private repo. Your private ideas repo (`App-Ideas`) stays private — only this engine repo needs to be public.

### 2. Create the ideas repo

Anywhere you like. Default expectation: `<your-handle>/App-Ideas`, private, with a `main` branch. The daily-brief workflow will push `ideas/<YYYY-MM-DD>.md` files there as draft PRs.

### 3. Generate two secrets

Run locally (you need Claude Code installed and signed in to your Pro/Max plan):

```bash
claude setup-token
```

Copy the token. In this repo's GitHub settings → Secrets and variables → Actions → New repository secret:

- `CLAUDE_CODE_OAUTH_TOKEN` ← paste the token from `claude setup-token`
- `PAT_TOKEN` ← a [fine-grained PAT](https://github.com/settings/tokens?type=beta) scoped only to your `App-Ideas` repo, with `Contents: write` and `Pull requests: write`

The Claude Code GitHub App must also be installed on this repo. If it isn't, run `/install-github-app` in a Claude Code session — it sets the app up and you can confirm it points at this repository.

### 4. (Optional) Add source keys

Each is independent — missing a key just skips that source group on its 4-hour slot.

| Secret | Unlocks | Cost |
|---|---|---|
| `SCRAPECREATORS_API_KEY` | TikTok + Instagram + Threads + Pinterest + YouTube/TikTok comments | 10K free calls then PAYG |
| `OPENROUTER_API_KEY` | Perplexity Sonar web grounding | PAYG |
| `BRAVE_API_KEY` | Brave web search | 2,000 free queries/month |
| `XAI_API_KEY` | X / Twitter via xAI | PAYG |
| `AUTH_TOKEN` + `CT0` | X / Twitter via your browser cookies | free |
| `BSKY_HANDLE` + `BSKY_APP_PASSWORD` | Bluesky | free (app password from bsky.app) |

The "always free" sources (Reddit, HN, Polymarket, GitHub) work with no keys at all.

### 5. Edit `topics.yml`

The seed file at the repo root. 32 starter seeds following the 70/20/10 mix recommended by the opportunity-mining literature (Marc Lou's pain-vs-vitamin framing, Idea Browser's community-signal approach, F5Bot/PainOnSocial query operators):

- **70% pain-phrase seeds** — `'"I wish there was an app"'`, `'"why is there no" tool'`, `'"local-first alternative to"'`
- **20% vertical-pain seeds** — `'freelancers "I wish"'`, `'landlords "why is there no"'`, `'sysadmin "I hate"'`
- **10% community firehoses + rotating wildcards** — `site:reddit.com/r/SideProject`, `Show HN`, plus 1–2 trends you swap weekly

Edit the file directly — no rebuild, no redeploy. The next batch picks it up.

### 6. Push and wait

Workflows run on the schedule:

| When (UTC) | What |
|---|---|
| 00:00 | batch A — Reddit + HN |
| 04:00 | batch B — X + Bluesky |
| 08:00 | batch C — YouTube |
| 12:00 | batch D — TikTok + Instagram |
| 16:00 | batch E — GitHub + Polymarket |
| 20:00 | batch F — Web + Perplexity |
| 23:00 | **daily synthesis → PR in `App-Ideas`** |

You can also kick any of them manually:

- **Actions tab** → pick the workflow → *Run workflow* (with optional input overrides)
- **Label trigger** — open any issue, add the label `run-batch` (fires `batch.yml`) or `run-daily-brief` (fires `daily-brief.yml`). The workflow comments back on the issue with the run URL and auto-removes the label so the next label add fires a fresh run. Handy for one-tap testing from the GitHub UI on mobile.

Create the labels once in this repo's **Issues → Labels** UI; any color works.

---

## Reading the briefs

Watch `App-Ideas` for new draft PRs. Each PR is one day's brief. Review:

- **Trace every URL** back to the source — the synthesis is instructed never to invent evidence, but verify.
- **Drop ideas with 2+ existing competitors** — Claude is told to flag these, but check.
- **Treat PAIN + WILL-PAY items as highest priority.** A complaint with a price tag is more investable than a complaint without one.
- **Merge what's worth pursuing**, close the rest. The closed PRs are still in the repo's history if you want to revisit.

The `data/usage-log.csv` file on this repo's `data` branch tracks every daily-brief run (timestamp, run id, status, whether a brief was produced). Cross-reference against your Anthropic console for token-cost audit.

---

## Repo layout

```
.github/workflows/
  batch.yml           # every 4h: pick source group + 4 seeds, run engine, save JSON
  daily-brief.yml     # daily 23 UTC: aggregate, synthesize, cross-repo PR
  validate.yml        # CI: contract + version tests on every push
  release.yml         # legacy plugin release (kept for reference)
skills/last30days/
  SKILL.md            # the engine's runtime contract (1400+ lines)
  scripts/
    last30days.py     # CLI entry point — used by batch.yml
    aggregate_day.py  # rolling-window aggregator — used by daily-brief.yml
    select_seeds.py   # deterministic seed rotation — used by batch.yml
    lib/
      ideas.py        # opportunity classifier (pain / launch / wtp / workflow)
      pipeline.py     # multi-source orchestration
      ...             # ~47 modules: per-source clients, clustering, rerank, render
tests/                # ~80 pytest files; see test_ideas.py + test_aggregate_day.py
                      # + test_select_seeds.py for the new code in this fork
topics.yml            # the seed file you edit
doc.md                # planning + architecture notes for this refactor
```

---

## Local development

```bash
# Run the engine on a single seed (no key needed for Reddit/HN/Polymarket/GitHub)
uv run python3 skills/last30days/scripts/last30days.py "I wish there was an app" \
  --search reddit,hackernews \
  --emit ideas

# Persist a batch JSON for the aggregator
uv run python3 skills/last30days/scripts/last30days.py "freelancers I wish" \
  --search reddit \
  --emit json \
  --save-batch data/

# Aggregate a day's batches into one ideas brief
uv run python3 skills/last30days/scripts/aggregate_day.py \
  --data-dir data --window-days 30 --emit ideas --out brief.md

# Pick seeds for a specific batch slot
uv run python3 skills/last30days/scripts/select_seeds.py \
  --topics topics.yml --count 4 --date 2026-05-04 --hour 12

# Run tests
uv run pytest tests/test_ideas.py tests/test_aggregate_day.py tests/test_select_seeds.py
```

---

## Honest expectations

- **~70% of generated ideas on first runs will be noise** — already-exists, too-small, no willingness-to-pay, or too-vague. Expected and survivable.
- **The 30% that survive the four-pass filter are real.** Better than scrolling subreddits manually.
- **The pipeline does not tell you which ideas are worth *building*.** That's still a human call requiring market research, your skill fit, defensibility analysis. The pipeline tells you what to *consider*.
- **The LLM will always produce plausible-sounding ideas, even from thin data.** Counter this with: hard limit on ideas per day (top 7), minimum-evidence rule (Claude is instructed never to cite a URL not in the brief), and your own review.

See `doc.md` §8 for the longer version of this honesty pass.

---

## Credits

Engine ([`skills/last30days/scripts/lib/`](skills/last30days/scripts/lib)) and skill contract ([`skills/last30days/SKILL.md`](skills/last30days/SKILL.md)) by [Matt Van Horn](https://github.com/mvanhorn) — see [mvanhorn/last30days-skill](https://github.com/mvanhorn/last30days-skill) for the upstream and the original v3 architecture by [@j-sperling](https://github.com/j-sperling).

This fork narrows scope to Claude-Code-only, drops the multi-harness packaging, and adds the GitHub-Actions pipeline + opportunity classifier described above. MIT license. No analytics. No tracking. Your data and your ideas stay on the GitHub repos you own.
