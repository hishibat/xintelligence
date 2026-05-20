"""End-to-end test: run_daily produces all expected artifacts."""
from pathlib import Path

from scripts.run_daily import main as run_daily_main


def test_run_daily_mock_e2e(tmp_path: Path):
    out = tmp_path / "outputs"
    rc = run_daily_main([
        "--provider", "mock",
        "--llm-provider", "mock",
        "--time-range", "24h",
        "--topic", "all",
        "--output-dir", str(out),
        "--date", "2026-05-20",
    ])
    assert rc == 0

    daily_dir = out / "daily_reports" / "2026-05-20"
    assert (daily_dir / "report.md").exists()
    assert (daily_dir / "run_manifest.json").exists()
    assert (out / "csv" / "2026-05-20.csv").exists()
    assert (out / "excel" / "2026-05-20_x_intelligence_report.xlsx").exists()
    draft_dir = out / "content_drafts" / "2026-05-20"
    assert any(draft_dir.glob("*.md"))
    video_dir = out / "video_prompts" / "2026-05-20"
    assert any(video_dir.glob("*.md"))
    review_dir = out / "review_queue" / "2026-05-20"
    assert (review_dir / "drafts_to_review.md").exists()
    assert (review_dir / "approved").is_dir()
    assert (review_dir / "rejected").is_dir()
    assert (review_dir / "needs_fact_check").is_dir()
