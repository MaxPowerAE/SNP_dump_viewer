from core import extract_wikilinks, format_content_for_markdown, split_wiki_sections


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


def test_format_content_for_markdown_with_on_chip_template() -> None:
    text = "{{on chip | 23andMe v1}}"
    formatted = format_content_for_markdown(text)
    assert "### on chip" in formatted
    assert "- 23andMe v1" in formatted
