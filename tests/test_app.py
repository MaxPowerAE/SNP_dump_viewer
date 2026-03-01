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
