---
description: Maintain a CSV ledger of every surfaced app idea and its fate (triaged, feasibility-tested, validated, built, abandoned). Prevents re-litigating dead ideas.
argument-hint: <subcommand> — `add <brief.md>` | `list [--status <s>]` | `status <id> <new-status>` | `dedup <title>`
allowed-tools: [Read, Bash, Write]
---

Invoke the `idea-ledger` skill with the user's arguments: $ARGUMENTS

Subcommands map directly to `skills/idea-ledger/scripts/ledger.py`:

- `add` — parse `## N. <Title>` headings from a brief, append rows with status `surfaced`, dedup-check before commit
- `list` — print the ledger as a markdown table, optionally filtered by status
- `status` — move a row forward through the state machine; requires `--killer-assumption` for any kill-state move
- `dedup` — given a title, show the top 3 near-duplicate ledger entries before adding

The ledger file (`ledger.csv` by default) lives in the user's `App-Ideas` private repo, not this engine repo. Confirm the path with the user before initializing a new ledger.
