"""Tests for the --emit=ideas opportunity extractor."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "last30days" / "scripts"))

from lib import ideas, schema


def _candidate(
    candidate_id: str,
    title: str,
    body: str = "",
    *,
    source: str = "reddit",
    container: str | None = None,
    final_score: float = 0.5,
    engagement: dict[str, float | int] | None = None,
    url: str = "https://example.com/post",
) -> schema.Candidate:
    item = schema.SourceItem(
        item_id=f"{candidate_id}-i",
        source=source,
        title=title,
        body=body,
        url=url,
        container=container,
        engagement=engagement or {},
        published_at="2026-04-15",
    )
    return schema.Candidate(
        candidate_id=candidate_id,
        item_id=item.item_id,
        source=source,
        title=title,
        url=url,
        snippet=body[:120],
        subquery_labels=["primary"],
        native_ranks={f"primary:{source}": 1},
        local_relevance=0.7,
        freshness=80,
        engagement=sum(engagement.values()) if engagement else None,
        source_quality=1.0,
        rrf_score=0.02,
        rerank_score=final_score,
        final_score=final_score,
        sources=[source],
        source_items=[item],
    )


def _report(candidates: list[schema.Candidate]) -> schema.Report:
    return schema.Report(
        topic="indie SaaS opportunities",
        range_from="2026-04-01",
        range_to="2026-04-30",
        generated_at="2026-04-30T00:00:00+00:00",
        provider_runtime=schema.ProviderRuntime(
            reasoning_provider="claude",
            planner_model="claude-sonnet-4-6",
            rerank_model="claude-sonnet-4-6",
        ),
        query_plan=schema.QueryPlan(
            intent="opportunity_mining",
            freshness_mode="rolling_30d",
            cluster_mode="entity",
            raw_topic="indie SaaS opportunities",
            subqueries=[
                schema.SubQuery(
                    label="primary",
                    search_query="indie SaaS opportunities",
                    ranking_query="What unmet needs are indie devs voicing?",
                    sources=["reddit"],
                )
            ],
            source_weights={"reddit": 1.0},
        ),
        clusters=[
            schema.Cluster(
                cluster_id=f"cluster-{c.candidate_id}",
                title=c.title,
                candidate_ids=[c.candidate_id],
                representative_ids=[c.candidate_id],
                sources=c.sources,
                score=c.final_score * 100,
            )
            for c in candidates
        ],
        ranked_candidates=candidates,
        items_by_source={
            c.source: [c.source_items[0]] for c in candidates
        },
        errors_by_source={},
    )


class TestSignalClassification(unittest.TestCase):
    def test_pain_point_phrase_is_classified(self):
        text = "I wish there was an app that batches my email replies for me."
        signals = ideas._classify_text(text)
        self.assertIn("pain_point", signals)

    def test_launch_phrase_is_classified(self):
        text = "Show HN: I built a tiny tool that converts CSV to SQL."
        signals = ideas._classify_text(text)
        self.assertIn("launch", signals)

    def test_wtp_phrase_is_classified(self):
        text = "Honestly I'd pay $30/month for this. Take my money."
        signals = ideas._classify_text(text)
        self.assertIn("wtp", signals)

    def test_workflow_phrase_is_classified(self):
        text = "I currently stitch together Zapier and a spreadsheet hack."
        signals = ideas._classify_text(text)
        self.assertIn("workflow", signals)

    def test_unrelated_text_yields_no_signal(self):
        self.assertEqual({}, ideas._classify_text("the weather is nice today"))


class TestExtractIdeas(unittest.TestCase):
    def test_pain_point_candidate_is_surfaced(self):
        cand = _candidate(
            "c1",
            "I wish there was an app that handled meeting prep",
            body="Currently I'm doing this manually with a spreadsheet hack.",
            engagement={"upvotes": 423},
        )
        report = _report([cand])
        result = ideas.extract_ideas(report)
        self.assertEqual(1, len(result))
        self.assertIn("pain_point", result[0].signal_types)
        # workflow keyword in body should also fire
        self.assertIn("workflow", result[0].signal_types)
        self.assertGreater(result[0].heuristic_boost, 0.0)

    def test_wtp_signal_outranks_unscored_candidate(self):
        cold = _candidate("cold", "Generic news headline about AI", final_score=0.9)
        warm = _candidate(
            "warm",
            "I'd pay $50/month for a tool that drafts grant applications",
            final_score=0.3,
        )
        report = _report([cold, warm])
        result = ideas.extract_ideas(report)
        # cold candidate has no signal → filtered (min_signals=1 default)
        self.assertEqual(["warm"], [i.candidate_id for i in result])
        self.assertIn("wtp", result[0].signal_types)

    def test_launch_container_promotes_candidate_even_without_phrase(self):
        cand = _candidate(
            "c1",
            "Built a tool for indie devs to track MRR",
            body="Spent 3 weeks on this, sharing in case it's useful.",
            container="r/SideProject",
            final_score=0.4,
        )
        report = _report([cand])
        result = ideas.extract_ideas(report)
        self.assertEqual(1, len(result))
        self.assertIn("launch", result[0].signal_types)

    def test_no_matches_falls_back_to_top_candidates(self):
        cand = _candidate("c1", "Boring news headline", body="Nothing actionable here.")
        report = _report([cand])
        result = ideas.extract_ideas(report)
        self.assertEqual(1, len(result))
        self.assertEqual(["unscored"], result[0].signal_types)

    def test_top_n_caps_results(self):
        cands = [
            _candidate(f"c{i}", f"I'd pay for tool {i}", final_score=0.5 + i / 100)
            for i in range(15)
        ]
        report = _report(cands)
        result = ideas.extract_ideas(report, top_n=5)
        self.assertEqual(5, len(result))
        # ranked desc by total_score
        scores = [i.total_score for i in result]
        self.assertEqual(scores, sorted(scores, reverse=True))


class TestRenderIdeas(unittest.TestCase):
    def test_render_includes_synthesis_instructions_and_evidence(self):
        cand = _candidate(
            "c1",
            "I'd pay $20/month for a calendar that knows my prep style",
            body="Honestly, I'd pay for this. Currently using three apps.",
            engagement={"upvotes": 250},
        )
        report = _report([cand])
        result = ideas.extract_ideas(report)
        out = ideas.render_ideas(report, result)

        self.assertIn("# last30days IDEAS · indie SaaS opportunities", out)
        self.assertIn("SYNTHESIS INSTRUCTIONS", out)
        self.assertIn("WILL-PAY", out)
        self.assertIn("https://example.com/post", out)
        self.assertIn("eng:250", out)

    def test_render_handles_empty_ideas_list(self):
        report = _report([])
        out = ideas.render_ideas(report, [])
        self.assertIn("No candidates matched", out)
        self.assertIn("--subreddits", out)

    def test_render_omits_source_health_when_no_errors(self):
        cand = _candidate("c1", "I'd pay for a thing")
        report = _report([cand])
        out = ideas.render_ideas(report, ideas.extract_ideas(report))
        # Section header absent; the conditional reference inside the
        # synthesis instructions ("If a SOURCE HEALTH section…") is fine.
        self.assertNotIn("## SOURCE HEALTH", out)
        self.assertIn("Healthy sources", out)
        self.assertIn("reddit", out)

    def test_render_emits_source_health_section_when_errors_present(self):
        cand = _candidate("c1", "I'd pay for a thing")
        report = _report([cand])
        report.errors_by_source["x"] = "401 unauthorized — cookies expired"
        report.errors_by_source["tiktok"] = "rate limited"
        out = ideas.render_ideas(report, ideas.extract_ideas(report))
        self.assertIn("## SOURCE HEALTH", out)
        self.assertIn("**x**: 401 unauthorized", out)
        self.assertIn("**tiktok**: rate limited", out)
        # Synthesis instruction #8 references the SOURCE HEALTH block.
        self.assertIn("SOURCE HEALTH section appears above", out)

    def test_render_truncates_long_error_messages(self):
        cand = _candidate("c1", "I'd pay for a thing")
        report = _report([cand])
        report.errors_by_source["reddit"] = "x" * 500
        out = ideas.render_ideas(report, ideas.extract_ideas(report))
        # Truncated to 200 chars + ellipsis.
        self.assertIn("…", out)
        self.assertNotIn("x" * 250, out)


if __name__ == "__main__":
    unittest.main()
