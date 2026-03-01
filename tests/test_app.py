from pathlib import Path

from core import (
    build_interpretation_context,
    build_match_report,
    classify_interpretation,
    extract_risk_allele,
    extract_trait,
    extract_title_interpretation,
    fetch_pubmed_links_for_snp,
    is_bad_homozygous_genotype,
    convert_genotype_for_orientation,
    detect_dump_orientation,
    extract_wikilinks,
    format_content_for_markdown,
    has_risk_allele_match,
    parse_23andme_file,
    scan_snps_with_progress,
    split_wiki_sections,
)
from app import format_live_match_summary, match_warning_marker
from core import MatchResult, SNPEntry


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


def test_extract_title_and_risk_allele() -> None:
    content = "|Title=Main interpretation\n|RiskAllele=G"
    assert extract_title_interpretation(content) == "Main interpretation"
    assert extract_risk_allele(content) == "G"


def test_extract_title_and_risk_allele_without_pipe() -> None:
    content = "Title=Main interpretation\nRiskAllele=A"
    assert extract_title_interpretation(content) == "Main interpretation"
    assert extract_risk_allele(content) == "A"




def test_extract_trait() -> None:
    content = "|Trait=Cardiovascular disease\n|RiskAllele=G"
    assert extract_trait(content) == "Cardiovascular disease"


def test_extract_trait_none() -> None:
    content = "|Trait=None"
    assert extract_trait(content) == ""

def test_build_interpretation_context_for_generic_interpretation() -> None:
    interpretation = "Специфичная интерпретация для генотипа не найдена. Показано общее описание SNP."
    result = build_interpretation_context(interpretation, "Higher risk for disease", "Obesity", "G")
    assert result == "Title: Higher risk for disease\nTrait: Obesity\nRiskAllele: G"


def test_build_interpretation_context_appends_metadata() -> None:
    result = build_interpretation_context("Protective association found.", "Main interpretation", "Longevity", "G")
    assert "Protective association found." in result
    assert "Title: Main interpretation" in result
    assert "Trait: Longevity" in result
    assert "RiskAllele: G" in result




def test_has_risk_allele_match() -> None:
    assert has_risk_allele_match("AG", "G")
    assert not has_risk_allele_match("CT", "A")
    assert not has_risk_allele_match("CT", None)

def test_bad_homozygous_detection() -> None:
    assert is_bad_homozygous_genotype("GG", "G")
    assert not is_bad_homozygous_genotype("AG", "G")


def test_fetch_pubmed_links_for_snp(monkeypatch) -> None:
    class FakeResponse:
        def __init__(self, payload: str) -> None:
            self.payload = payload

        def read(self) -> bytes:
            return self.payload.encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    calls = []

    def fake_urlopen(url: str, timeout: int):
        calls.append(url)
        if "esearch.fcgi" in url:
            return FakeResponse('{"esearchresult": {"idlist": ["123"]}}')
        return FakeResponse('{"result": {"123": {"title": "Study rs7412"}}}')

    monkeypatch.setattr("core.request.urlopen", fake_urlopen)
    links = fetch_pubmed_links_for_snp("rs7412")
    assert links == [("Study rs7412", "https://pubmed.ncbi.nlm.nih.gov/123/")]
    assert len(calls) == 2


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


def test_match_warning_marker_red_for_bad_two_alleles() -> None:
    match = MatchResult(
        rsid="rs1",
        user_genotype_plus="AG",
        user_genotype_for_dump="AG",
        orientation="plus",
        classification="bad",
        interpretation="risk",
        title_interpretation="title",
        trait="trait",
        risk_allele="A",
        is_bad_homozygous=False,
        pubmed_articles=[],
        entry=SNPEntry(rsid="rs1", content="", scraped_at=None, attribution=None),
    )
    assert match_warning_marker(match) == "🔴 !!!"


def test_match_warning_marker_yellow_for_risk_allele_presence() -> None:
    match = MatchResult(
        rsid="rs2",
        user_genotype_plus="AG",
        user_genotype_for_dump="AG",
        orientation="plus",
        classification="neutral",
        interpretation="text",
        title_interpretation="title",
        trait="trait",
        risk_allele="G",
        is_bad_homozygous=False,
        pubmed_articles=[],
        entry=SNPEntry(rsid="rs2", content="", scraped_at=None, attribution=None),
    )
    assert match_warning_marker(match) == "🟡 !"


def test_format_live_match_summary_contains_requested_fields() -> None:
    match = MatchResult(
        rsid="rs3",
        user_genotype_plus="CT",
        user_genotype_for_dump="GA",
        orientation="minus",
        classification="neutral",
        interpretation="Some interpretation",
        title_interpretation="Some title",
        trait="Some trait",
        risk_allele="A",
        is_bad_homozygous=False,
        pubmed_articles=[],
        entry=SNPEntry(rsid="rs3", content="", scraped_at=None, attribution=None),
    )

    summary = format_live_match_summary(match)
    assert "rs3" in summary
    assert "CT" in summary
    assert "GA" in summary
    assert "minus" in summary
    assert "neutral" in summary
    assert "A" in summary
    assert "Some trait" in summary
    assert "Some interpretation" in summary
    assert "Some title" in summary


def test_scan_snps_with_progress_counts_bad_only_on_risk_allele_match(tmp_path: Path) -> None:
    db_path = tmp_path / "test_bad.db"
    progress_path = tmp_path / "progress_bad.json"

    import sqlite3

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE snps (rsid TEXT, content TEXT, scraped_at TEXT, attribution TEXT)"
        )
        connection.execute(
            "INSERT INTO snps (rsid, content, scraped_at, attribution) VALUES (?, ?, ?, ?)",
            (
                "rsbad",
                "|Title=Higher risk for condition\n|RiskAllele=T\n==AA==\nHigher risk for condition",
                "2026-01-01",
                "test",
            ),
        )
        connection.commit()

    snps = parse_23andme_file("rsbad\t1\t1\tAA")

    _, _, stats = scan_snps_with_progress(db_path, snps, progress_path, save_interval=1)

    assert stats["found"] == 1
    assert stats["bad"] == 0

