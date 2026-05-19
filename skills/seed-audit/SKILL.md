---
name: seed-audit
description: Audit `topics.yml` seeds against the rolling 30-day batch pool on the `data` branch. Reports which seeds produced zero surviving clusters, which produced only low-engagement noise, and recommends specific swaps. Use whenever the user says "audit my seeds", "which topics.yml seeds are dead", "is topics.yml pulling its weight", "swap weak seeds", "/seed-audit", or asks for a topics.yml refresh. Research-only: do not modify `topics.yml` automatically — produce a swap recommendation the user reviews.
argument-hint: [--data-dir <path-to-data-branch-checkout>] [--window-days 30] [--topics topics.yml]
allowed-tools: Read, Bash, Write
user-invocable: true
---

# Seed Audit

Most users edit `topics.yml` once and never look at it again. Within 6 weeks, half the seeds are dead weight — burning batch budget on queries that produce zero usable signal. This skill answers two questions:

1. **Which seeds produced nothing in the rolling 30-day window?** Candidates for removal.
2. **Which seeds are over-represented?** Candidates for thinning to avoid Reddit / search-engine bias.

It does **not** edit `topics.yml`. It produces a swap-list the user can accept, edit, or reject.

## Workflow

### Step 1 — Locate the data pool

The batch pool lives on the `data` branch. Two options:

```bash
# Option A: clone the data branch into a scratch dir
git worktree add /tmp/data-branch data 2>/dev/null || git fetch origin data:data && git worktree add /tmp/data-branch data
DATA_DIR=/tmp/data-branch/data

# Option B: caller already checked it out (CI case)
DATA_DIR=batch-data/data
```

If neither path resolves, ask the user where the data is. If no data exists yet (first month of running), exit with "Rolling pool is empty — wait for ≥7 days of batches before auditing."

### Step 2 — Run the audit script

```bash
uv run --frozen python3 skills/seed-audit/scripts/audit_seeds.py \
  --data-dir "$DATA_DIR" \
  --topics topics.yml \
  --window-days 30 \
  --emit markdown
```

Script behavior (read [scripts/audit_seeds.py](scripts/audit_seeds.py) for the full contract):
- Walks `<DATA_DIR>/*/*.json`, loads each batch report.
- Bucket per seed by `report.topic` → `{batches: N, candidates: K, clusters: C, top_score: S}`.
- Cross-references against the currently-enabled seeds in `topics.yml`.
- Classifies each seed into one of:
  - **DEAD** — 0 surviving clusters across all batches
  - **WEAK** — ≥1 batch produced clusters but top score < median
  - **HEALTHY** — clusters present, top score ≥ median
  - **DOMINANT** — single seed accounts for ≥30% of all clusters (over-represented, candidate for thinning)
  - **ORPHAN** — in the data pool but no longer in `topics.yml` (user already removed it)

### Step 3 — Recommend swaps

For each DEAD or WEAK seed, propose a replacement. The replacement should follow the 70/20/10 mix already locked in `topics.yml` (`doc.md §7`):

- DEAD pain-phrase → suggest a sibling pain-phrase scoped tighter (e.g. add an audience qualifier)
- DEAD vertical-pain → suggest a different audience with a clearer budget signal
- DEAD community firehose → suggest a more active subreddit (cross-check via a single `WebSearch` for "<sub> active members")
- DOMINANT seed → propose splitting it into 2 narrower seeds rather than removing

Do **not** invent seeds that don't follow the existing format. Quote-wrap pain phrases. Keep audience qualifiers concrete.

### Step 4 — Output the audit + swap list

Exact format:

```
# Seed audit — <YYYY-MM-DD>

Window: last <N> days   Batches: <B>   Unique seeds seen: <U>
Active in topics.yml: <A>   Orphan in data: <O>

## DEAD (no clusters, recommend remove)
- `<seed>` — 0 clusters across <n> batches
  Suggested replacement: `<new seed>`
  Why: <one short reason>

## WEAK (low yield, recommend swap)
- `<seed>` — <c> clusters, top score <s> (median: <m>)
  Suggested replacement: `<new seed>`
  Why: <one short reason>

## DOMINANT (over-represented, recommend split or thin)
- `<seed>` — <c>/<total> clusters (<%>)
  Suggested split: `<seed-a>` + `<seed-b>`
  Why: avoids over-indexing on one phrase / sub

## HEALTHY (leave alone)
- `<seed>` — <c> clusters, top score <s>
- `<seed>` — <c> clusters, top score <s>

## ORPHAN (already removed from topics.yml; will age out of pool naturally)
- `<seed>` — last batch <date>
```

After the audit, output a single `topics.yml` diff block the user can review and apply manually.

## Top-level rules

- **Don't edit `topics.yml` automatically.** The user owns that file. Produce a diff block they apply.
- **Require ≥7 days of data before declaring a seed DEAD.** Cold-start runs are noisy.
- **DOMINANT is a warning, not a kill.** A seed that produces 40% of clusters might be your best one — but it also might be drowning out signal from others. Split, don't remove.
- **ORPHAN entries are informational.** They age out of the 30-day window naturally; don't recommend action.
- **Single `WebSearch` budget per WEAK / DEAD seed.** Don't burn 30 web searches on an audit.
