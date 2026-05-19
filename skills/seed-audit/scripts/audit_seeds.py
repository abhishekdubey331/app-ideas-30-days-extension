#!/usr/bin/env python3
"""Audit topics.yml seeds against the rolling batch pool on the data branch.

Run from repo root:

  uv run --frozen python3 skills/seed-audit/scripts/audit_seeds.py \
    --data-dir /tmp/data-branch/data \
    --topics topics.yml \
    --window-days 30 \
    --emit markdown

Emits a per-seed yield report. The skill's SKILL.md interprets the output
into a swap-list. This script is intentionally dumb — counting and
bucketing only, no LLM reasoning.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path


@dataclass
class SeedYield:
    seed: str
    batches: int = 0
    candidates: int = 0
    clusters: int = 0
    top_score: float = 0.0
    last_seen: str = ""
    sample_paths: list[str] = field(default_factory=list)


def _load_topics_seeds(topics_path: Path) -> set[str]:
    """Return the flat set of seed strings currently enabled in topics.yml.

    We don't import PyYAML to keep this script dependency-free; the file
    is small and well-structured enough for a line-scan parser.
    """
    seeds: set[str] = set()
    if not topics_path.exists():
        return seeds
    in_list = False
    for raw in topics_path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" ") and line.endswith(":"):
            section = line[:-1].strip()
            in_list = section in {
                "pain_phrases",
                "vertical_pains",
                "communities",
                "launch_signals",
                "rotating",
            }
            continue
        if in_list and line.lstrip().startswith("- "):
            value = line.lstrip()[2:].strip()
            # YAML quoted strings — strip outer quotes only
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            seeds.add(value)
    return seeds


def _walk_reports(data_dir: Path, window_days: int) -> list[tuple[Path, dict]]:
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=window_days)
    out: list[tuple[Path, dict]] = []
    for path in sorted(data_dir.rglob("*.json")):
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        except OSError:
            mtime = None
        if mtime and mtime < cutoff:
            # Fall back to parent-dir date so CI checkouts (mtimes get
            # clobbered) still survive.
            parent = path.parent.name
            try:
                day = datetime.strptime(parent, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if day < cutoff:
                continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[audit] Skipping {path}: {exc}", file=sys.stderr)
            continue
        out.append((path, payload))
    return out


def _top_candidate_score(report: dict) -> float:
    candidates = report.get("ranked_candidates") or []
    best = 0.0
    for cand in candidates:
        score = cand.get("final_score") or 0.0
        if score > best:
            best = float(score)
    return best


def aggregate_yields(reports: list[tuple[Path, dict]]) -> dict[str, SeedYield]:
    by_seed: dict[str, SeedYield] = defaultdict(lambda: SeedYield(seed=""))
    for path, report in reports:
        seed = (report.get("topic") or "").strip()
        if not seed:
            continue
        entry = by_seed[seed]
        if not entry.seed:
            entry.seed = seed
        entry.batches += 1
        entry.candidates += len(report.get("ranked_candidates") or [])
        entry.clusters += len(report.get("clusters") or [])
        top = _top_candidate_score(report)
        if top > entry.top_score:
            entry.top_score = top
        day_hint = path.parent.name
        if day_hint > (entry.last_seen or ""):
            entry.last_seen = day_hint
        if len(entry.sample_paths) < 3:
            entry.sample_paths.append(str(path))
    return by_seed


def classify(
    yields: dict[str, SeedYield],
    active_seeds: set[str],
) -> dict[str, list[SeedYield]]:
    if not yields:
        return {"DEAD": [], "WEAK": [], "HEALTHY": [], "DOMINANT": [], "ORPHAN": []}

    nonzero_scores = [y.top_score for y in yields.values() if y.top_score > 0]
    median_score = statistics.median(nonzero_scores) if nonzero_scores else 0.0
    total_clusters = sum(y.clusters for y in yields.values()) or 1

    buckets: dict[str, list[SeedYield]] = {
        "DEAD": [],
        "WEAK": [],
        "HEALTHY": [],
        "DOMINANT": [],
        "ORPHAN": [],
    }
    for y in yields.values():
        if y.seed not in active_seeds:
            buckets["ORPHAN"].append(y)
            continue
        share = y.clusters / total_clusters
        if share >= 0.30 and y.clusters > 0:
            buckets["DOMINANT"].append(y)
            continue
        if y.clusters == 0:
            buckets["DEAD"].append(y)
            continue
        if y.top_score < median_score:
            buckets["WEAK"].append(y)
            continue
        buckets["HEALTHY"].append(y)

    # Active seeds that produced zero data at all
    for seed in active_seeds:
        if seed not in yields:
            buckets["DEAD"].append(SeedYield(seed=seed))

    return buckets


def render_markdown(
    buckets: dict[str, list[SeedYield]],
    *,
    window_days: int,
    total_batches: int,
    total_unique: int,
    total_active: int,
) -> str:
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    lines = [
        f"# Seed audit — {today}",
        "",
        f"Window: last {window_days} days   Batches: {total_batches}   Unique seeds seen: {total_unique}",
        f"Active in topics.yml: {total_active}   Orphan in data: {len(buckets['ORPHAN'])}",
        "",
    ]

    def section(title: str, key: str, sort_key) -> None:
        items = sorted(buckets[key], key=sort_key)
        if not items:
            lines.append(f"## {title}")
            lines.append("- (none)")
            lines.append("")
            return
        lines.append(f"## {title}")
        for y in items:
            if key == "DEAD":
                lines.append(f"- `{y.seed}` — 0 clusters across {y.batches} batches")
            elif key == "WEAK":
                lines.append(
                    f"- `{y.seed}` — {y.clusters} clusters, top score {y.top_score:.2f}"
                )
            elif key == "DOMINANT":
                total = sum(z.clusters for z in buckets["HEALTHY"] + buckets["DOMINANT"]) or 1
                share = y.clusters / total * 100
                lines.append(
                    f"- `{y.seed}` — {y.clusters}/{total} clusters ({share:.0f}%)"
                )
            elif key == "HEALTHY":
                lines.append(
                    f"- `{y.seed}` — {y.clusters} clusters, top score {y.top_score:.2f}"
                )
            elif key == "ORPHAN":
                lines.append(f"- `{y.seed}` — last seen {y.last_seen or 'unknown'}")
        lines.append("")

    section("DEAD (no clusters, recommend remove)", "DEAD", lambda y: y.seed)
    section("WEAK (low yield, recommend swap)", "WEAK", lambda y: y.top_score)
    section("DOMINANT (over-represented, recommend split or thin)", "DOMINANT", lambda y: -y.clusters)
    section("HEALTHY (leave alone)", "HEALTHY", lambda y: -y.clusters)
    section("ORPHAN (already removed from topics.yml; will age out)", "ORPHAN", lambda y: y.last_seen)
    return "\n".join(lines)


def render_json(buckets: dict[str, list[SeedYield]]) -> str:
    payload = {
        bucket: [
            {
                "seed": y.seed,
                "batches": y.batches,
                "candidates": y.candidates,
                "clusters": y.clusters,
                "top_score": round(y.top_score, 4),
                "last_seen": y.last_seen,
            }
            for y in items
        ]
        for bucket, items in buckets.items()
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--topics", default=Path("topics.yml"), type=Path)
    parser.add_argument("--window-days", type=int, default=30)
    parser.add_argument("--emit", choices=["markdown", "json"], default="markdown")
    args = parser.parse_args(argv)

    data_dir: Path = args.data_dir.expanduser()
    if not data_dir.exists():
        print(f"[audit] Data dir not found: {data_dir}", file=sys.stderr)
        return 2

    active = _load_topics_seeds(args.topics.expanduser())
    reports = _walk_reports(data_dir, args.window_days)
    if not reports:
        print(
            f"[audit] No batch JSONs found under {data_dir} within "
            f"{args.window_days} days — rolling pool is empty.",
            file=sys.stderr,
        )
        return 1

    yields = aggregate_yields(reports)
    buckets = classify(yields, active)

    if args.emit == "json":
        print(render_json(buckets))
    else:
        print(
            render_markdown(
                buckets,
                window_days=args.window_days,
                total_batches=len(reports),
                total_unique=len(yields),
                total_active=len(active),
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
