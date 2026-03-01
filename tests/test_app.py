from pathlib import Path

from core import (
    build_match_report,
    classify_interpretation,
    convert_genotype_for_orientation,
    detect_dump_orientation,
    extract_wikilinks,
    format_content_for_markdown,
    parse_23andme_file,
    scan_snps_with_progress,
    split_wiki_sections,
)


def test_split_wiki_sections_with_headings() -> None:
    text = "Intro\n== Summary ==\nBody\n== References ==\n* [[ApoE]]"
    sections = split_wiki_sections(text)
    assert sections[0] == ("Кратко", "Intro")
    assert sections[1] == ("Summary", "Body")
    assert sections[2][0] == "References"


def test_extract_wikilinks_uniqueness_and_pipes() -> None:
    text = "[[ApoE]] [[ApoE|ApoE gene]] [[rs7412]]"
    assert extract_wikilinks(text) == ["ApoE", "rs7412"]


def test_format_content_for_markdown() -> None:
    text = "'''Bold''' and ''italic'' with [[ApoE|ApoE gene]]"
    formatted = format_content_for_markdown(text)
    assert "**Bold**" in formatted
    assert "*italic*" in formatted
    assert "[ApoE gene](https://www.snpedia.com/index.php/ApoE)" in formatted


def test_format_content_for_markdown_with_rsnum_template() -> None:
    text = "{{Rsnum |rsid=983332 |Chromosome=1 |position=87666697}}"
    formatted = format_content_for_markdown(text)
    assert "### Rsnum" in formatted
    assert "| rsid | 983332 |" in formatted
    assert "| position | 87666697 |" in formatted


def test_format_content_for_markdown_with_population_template() -> None:
    text = (
        "{{ разнообразие популяции "
        "| geno1=(A;A) | geno2=(A;C) | geno3=(C;C) "
        "| CEU | 4.4 | 31.0 | 64.6 "
        "| YRI | 13.6 | 32.0 | 54.4 "
        "| HapMapRevision=28 }}"
    )
    formatted = format_content_for_markdown(text)
    assert "### разнообразие популяции" in formatted
    assert "| Популяция | (A;A) | (A;C) | (C;C) |" in formatted
    assert "| CEU | 4.4 | 31.0 | 64.6 |" in formatted
    assert "- HapMapRevision: 28" in formatted


def test_format_content_for_markdown_with_english_population_template() -> None:
    text = (
        "{{ population diversity "
        "| geno1=(A;A) | geno2=(A;G) | geno3=(G;G) "
        "| CEU | 61.1 | 37.2 | 1.8 "
        "| HapMapRevision=28 }}"
    )
    formatted = format_content_for_markdown(text)
    assert "### population diversity" in formatted
    assert "| Популяция | (A;A) | (A;G) | (G;G) |" in formatted
    assert "| CEU | 61.1 | 37.2 | 1.8 |" in formatted


def test_format_content_for_markdown_with_adjacent_templates() -> None:
    text = "{{Rsnum |rsid=9804128}}{{ population diversity | CEU | 1 | 2 | 3 }}"
    formatted = format_content_for_markdown(text)
    assert "### Rsnum" in formatted
    assert "### population diversity" in formatted


def test_format_content_for_markdown_with_on_chip_template() -> None:
    text = "{{on chip | 23andMe v1}}"
    formatted = format_content_for_markdown(text)
    assert "### on chip" in formatted
    assert "- 23andMe v1" in formatted


def test_parse_23andme_file() -> None:
    text = "# comment\nrs7412\t19\t44908684\tCT\nrs429358\t19\t44908822\tCC\n"
    parsed = parse_23andme_file(text)
    assert len(parsed) == 2
    assert parsed[0].rsid == "rs7412"
    assert parsed[0].genotype_plus == "CT"


def test_detect_orientation_and_convert_genotype() -> None:
    content = "{{Rsnum|StabilizedOrientation=minus}}"
    assert detect_dump_orientation(content) == "minus"
    assert convert_genotype_for_orientation("AG", "minus") == "TC"


def test_classify_interpretation() -> None:
    assert classify_interpretation("Protective effect") == "good"
    assert classify_interpretation("Higher risk for disease") == "bad"


def test_scan_snps_with_progress(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    progress_path = tmp_path / "progress.json"

    import sqlite3

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE snps (rsid TEXT, content TEXT, scraped_at TEXT, attribution TEXT)"
        )
        connection.execute(
            "INSERT INTO snps (rsid, content, scraped_at, attribution) VALUES (?, ?, ?, ?)",
            (
                "rs7412",
                "{{Rsnum|StabilizedOrientation=plus}}\n==CT==\nProtective association found.",
                "2026-01-01",
                "test",
            ),
        )
        connection.commit()

    snp_lines = "rs7412\t19\t44908684\tCT\nrs0000\t1\t1\tAA"
    snps = parse_23andme_file(snp_lines)

    matches, checked, stats = scan_snps_with_progress(db_path, snps, progress_path, save_interval=1)

    assert checked == 2
    assert len(matches) == 1
    assert stats["found"] == 1
    assert stats["good"] == 1
    report = build_match_report(matches)
    assert "rs7412" in report
    assert "Protective association found." in report
