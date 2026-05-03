#!/usr/bin/env python3
"""Deterministic seed-rotation helper for the batch workflow.

Reads `topics.yml` and prints N seeds for the current batch, one per line.
The selection is a deterministic round-robin keyed on (date, hour) so the
same workflow run always picks the same seeds — re-runs are reproducible
and CI failures don't shift the dataset.

Usage:
    select_seeds.py [--topics topics.yml] [--count 4] [--category pain_phrases]
                    [--date 2026-05-03] [--hour 12]

If --category is omitted, seeds are drawn from the union of all enabled
categories. --date and --hour default to "now (UTC)".
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

# The five seed-list keys recognized in topics.yml. `defaults` is metadata,
# not seeds; everything else is concatenated when --category is omitted.
SEED_KEYS = ("pain_phrases", "vertical_pains", "communities", "launch_signals", "rotating")


def load_topics(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"topics file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"topics file must be a mapping, got {type(data).__name__}")
    return data


def gather_seeds(topics: dict, category: str | None) -> list[str]:
    """Return the seed pool. Honours `enabled: false` markers if present."""
    pool: list[str] = []
    keys = (category,) if category else SEED_KEYS
    for key in keys:
        section = topics.get(key)
        if section is None:
            continue
        if isinstance(section, dict):
            if section.get("enabled") is False:
                continue
            entries = section.get("items") or []
        elif isinstance(section, list):
            entries = section
        else:
            continue
        for entry in entries:
            if isinstance(entry, str) and entry.strip():
                pool.append(entry.strip())
    return pool


def select(pool: list[str], count: int, *, date: str, hour: int) -> list[str]:
    """Pick `count` seeds with deterministic round-robin offset by date+hour."""
    if not pool:
        return []
    # Stable offset: ordinal(date) * 24 + hour. Wraps the pool so we never
    # repeat the same N within a day. Different days shift the slice.
    try:
        d = datetime.strptime(date, "%Y-%m-%d")
    except ValueError as exc:
        raise SystemExit(f"--date must be YYYY-MM-DD, got {date!r}: {exc}")
    offset = (d.toordinal() * 24 + int(hour)) % len(pool)
    rotated = pool[offset:] + pool[:offset]
    return rotated[:count]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--topics",
        default="topics.yml",
        help="Path to topics.yml (default: ./topics.yml)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=4,
        help="How many seeds to print (default: 4)",
    )
    parser.add_argument(
        "--category",
        choices=SEED_KEYS,
        help="Restrict the pool to one category. Default: union of all categories.",
    )
    now = datetime.now(tz=timezone.utc)
    parser.add_argument(
        "--date",
        default=now.strftime("%Y-%m-%d"),
        help="Date for the rotation key (default: today UTC)",
    )
    parser.add_argument(
        "--hour",
        type=int,
        default=now.hour,
        help="Hour for the rotation key 0-23 (default: now UTC)",
    )
    args = parser.parse_args(argv)

    topics_path = Path(args.topics).expanduser()
    topics = load_topics(topics_path)
    pool = gather_seeds(topics, args.category)
    if not pool:
        sys.stderr.write(
            f"[select_seeds] No seeds in pool (category={args.category or 'all'}). "
            f"Edit {topics_path} to add seeds.\n"
        )
        return 1
    chosen = select(pool, args.count, date=args.date, hour=args.hour)
    for seed in chosen:
        print(seed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
