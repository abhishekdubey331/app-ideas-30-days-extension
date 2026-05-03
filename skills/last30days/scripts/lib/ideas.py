"""App-idea opportunity extractor.

Walks the engagement-weighted clusters/candidates produced by the v3 pipeline
and classifies each one against four heuristic signal types relevant to
identifying buildable app ideas:

- pain_point: explicit complaints / "I wish there was an app" / unmet need
- launch:     a recently-shipped product showing engagement velocity
- wtp:        willingness-to-pay markers ("I'd pay for this", named price)
- workflow:   stitched-together-tools workflows that imply tooling gaps

Per-cluster heuristic scores stack on top of the existing pipeline score.
The output is markdown structured for Claude Code to read and synthesize
into ranked, evidence-cited app ideas. The Python layer does keyword
matching and aggregation; the LLM layer does the actual idea articulation.

This is intentionally pure-Python with no external API calls. A v2 may add
competitor checks (extra web search per candidate) and market-size proxies
(subreddit subscriber counts, GitHub star totals). Both are deferred.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from . import schema


PAIN_POINT_PATTERNS = [
    r"\bi wish (?:there was|there were|someone (?:would|could) (?:make|build))",
    r"\bwhy is there no\b",
    r"\bwhy does(?:n't| not) (?:anyone|someone|anybody) (?:make|build)",
    r"\bsomeone (?:should|needs to) (?:build|make)",
    r"\banyone know (?:of )?an? (?:app|tool|service)",
    r"\bis there an? (?:app|tool|service) (?:that|for)",
    r"\b(?:i|we) (?:keep|always) having? to\b",
    r"\b(?:so frustrating|such a pain|biggest pain)\b",
    r"\b(?:hate|loathe) (?:that|when|how)\b",
    r"\bcurrently (?:i (?:have to|need to)|using a spreadsheet|doing this manually)\b",
]

LAUNCH_PATTERNS = [
    r"\b(?:show hn|launch hn)\b",
    r"^\s*introducing\b",
    r"\bi (?:just )?(?:built|shipped|launched|made)\b",
    r"\bwe (?:just )?(?:built|shipped|launched|released)\b",
    r"\b(?:announcing|launching)\s+\w+",
    r"\bv1\.0\b|\b1\.0 (?:released|launched)\b",
]

WTP_PATTERNS = [
    r"\bi(?:'?d|\s+would)\s+(?:gladly\s+)?pay\b",
    r"\b(?:happy|willing) to pay\b",
    r"\bcurrently (?:paying|spending|using)\s+\$?\d",
    r"\$\s?\d{1,4}\s?(?:/(?:mo|month|yr|year)|\s+per\s+month)\b",
    r"\bwould pay\s+\$?\d",
    r"\btake my money\b",
    r"\bshut up and take my money\b",
]

WORKFLOW_PATTERNS = [
    r"\b(?:stitch(?:ing)?|cobble(?:d)?) together\b",
    r"\b(?:zapier|make\.com|n8n)\b.*\b(?:plus|and)\b",
    r"\bspreadsheet (?:hack|workaround)\b",
    r"\bduct[\s-]taped?\b",
    r"\b(?:multiple|several|three|four|five) (?:apps|tools)\b",
]

# Pre-compile case-insensitive
_pain_re = [re.compile(p, re.IGNORECASE) for p in PAIN_POINT_PATTERNS]
_launch_re = [re.compile(p, re.IGNORECASE) for p in LAUNCH_PATTERNS]
_wtp_re = [re.compile(p, re.IGNORECASE) for p in WTP_PATTERNS]
_workflow_re = [re.compile(p, re.IGNORECASE) for p in WORKFLOW_PATTERNS]

# Subreddits and HN tags whose mere presence signals idea-relevant context.
LAUNCH_CONTAINERS = {
    "r/sideproject", "r/microsaas", "r/saas", "r/entrepreneur",
    "r/internetisbeautiful", "r/startup_resources", "r/indiehackers",
}

SignalType = str  # "pain_point" | "launch" | "wtp" | "workflow"


@dataclass
class Evidence:
    source: str
    url: str
    title: str
    excerpt: str
    engagement: int | float | None
    published_at: str | None
    matched_signal: SignalType
    matched_phrase: str = ""


@dataclass
class Idea:
    candidate_id: str
    title: str
    signal_types: list[SignalType] = field(default_factory=list)
    pipeline_score: float = 0.0
    heuristic_boost: float = 0.0
    evidence: list[Evidence] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)

    @property
    def total_score(self) -> float:
        return self.pipeline_score + self.heuristic_boost


def _scan(text: str, patterns: list[re.Pattern[str]]) -> str | None:
    """Return the first matched substring (lowercased) or None."""
    if not text:
        return None
    for pat in patterns:
        m = pat.search(text)
        if m:
            return m.group(0).strip()
    return None


def _classify_text(text: str) -> dict[SignalType, str]:
    """Run all four pattern sets over text. Returns {signal: matched_phrase}."""
    matches: dict[SignalType, str] = {}
    for label, patterns in (
        ("pain_point", _pain_re),
        ("launch", _launch_re),
        ("wtp", _wtp_re),
        ("workflow", _workflow_re),
    ):
        hit = _scan(text, patterns)
        if hit:
            matches[label] = hit
    return matches


# Heuristic boosts (additive, on top of pipeline final_score). Calibrated so a
# strong pain-point with WTP signal can move a mid-tier candidate above a
# top-ranked but irrelevant one. Tunable.
SIGNAL_BOOST = {
    "pain_point": 0.40,
    "wtp": 0.50,
    "launch": 0.25,
    "workflow": 0.20,
}


def _container_boost(item: schema.SourceItem) -> tuple[float, str | None]:
    container = (item.container or "").strip().lower()
    if not container:
        return 0.0, None
    if not container.startswith("r/"):
        container = f"r/{container.lstrip('r/')}" if container.startswith("sideproject") else container
    if container in LAUNCH_CONTAINERS:
        return 0.15, container
    return 0.0, None


def _excerpt(text: str, phrase: str, width: int = 160) -> str:
    if not text:
        return ""
    text = " ".join(text.split())
    if not phrase:
        return text[:width].rstrip() + ("…" if len(text) > width else "")
    idx = text.lower().find(phrase.lower())
    if idx < 0:
        return text[:width].rstrip() + ("…" if len(text) > width else "")
    half = width // 2
    start = max(0, idx - half)
    end = min(len(text), idx + len(phrase) + half)
    snippet = text[start:end].strip()
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet = snippet + "…"
    return snippet


def _candidate_evidence(
    candidate: schema.Candidate,
) -> tuple[list[Evidence], set[SignalType]]:
    """Scan a candidate's source items for signal matches."""
    evidence: list[Evidence] = []
    signals: set[SignalType] = set()

    title_signals = _classify_text(candidate.title or "")
    snippet_signals = _classify_text(candidate.snippet or "")

    # Title/snippet matches use the primary item as evidence host.
    primary = schema.candidate_primary_item(candidate)
    if primary and (title_signals or snippet_signals):
        merged = {**snippet_signals, **title_signals}
        for sig, phrase in merged.items():
            signals.add(sig)
            evidence.append(Evidence(
                source=primary.source,
                url=primary.url,
                title=primary.title or candidate.title,
                excerpt=_excerpt(primary.body or primary.snippet or candidate.snippet, phrase),
                engagement=_engagement_total(primary.engagement),
                published_at=primary.published_at,
                matched_signal=sig,
                matched_phrase=phrase,
            ))

    for item in candidate.source_items:
        item_signals = _classify_text(f"{item.title}\n{item.body or item.snippet}")
        for sig, phrase in item_signals.items():
            signals.add(sig)
            evidence.append(Evidence(
                source=item.source,
                url=item.url,
                title=item.title,
                excerpt=_excerpt(item.body or item.snippet, phrase),
                engagement=_engagement_total(item.engagement),
                published_at=item.published_at,
                matched_signal=sig,
                matched_phrase=phrase,
            ))

    return evidence, signals


def _engagement_total(engagement: dict[str, float | int] | None) -> int | float | None:
    if not engagement:
        return None
    nums = [v for v in engagement.values() if isinstance(v, (int, float))]
    return sum(nums) if nums else None


def extract_ideas(
    report: schema.Report,
    *,
    top_n: int = 10,
    min_signals: int = 1,
) -> list[Idea]:
    """Walk ranked candidates, classify them, return top_n by total score.

    Candidates without any signal match are dropped. Set min_signals=0 to
    keep all candidates (useful for debugging / seeing what was filtered).
    """
    by_id = {c.candidate_id: c for c in report.ranked_candidates}
    ideas: list[Idea] = []

    for candidate in report.ranked_candidates:
        evidence, signals = _candidate_evidence(candidate)

        boost = sum(SIGNAL_BOOST.get(s, 0.0) for s in signals)
        for item in candidate.source_items:
            extra, container = _container_boost(item)
            if extra and container:
                boost += extra
                signals.add("launch")
                evidence.append(Evidence(
                    source=item.source,
                    url=item.url,
                    title=item.title,
                    excerpt=_excerpt(item.body or item.snippet, ""),
                    engagement=_engagement_total(item.engagement),
                    published_at=item.published_at,
                    matched_signal="launch",
                    matched_phrase=f"posted in {container}",
                ))
                break

        if len(signals) < min_signals:
            continue

        ideas.append(Idea(
            candidate_id=candidate.candidate_id,
            title=candidate.title or "(untitled)",
            signal_types=sorted(signals),
            pipeline_score=float(candidate.final_score or 0.0),
            heuristic_boost=boost,
            evidence=evidence,
            sources=schema.candidate_sources(candidate),
        ))

    ideas.sort(key=lambda i: i.total_score, reverse=True)
    # Defensive: if everything got filtered out at min_signals=1, fall back
    # to the top candidates with no signal so the user sees something instead
    # of an empty brief. Mark them clearly.
    if not ideas and min_signals > 0 and report.ranked_candidates:
        for candidate in report.ranked_candidates[:top_n]:
            ideas.append(Idea(
                candidate_id=candidate.candidate_id,
                title=candidate.title or "(untitled)",
                signal_types=["unscored"],
                pipeline_score=float(candidate.final_score or 0.0),
                heuristic_boost=0.0,
                evidence=[],
                sources=schema.candidate_sources(candidate),
            ))
    return ideas[:top_n]


# ---------------------------------------------------------------------------
# Markdown rendering tuned for Claude synthesis
# ---------------------------------------------------------------------------

_SIGNAL_LABEL = {
    "pain_point": "PAIN",
    "wtp": "WILL-PAY",
    "launch": "LAUNCH",
    "workflow": "WORKFLOW",
    "unscored": "UNSCORED",
}


def _format_evidence(ev: Evidence) -> list[str]:
    eng = f" [eng:{int(ev.engagement)}]" if ev.engagement else ""
    date = f" ({ev.published_at})" if ev.published_at else ""
    phrase = f" — matched “{ev.matched_phrase}”" if ev.matched_phrase else ""
    lines = [
        f"  - **{_SIGNAL_LABEL.get(ev.matched_signal, ev.matched_signal)}**{phrase}",
        f"    [{ev.source}{eng}{date}] {ev.title}",
        f"    {ev.url}",
    ]
    if ev.excerpt:
        lines.append(f"    > {ev.excerpt}")
    return lines


def render_ideas(report: schema.Report, ideas: Iterable[Idea]) -> str:
    """Render an opportunity-extraction brief for Claude Code synthesis.

    The structure is deliberate: the LLM consumes this as evidence and is
    instructed to produce ranked, evidence-cited app-idea proposals. Do not
    inline synthesis here — the Python side stays deterministic.
    """
    ideas = list(ideas)
    lines: list[str] = [
        f"# last30days IDEAS · {report.topic}",
        "",
        f"- Date range: {report.range_from} to {report.range_to}",
        f"- Generated: {report.generated_at}",
        f"- Candidates classified: {len(report.ranked_candidates)}",
        f"- Ideas surfaced (top {len(ideas)}): {len(ideas)}",
        "",
        "## SYNTHESIS INSTRUCTIONS (Claude Code, read carefully)",
        "",
        "You are receiving raw classified opportunity evidence from the",
        "last30days engine. Your job is to produce a ranked list of",
        "**buildable app ideas** with the following rules:",
        "",
        "1. Output 3-7 distinct app ideas, ordered by combined score.",
        "2. Each idea must cite at least one piece of evidence by URL from",
        "   this brief. No idea without a cited source.",
        "3. For each idea, name the unmet need in one sentence, then the",
        "   proposed app in one sentence, then the evidence (bulleted).",
        "4. Flag any idea where you can already name 2+ existing competitors",
        "   — downrank it and say so explicitly. We do NOT want to surface",
        "   ideas that are already crowded markets.",
        "5. Prefer PAIN + WILL-PAY combinations. A pain point with no",
        "   willingness-to-pay signal is interesting; a pain point with",
        "   WILL-PAY is investable.",
        "6. LAUNCH-only signals (someone already shipped this) are useful",
        "   for *adjacency* ideas — \"X exists, but nobody has done Y for",
        "   Z\". Frame them that way, not as \"build X\".",
        "7. Do not invent evidence. If a candidate has no excerpt, say so.",
        "8. End with a one-line honest assessment: how strong is this",
        "   batch, and what topic queries should the user run next to",
        "   sharpen the picture?",
        "",
        "## CLASSIFIED OPPORTUNITIES",
        "",
    ]

    if not ideas:
        lines.extend([
            "_No candidates matched any opportunity signal._",
            "",
            "This usually means the topic was too broad or the engine",
            "did not surface idea-relevant communities. Suggest the user",
            "re-run with a narrower topic or a community-seeded query",
            "(e.g. add `--subreddits r/SideProject,r/microsaas`).",
        ])
        return "\n".join(lines) + "\n"

    for idx, idea in enumerate(ideas, start=1):
        signals = ", ".join(_SIGNAL_LABEL.get(s, s) for s in idea.signal_types)
        lines.extend([
            f"### {idx}. {idea.title}",
            "",
            f"- Signals: {signals}",
            f"- Score: pipeline={idea.pipeline_score:.2f} + boost={idea.heuristic_boost:.2f} = **{idea.total_score:.2f}**",
            f"- Sources: {', '.join(idea.sources) or 'unknown'}",
            "- Evidence:",
        ])
        if idea.evidence:
            for ev in idea.evidence:
                lines.extend(_format_evidence(ev))
        else:
            lines.append("  - _(no signal-matching excerpt; included for raw rank)_")
        lines.append("")

    return "\n".join(lines) + "\n"
