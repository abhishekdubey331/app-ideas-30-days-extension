---
description: Audit which topics.yml seeds are producing usable signal in the rolling 30-day batch pool and recommend swaps for dead or low-yield seeds.
argument-hint: [--data-dir <path>] [--window-days 30] [--topics topics.yml]
allowed-tools: [Read, Bash, Write, WebSearch]
---

Invoke the `seed-audit` skill with the user's arguments: $ARGUMENTS

Locate the rolling batch pool (the `data` branch checked out locally or fetched as a worktree), run the audit script, and produce a swap-list. Do not modify `topics.yml` automatically — output a diff block the user can review and apply manually. Require ≥7 days of data before declaring any seed DEAD.
