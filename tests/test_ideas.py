"""Tests for the --emit=ideas evidence brief renderer."""
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
    published_at: str | None = "2026-04-15",
) -> schema.Candidate:
    item = schema.SourceItem(
        item_id=f"{candidate_id}-i",
        source=source,
        title=title,
        body=body,
        url=url,
        container=container,
        engagement=engagement or {},
        published_at=published_at,
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


class TestSelectCandidates(unittest.TestCase):
    def test_returns_top_n_ordered_by_final_score(self):
        cands = [
            _candidate(f"c{i}", f"Candidate {i}", final_score=0.1 * i)
            for i in range(10)
        ]
        # Shuffle by passing in arbitrary order — selection should re-sort.
        report = _report(list(reversed(cands)))
        result = ideas.select_candidates(report, top_n=3)
        self.assertEqual(["c9", "c8", "c7"], [v.candidate_id for v in result])

    def test_view_carries_source_container_engagement(self):
        cand = _candidate(
            "c1",
            "I keep stitching Zapier and a spreadsheet",
            body="Three tools for one workflow. Pay $40/mo and still broken.",
            container="r/SideProject",
            engagement={"upvotes": 250, "comments": 30},
        )
        result = ideas.select_candidates(_report([cand]))
        self.assertEqual(1, len(result))
        view = result[0]
        self.assertEqual("reddit", view.source)
        self.assertEqual("r/SideProject", view.container)
        self.assertEqual(280, view.engagement)
        self.assertIn("Three tools", view.excerpt)
        self.assertEqual("2026-04-15", view.published_at)

    def test_excerpt_truncates_long_bodies(self):
        long_body = "word " * 200
        cand = _candidate("c1", "Title", body=long_body)
        view = ideas.select_candidates(_report([cand]))[0]
        self.assertLessEqual(len(view.excerpt), ideas.EXCERPT_WIDTH + 1)
        self.assertTrue(view.excerpt.endswith("…"))

    def test_no_classification_filtering(self):
        """Every candidate survives selection — classification is downstream."""
        cands = [
            _candidate("boring", "Generic news headline about AI"),
            _candidate("painful", "I wish there was an app for X"),
        ]
        result = ideas.select_candidates(_report(cands))
        self.assertEqual({"boring", "painful"}, {v.candidate_id for v in result})


class TestRenderBrief(unittest.TestCase):
    def test_brief_includes_synthesis_instructions_and_evidence(self):
        cand = _candidate(
            "c1",
            "I'd pay $20/month for a calendar that knows my prep style",
            body="Honestly, I'd pay for this. Currently using three apps.",
            engagement={"upvotes": 250},
        )
        report = _report([cand])
        out = ideas.render_brief(report, ideas.select_candidates(report))

        self.assertIn("# last30days BRIEF · indie SaaS opportunities", out)
        self.assertIn("SYNTHESIS INSTRUCTIONS", out)
        # Classification taxonomy is described in the prompt block.
        self.assertIn("PAIN", out)
        self.assertIn("WILL-PAY", out)
        self.assertIn("LAUNCH", out)
        self.assertIn("WORKFLOW", out)
        # Candidate metadata is present.
        self.assertIn("https://example.com/post", out)
        self.assertIn("eng:250", out)
        self.assertIn("Honestly, I'd pay for this", out)

    def test_brief_handles_empty_candidate_list(self):
        report = _report([])
        out = ideas.render_brief(report, [])
        self.assertIn("No candidates surfaced", out)
        self.assertIn("--subreddits", out)

    def test_brief_omits_source_health_when_no_errors(self):
        cand = _candidate("c1", "Some candidate")
        report = _report([cand])
        out = ideas.render_brief(report, ideas.select_candidates(report))
        self.assertNotIn("## SOURCE HEALTH", out)
        self.assertIn("Healthy sources", out)
        self.assertIn("reddit", out)

    def test_brief_emits_source_health_section_when_errors_present(self):
        cand = _candidate("c1", "Some candidate")
        report = _report([cand])
        report.errors_by_source["x"] = "401 unauthorized — cookies expired"
        report.errors_by_source["tiktok"] = "rate limited"
        out = ideas.render_brief(report, ideas.select_candidates(report))
        self.assertIn("## SOURCE HEALTH", out)
        self.assertIn("**x**: 401 unauthorized", out)
        self.assertIn("**tiktok**: rate limited", out)
        # Synthesis instruction #8 references the SOURCE HEALTH block.
        self.assertIn("SOURCE HEALTH section appears above", out)

    def test_brief_truncates_long_error_messages(self):
        cand = _candidate("c1", "Some candidate")
        report = _report([cand])
        report.errors_by_source["reddit"] = "x" * 500
        out = ideas.render_brief(report, ideas.select_candidates(report))
        self.assertIn("…", out)
        self.assertNotIn("x" * 250, out)

    def test_brief_renders_multiple_candidates_in_score_order(self):
        cands = [
            _candidate("low", "Lower-ranked", final_score=0.3),
            _candidate("high", "Higher-ranked", final_score=0.9),
        ]
        report = _report(cands)
        out = ideas.render_brief(report, ideas.select_candidates(report))
        # Higher-scored candidate should appear first under ## CANDIDATES.
        candidates_section = out.split("## CANDIDATES", 1)[1]
        self.assertLess(
            candidates_section.index("Higher-ranked"),
            candidates_section.index("Lower-ranked"),
        )


if __name__ == "__main__":
    unittest.main()
