from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile

import streamlit as st

from core import (
    SNPEntry,
    extract_wikilinks,
    fetch_snp_entry,
    format_content_for_markdown,
    list_similar_rsids,
    split_wiki_sections,
)


def ensure_sqlite_file(uploaded_file) -> Path:
    suffix = Path(uploaded_file.name).suffix or ".db"
    with NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_file.write(uploaded_file.getvalue())
        temp_path = Path(temp_file.name)
    return temp_path


def render_entry(entry: SNPEntry) -> None:
    st.subheader(entry.rsid)

    metadata_col, links_col = st.columns([2, 1])
    with metadata_col:
        st.markdown("### Метаданные")
        st.write(
            {
                "scraped_at": entry.scraped_at or "—",
                "attribution": entry.attribution or "—",
            }
        )

    links = extract_wikilinks(entry.content)
    with links_col:
        st.markdown("### Ссылки")
        if links:
            for link in links:
                st.markdown(f"- [{link}](https://www.snpedia.com/index.php/{link})")
        else:
            st.caption("В тексте не найдено wiki-ссылок.")

    st.markdown("### Содержимое")
    for title, body in split_wiki_sections(entry.content):
        with st.expander(title, expanded=True):
            st.markdown(format_content_for_markdown(body))


def main() -> None:
    st.set_page_config(page_title="SNP Dump Viewer", page_icon="🧬", layout="wide")

    st.title("🧬 SNP Dump Viewer")
    st.caption(
        "Загрузите локальный SQLite-дамп из SNPedia-Scraper и найдите SNP по rsid "
        "(таблица snps: rsid, content, scraped_at, attribution)."
    )

    uploaded_file = st.file_uploader(
        "Локальный файл дампа (.sqlite/.db)",
        type=["sqlite", "db", "sqlite3"],
        accept_multiple_files=False,
    )

    if uploaded_file is None:
        st.info("Сначала загрузите файл дампа базы данных.")
        return

    db_path = ensure_sqlite_file(uploaded_file)

    rsid = st.text_input("Введите SNP (пример: rs7412)", placeholder="rs7412")
    suggestions = list_similar_rsids(db_path, rsid, limit=15) if rsid else []

    if suggestions:
        st.caption("Похожие SNP в базе:")
        st.write(", ".join(suggestions))

    if not rsid:
        return

    try:
        entry = fetch_snp_entry(db_path, rsid)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Ошибка чтения базы данных: {exc}")
        return

    if entry is None:
        st.warning("SNP не найден. Уточните rsid или выберите из подсказок выше.")
        return

    render_entry(entry)


if __name__ == "__main__":
    main()
