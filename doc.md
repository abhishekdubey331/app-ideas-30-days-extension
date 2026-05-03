# App Ideas Engine — Refactor Plan

Working document. Captures decisions made, open questions, and the commit plan so we don't drift or re-litigate.

Last updated: 2026-05-03

---

## 1. Goal

Transform this repo (currently the multi-harness `last30days` research skill) into a **Claude-Code-only app-idea generation engine** that:

- Runs autonomously on GitHub Actions throughout the day in batches.
- Collects signal from Reddit, HN, X, YouTube, TikTok, Instagram, GitHub, Polymarket, and web search over a rolling 30-day window.
- At end of day, synthesizes ranked, credible app ideas (not raw briefs).
- Opens a PR with the day's ideas in a separate **private ideas repo**.
- Operates under the user's Claude Max ($200/mo) subscription via OAuth — no separate Anthropic API key purchase.

---

## 2. Architecture decisions (locked)

| Decision | Choice | Rationale |
|---|---|---|
| Harness scope | Claude Code only | User has Max plan + GitHub App; drop Hermes/Gemini/Codex. |
| Repo visibility | **Public** (this repo) | Unlimited GitHub Actions minutes. Ideas repo stays private. |
| Auth | `CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token` | Counts against Max quota, no separate API billing. |
| Runtime | GitHub Actions (hourly batches + daily synthesis) | No server to run. |
| Window | Rolling 30-day | Matches engine name; today's batch adds to pool, old data ages out. |
| State | Commit batched JSON to `data` branch | Simpler than artifacts (which expire and are job-scoped). |
| Output destination | Cross-repo PR to `abhishekdubey331/App-Ideas` | Auth via fine-grained PAT stored as `PAT_TOKEN`. |
| Cadence | Hourly batches + 1 daily synthesis at 23:00 UTC | 1-hr gap lets user see token cost per run. |

---

## 3. Required GitHub secrets

| Secret | Purpose |
|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | Auth for `anthropics/claude-code-action`. Generate via `claude setup-token`. |
| `PAT_TOKEN` | Fine-grained PAT with write access to `abhishekdubey331/App-Ideas`. Needed because default `GITHUB_TOKEN` cannot write across repos. |
| `SCRAPECREATORS_API_KEY` | (Optional) TikTok, Instagram, Threads, Pinterest, YouTube/TikTok comments. 10K free calls. |
| `OPENROUTER_API_KEY` | (Optional) Perplexity Sonar web grounding. |
| `BRAVE_API_KEY` / `EXA_API_KEY` / `SERPER_API_KEY` | (Optional) Web search backends. |
| X cookies (`AUTH_TOKEN`, `CT0`) | (Optional) X/Twitter search. |
| `BSKY_HANDLE` / `BSKY_APP_PASSWORD` | (Optional) Bluesky search. |

The pipeline already gates each source on its key (`env.py` `is_*_available` helpers). Missing keys = source skipped silently.

---

## 4. Commit plan (7 commits on `claude/general-session-fQva9`)

| # | Commit | Scope | Notes |
|---|---|---|---|
| 1 | Strip non-Claude harnesses | Delete `.codex-plugin/`, `.agents/plugins/`, `gemini-extension.json`, `HERMES_SETUP.md`. Remove Hermes branches from `sync.sh`. Keep `.claude-plugin/`, Python pipeline, tests. | Mechanical. |
| 2 | Update docs to Claude-only scope | Edit `README.md`, `CLAUDE.md`, `SKILL.md` frontmatter. Update `CONTRIBUTORS.md`. | No code changes. |
| 3 | Add `--emit=ideas` mode | New `lib/ideas.py` opportunity extractor. Wire into `last30days.py`. **Includes signal-strengthening additions (see §6).** Unit tests. | Largest commit. The real work. |
| 4 | Add rolling-window persistence | New `--save-batch <path>` flag dumps `Report` JSON. New `scripts/aggregate_day.py` globs last 30 days of `data/*.json` into one combined `Report`. TTL/cleanup step. | Straightforward JSON I/O. |
| 5 | Hourly batch workflow | `.github/workflows/batch.yml` — cron `0 * * * *`, hour-of-day picks source group, runs pipeline with `INCLUDE_SOURCES`, commits `data/YYYY-MM-DD/<hour>-<group>.json` to `data` branch. uv cache. | YAML + matrix logic. |
| 6 | Daily synthesis + cross-repo PR | `.github/workflows/daily-brief.yml` — cron `0 23 * * *`, runs `aggregate_day.py`, calls Claude Code action with ideas-extraction prompt, uses `IDEAS_REPO_PAT` to open PR with `ideas/YYYY-MM-DD.md`. | YAML + checkout/PR action for cross-repo. |
| 7 | Token usage logging + setup README | `scripts/log_usage.sh` parses Claude Code action output → `data/usage-log.csv`. README section: secrets, `claude setup-token`, reading the log. | Polish. |

Each commit is independently reviewable. Stop after any one and the repo still works.

---

## 5. Source-batching plan (open question — needs user sign-off)

Default proposal: 6 groups, every 4 hours (24h coverage):

| Hour (UTC) | Group | Sources |
|---|---|---|
| 00:00 | A | Reddit + HN |
| 04:00 | B | X + Bluesky |
| 08:00 | C | YouTube |
| 12:00 | D | TikTok + Instagram |
| 16:00 | E | GitHub + Polymarket |
| 20:00 | F | Web (Perplexity/Brave) |
| 23:00 | — | **Daily synthesis** (reads last 30 days, opens PR) |

Rationale: spreads paid-API load (ScrapeCreators), respects rate limits, gives clear per-hour token attribution. Six runs/day × ~2 min × 30 days ≈ **360 min/month** — well under any limit (and unlimited on a public repo anyway).

Hourly cadence (24 batches/day) is doable on a public repo if user wants finer-grained token tracking, but probably overkill.

---

## 6. Ideas extractor design (commit 3) — signal-strengthening

Honest take on the raw engine: it's a strong **first-stage filter**, not an oracle. To turn engagement signal into *credible* app ideas, the `--emit=ideas` mode does more than just summarize complaints. It runs four passes over the rolling 30-day clusters:

### 6.1 Pain-point extraction
Mine clusters for:
- "I wish there was an app that…"
- "Why is there no…"
- "Anyone know an app that…"
- Workflow descriptions ending in frustration
- Top-comment complaints with high upvote weight

Engagement-weighted, deduplicated by entity.

### 6.2 Launch detector
Flag clusters where:
- Entity (repo, handle, product name) didn't appear in the pool 30 days ago
- Engagement velocity is climbing (stars/upvotes/views/comments increasing day-over-day)

Sources already in the pipeline that surface launches: Show HN, r/SideProject, r/microsaas, r/InternetIsBeautiful, X "introducing"/"I built"/"launched", GitHub new repos with star velocity. Optional Product Hunt GraphQL API (free, no key) could be added as a small new source module — defer to v2 unless trivial.

### 6.3 Competitor check (per candidate)
For each candidate idea, do a quick web search: "is there already an app that does X?" Downrank or annotate if matches found. This is the single biggest credibility lever — the raw engine has no idea what already exists.

### 6.4 Willingness-to-pay heuristics
Boost clusters that mention:
- "I'd pay for this"
- "Currently paying $X for…"
- Name a paid incumbent people are unhappy with
- Workflow involving multiple paid tools stitched together

### 6.5 Market-size proxy
Cheap signals available in-pipeline:
- Subreddit subscriber count
- GitHub stars on related repos
- Engagement volume across the cluster

### Deferred to v2
- App Store / Play Store review scraping (real new source module — separate scrapers, rate limits, possibly paid)
- Crunchbase / market-size APIs

---

## 7. Topic seeding (open question)

How does the workflow know what to research? Three options, not mutually exclusive:

1. **Fixed `topics.txt`** — user maintains a list, workflow reads it. Predictable, boring, may go stale.
2. **Issue-triggered** — open an issue with a topic, workflow picks it up. On-demand.
3. **Idea-rich seed list (recommended default)** — preload topics from communities likely to surface unmet needs (r/SideProject, r/microsaas, r/Entrepreneur, r/SaaS, "Show HN this week", trending GitHub repos). Run these by default; let user add custom topics via `topics.txt` or issues.

Recommendation: option 3 as default + option 1 for user overrides + option 2 for ad-hoc.

---

## 8. Honest expectations

- ~70% of generated ideas on first runs will be noise (already exists, too small, no willingness to pay, or too vague). Expected.
- The 30% that survive the four-pass filter (§6) are real and worth investigating. Better than scrolling subreddits manually.
- The pipeline does **not** tell you which ideas are worth *building* — that's still a human call requiring market research, your skill fit, defensibility analysis. The pipeline tells you what to *consider*.
- Risk: LLM will always produce plausible-sounding ideas even from thin data. Counter this with: hard limit on ideas per day (e.g. top 5), require N-source corroboration, show evidence inline so user can sanity-check before acting.

---

## 9. Open questions (need user answers before commit 1)

1. **Source-batching plan** — accept the default 6-group / 4-hour schedule in §5, or different groupings?
2. **Topic seeding** — accept the recommended hybrid (community seeds + `topics.txt` + issue triggers) in §7, or different?
3. ~~**Private ideas repo** — does it exist yet? What's the path (`<user>/<repo>`)? Is the PAT created?~~ **ANSWERED:** repo = `abhishekdubey331/App-Ideas`, PAT stored as secret `PAT_TOKEN`.
4. **Cadence** — 6 batches/day enough, or want finer-grained hourly (24 batches/day) for token attribution? Public repo means cost isn't a constraint.

---

## 10. Things to NOT do (anti-goals)

- Do not add features beyond what's needed for the ideas pipeline (no refactoring for fun, no premature abstractions).
- Do not break the existing pipeline / tests during the strip-down.
- Do not commit `IDEAS_REPO_PAT` or any other secret to the repo.
- Do not run the workflow on every push — schedule + manual dispatch only.
- Do not generate ideas without inline evidence — every ranked idea must cite the cluster(s) it came from so user can verify.
- Do not silently skip sources in production runs — log which sources ran, which were skipped, and why (missing key, rate limited, error).
