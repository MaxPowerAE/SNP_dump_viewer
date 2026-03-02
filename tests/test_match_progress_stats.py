from pathlib import Path

from scripts.match_progress_stats import build_report


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
    assert "Проверено SNP" in report
    assert "Найдено совпадений" in report
    assert "Bad" in report
    assert "2 (50.0%)" in report
    assert "С risk-аллелем" in report
    assert "Топ-5 trait" in report
    assert "Cardio" in report
    assert "Sleep" in report
