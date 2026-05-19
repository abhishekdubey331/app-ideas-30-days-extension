# last30days Skill

Claude Code skill for researching any topic across Reddit, X, YouTube, and web.
Python scripts with multi-source search aggregation.

## Structure
- `skills/last30days/SKILL.md` — canonical skill definition
- `skills/last30days/scripts/last30days.py` — main research engine
- `skills/last30days/scripts/lib/` — search, enrichment, rendering modules
- `skills/last30days/scripts/lib/vendor/bird-search/` — vendored X search client
- `skills/brief-triage/SKILL.md` — `/brief-triage`: triage a daily `ideas.md` into OBVIOUS NO / WORTH FEASIBILITY / NEEDS INFO buckets before paying for `/app-idea-feasibility`
- `skills/seed-audit/SKILL.md` + `scripts/audit_seeds.py` — `/seed-audit`: audit `topics.yml` seeds against the rolling pool on the `data` branch, recommend swaps for dead/weak seeds
- `skills/idea-ledger/SKILL.md` + `scripts/ledger.py` — `/idea-ledger`: CSV ledger tracking every surfaced idea + its fate (state machine: surfaced → triaged → feasibility → validation → building → shipped/abandoned)

## Commands
```bash
python3 skills/last30days/scripts/last30days.py "test query" --emit=compact
bash skills/last30days/scripts/sync.sh
```

## Rules
- `lib/__init__.py` must be bare package marker (comment only, NO eager imports)
- After edits: run `bash skills/last30days/scripts/sync.sh` to deploy
- Git remote: origin = public (`mvanhorn/last30days-skill`)

## Beta channel

Experimental changes get tested on `mvanhorn/last30days-skill-private`, which installs as a parallel `/last30days-beta` slash command. Beta-only changes never ship to public without a review PR here. Workflow guide lives at `BETA.md` in the private repo. Plan that established this setup: `docs/plans/2026-04-17-005-feat-beta-skill-from-private-repo-plan.md`.
