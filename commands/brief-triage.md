---
description: Triage a daily app-ideas brief into OBVIOUS NO / WORTH FEASIBILITY / NEEDS INFO buckets with a 5-word reason each.
argument-hint: <path-to-ideas.md> — defaults to the most recent ideas/<YYYY-MM-DD>/ideas.md
allowed-tools: [Read, Bash, WebSearch]
---

Invoke the `brief-triage` skill with the user's arguments: $ARGUMENTS

If no path is given, locate the most recent `ideas/<YYYY-MM-DD>/ideas.md` in the workspace and triage that. Output the verdict table per the skill's format. Do not auto-launch `/app-idea-feasibility` — the user decides which (if any) to feasibility-test.
