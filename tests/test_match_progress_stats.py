from pathlib import Path

from scripts.match_progress_stats import _resolve_progress_dir, build_report, write_report


def test_build_report_contains_compact_tables(tmp_path: Path) -> None:
    progress_path = tmp_path / "match_progress_demo.json"
    progress_path.write_text(
        """
{
  "next_index": 10,
  "found": 4,
  "good": 1,
  "bad": 2,
  "matches": [
    {
      "user_genotype_for_dump": "AG",
      "risk_allele": "A",
      "trait": "Cardio"
    },
    {
      "user_genotype_for_dump": "TT",
      "risk_allele": "T",
      "trait": "Cardio"
    },
    {
      "user_genotype_for_dump": "CC",
      "risk_allele": "A",
      "trait": "Sleep"
    },
    {
      "user_genotype_for_dump": "GG",
      "risk_allele": null,
      "trait": ""
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )

    report = build_report(progress_path)

    assert "Краткая статистика" in report
    assert "Поля progress JSON" in report
    assert "next_index" in report
    assert "Проверено SNP" in report
    assert "Найдено совпадений" in report
    assert "Bad" in report
    assert "2 (50.0%)" in report
    assert "С risk-аллелем" in report
    assert "Топ-5 trait" in report
    assert "Cardio" in report
    assert "Sleep" in report
    assert "Детализация совпадений" in report
    assert "[1] BAD" in report
    assert "trait: Cardio" in report
    assert "risk_allele: A" in report
    assert "[4] GOOD" in report


def test_build_report_parses_extra_json_fields(tmp_path: Path) -> None:
    progress_path = tmp_path / "match_progress_extra.json"
    progress_path.write_text(
        """
{
  "next_index": 1,
  "found": 1,
  "good": 1,
  "bad": 0,
  "started_at": "2026-03-01T12:00:00",
  "run_meta": {"source": "test"},
  "matches": [
    {
      "rsid": "rs123",
      "classification": "good",
      "user_genotype_plus": "AG",
      "orientation": "plus",
      "title_interpretation": "Demo title",
      "pubmed_articles": ["111111"],
      "user_genotype_for_dump": "AG",
      "risk_allele": "A",
      "interpretation": "not shown",
      "custom_field": "custom"
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )

    report = build_report(progress_path)

    assert "started_at" in report
    assert 'run_meta' in report
    assert "🔵 rsid: rs123" in report
    assert "🟠 classification: good" in report
    assert "🟦 pubmed_articles: [\"111111\"]" in report
    assert "custom_field: custom" not in report
    assert "interpretation: not shown" not in report


def test_resolve_progress_dir_falls_back_to_repo_root(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "SNP_dump_viewer"
    scripts_dir = project_root / "scripts"
    scripts_dir.mkdir(parents=True)
    (project_root / ".progress").mkdir()

    fake_script = scripts_dir / "match_progress_stats.py"
    fake_script.write_text("# stub", encoding="utf-8")
    monkeypatch.chdir(scripts_dir)
    monkeypatch.setattr("scripts.match_progress_stats.__file__", str(fake_script))

    resolved = _resolve_progress_dir(Path(".progress"))

    assert resolved == project_root / ".progress"


def test_write_report_uses_default_name(tmp_path: Path) -> None:
    progress_path = tmp_path / "match_progress_demo.json"
    progress_path.write_text("{}", encoding="utf-8")

    report_path = write_report(progress_path, "demo")

    assert report_path == tmp_path / "match_progress_demo.report.txt"
    assert report_path.read_text(encoding="utf-8") == "demo"
