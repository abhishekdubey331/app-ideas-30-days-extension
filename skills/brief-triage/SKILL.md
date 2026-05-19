---
name: brief-triage
description: Triage a daily app-ideas brief into three buckets so the user only feasibility-tests the ones that survive eye-test. Reads an `ideas.md` produced by the daily-brief workflow and outputs one verdict per idea — OBVIOUS NO / WORTH FEASIBILITY / NEEDS INFO — with a five-word reason. Use whenever the user says "triage today's brief", "which ideas should I feasibility-test", "kill the noise in this brief", "/brief-triage", or pastes an ideas.md file and asks which to pursue. Research-only: do not write code, PRDs, or follow-up briefs from this skill. The output is a one-shot kill/keep table that gates which ideas move to `app-idea-feasibility`.
argument-hint: <path-to-ideas.md> — defaults to the most recent ideas/<YYYY-MM-DD>/ideas.md in the current workspace
allowed-tools: Read, Bash, WebSearch
user-invocable: true
---

# Brief Triage

A 30-seconds-per-idea filter that sits between the **daily-brief** PR landing and the **app-idea-feasibility** skill. Most ideas don't deserve a $200/7-day feasibility test — they're obvious-no on visual inspection. This skill makes that judgment explicit, quoted, and dated.

## Workflow

### Step 1 — Locate the brief

If the user passed a path, read that. Otherwise look for the most recent `ideas/<YYYY-MM-DD>/ideas.md` in the working directory (the layout produced by `.github/workflows/daily-brief.yml`). If neither exists, ask the user for the path. Do not invent ideas.

### Step 2 — Triage each idea

For every idea in the brief, assign exactly one bucket:

| Verdict | Meaning | Triggers (any one is enough) |
|---|---|---|
| **OBVIOUS NO** | Don't waste $200 on this. | Crowded mobile market with a dominant paid incumbent (Notion, Calm, Strava, Duolingo, etc.); no plausible Android/iOS form factor; WTP quote is hedged or hypothetical ("might pay", "would consider"); idea targets "everyone" or "consumers"; already shipping under that exact name on Play Store / App Store; depends on a TOS-violating scrape (X/TikTok/Instagram personal data). |
| **WORTH FEASIBILITY** | Run `app-idea-feasibility` on this. | Sharp target user (an audience with a budget signal, not a demographic); explicit WTP quote with a number OR a named paid incumbent the author is unhappy with; not already dominated by a known mobile app; plausible solo-founder distribution channel. |
| **NEEDS INFO** | One missing fact would tip the verdict either way. State the fact. | E.g. "Need to know if Play Store already has 3+ paid apps in this slot"; "Need to confirm target user is the buyer, not the user"; "WTP quote is mobile-app-shaped but evidence URL is web-only". |

**Rule:** when in doubt between OBVIOUS NO and WORTH FEASIBILITY, default to OBVIOUS NO. The cost of a missed idea is one day of opportunity; the cost of a wasted feasibility test is $200 of attention and a real-world ad budget. False-positives are more expensive than false-negatives at this stage.

Optionally do **one** lightweight `WebSearch` per idea — only to confirm a suspected dominant incumbent's existence on Play Store / App Store. Don't go deep; that's `app-idea-feasibility`'s job.

### Step 3 — Output the triage table

Write the result to stdout (and optionally to `triage.md` alongside the brief if asked). Exact format:

```
# Triage — <YYYY-MM-DD>

Brief: <relative path to ideas.md>
Total ideas: <N>   Worth feasibility: <K>   Obvious no: <M>   Needs info: <P>

| # | Idea | Verdict | Reason (≤5 words) |
|---|---|---|---|
| 1 | <idea title> | WORTH FEASIBILITY | sharp persona, $49/mo quote |
| 2 | <idea title> | OBVIOUS NO | Notion already owns this |
| 3 | <idea title> | NEEDS INFO | check Play Store paid apps |
```

After the table, a one-line **next action**:

- If `Worth feasibility` is 0: "No ideas survive triage today. Skip feasibility, wait for tomorrow's brief."
- If `Worth feasibility` is 1: "Run `/app-idea-feasibility` on idea #N."
- If `Worth feasibility` is 2+: "Two+ survive — pick the one with the sharpest WTP quote first."

## Top-level rules

- **Five-word reason cap.** "Notion already owns this" is fine; "this is a crowded market with multiple incumbents already dominant" is not. Brevity forces clarity.
- **Quote, don't paraphrase.** If you cite a competitor, name it. If you cite a WTP signal, quote it. No "good WTP signals" — write the actual phrase.
- **One pass.** Don't second-guess your own verdicts. If you find yourself re-reading an idea three times, that's a NEEDS INFO.
- **Don't expand the schema.** Three buckets, period. Adding "MAYBE" or "PROMISING" defeats the purpose.
- **Don't auto-run `/app-idea-feasibility`.** This skill ends at the table — the user decides which (if any) to feasibility-test.
