from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile

import streamlit as st

from core import (
    MatchResult,
    SNPEntry,
    build_match_report,
    extract_wikilinks,
    fetch_snp_entry,
    format_content_for_markdown,
    hash_upload_identity,
    list_similar_rsids,
    parse_23andme_file,
    scan_snps_with_progress,
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


def render_matches(matches: list[MatchResult]) -> None:
    st.markdown("## Совпадения из файла 23andMe")
    for match in matches:
        icon = "🟢" if match.classification == "good" else "🔴" if match.classification == "bad" else "⚪"
        with st.expander(f"{icon} {match.rsid}: {match.user_genotype_plus} ({match.orientation})", expanded=False):
            st.markdown("### Поля совпадения")
            base_col, risk_col = st.columns(2)
            with base_col:
                st.write(
                    {
                        "генотип_23andme_plus": match.user_genotype_plus,
                        "генотип_для_дампа": match.user_genotype_for_dump,
                        "ориентация_дампа": match.orientation,
                        "классификация": match.classification,
                    }
                )
            with risk_col:
                st.write(
                    {
                        "RiskAllele": match.risk_allele or "—",
                        "плохая_гомозигота": "ДА" if match.is_bad_homozygous else "нет",
                    }
                )

            if match.is_bad_homozygous:
                st.error("⚠️ Обнаружена плохая гомозигота по RiskAllele.")

            if match.title_interpretation:
                st.markdown("### Интерпретация из поля Title")
                st.markdown(format_content_for_markdown(match.title_interpretation))

            st.markdown("### Интерпретация")
            st.markdown(format_content_for_markdown(match.interpretation))

            st.markdown("### PubMed")
            if match.pubmed_articles:
                for title, url in match.pubmed_articles:
                    st.markdown(f"- [{title}]({url})")
            else:
                st.caption("По этому SNP статьи в PubMed не найдены.")

            st.markdown("### Полная карточка SNP")
            render_entry(match.entry)


def main() -> None:
    st.set_page_config(page_title="SNP Dump Viewer", page_icon="🧬", layout="wide")

    st.title("🧬 SNP Dump Viewer")
    st.caption(
        "Загрузите локальный SQLite-дамп из SNPedia-Scraper и найдите SNP по rsid "
        "(таблица snps: rsid, content, scraped_at, attribution)."
    )

    st.markdown("## Загрузка файлов")
    db_col, snp_col = st.columns(2)

    with db_col:
        uploaded_file = st.file_uploader(
            "📁 Загрузить БД (.sqlite/.db)",
            type=["sqlite", "db", "sqlite3"],
            accept_multiple_files=False,
        )

    with snp_col:
        snp_file = st.file_uploader(
            "📄 Загрузить файл 23andMe (.txt)",
            type=["txt"],
            accept_multiple_files=False,
            key="snp-file",
        )

    if uploaded_file is None:
        st.info("Сначала загрузите файл дампа базы данных.")
        return

    db_path = ensure_sqlite_file(uploaded_file)

    st.markdown("---")
    st.markdown("## Поиск одного SNP")
    rsid = st.text_input("Введите SNP (пример: rs7412)", placeholder="rs7412")
    suggestions = list_similar_rsids(db_path, rsid, limit=15) if rsid else []

    if suggestions:
        st.caption("Похожие SNP в базе:")
        st.write(", ".join(suggestions))

    if rsid:
        try:
            entry = fetch_snp_entry(db_path, rsid)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Ошибка чтения базы данных: {exc}")
            return

        if entry is None:
            st.warning("SNP не найден. Уточните rsid или выберите из подсказок выше.")
        else:
            render_entry(entry)

    st.markdown("---")
    st.markdown("## Массовое сопоставление с файлом 23andMe V5")

    if snp_file is None:
        st.info("Чтобы запустить массовое сопоставление, загрузите файл 23andMe в блоке выше.")
        return

    snp_content = snp_file.getvalue().decode("utf-8", errors="ignore")
    user_snps = parse_23andme_file(snp_content)
    if not user_snps:
        st.warning("Не удалось прочитать SNP из файла 23andMe.")
        return

    progress_dir = Path(".progress")
    progress_dir.mkdir(exist_ok=True)
    progress_id = hash_upload_identity(uploaded_file.name, snp_file.name)
    progress_path = progress_dir / f"match_progress_{progress_id}.json"

    if st.button("Запустить/продолжить поиск совпадений", type="primary"):
        with st.spinner("Идет поиск совпадений..."):
            matches, total_checked, stats = scan_snps_with_progress(
                db_path=db_path,
                snps=user_snps,
                progress_path=progress_path,
                save_interval=10,
            )

        completion = 100.0 * (total_checked / len(user_snps)) if user_snps else 0.0
        st.success("Сканирование завершено или продолжено с сохраненной точки.")

        stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
        stat_col1.metric("Проверено", f"{total_checked}/{len(user_snps)}")
        stat_col2.metric("% выполнения", f"{completion:.1f}%")
        stat_col3.metric("Найдено совпадений", stats["found"])
        stat_col4.metric("Хорошие / Плохие", f"{stats['good']} / {stats['bad']}")

        report = build_match_report(matches)
        st.download_button(
            label="Скачать отчет",
            data=report.encode("utf-8"),
            file_name="snp_match_report.txt",
            mime="text/plain",
        )

        if matches:
            render_matches(matches)
        else:
            st.info("Совпадения в дампе не найдены.")


if __name__ == "__main__":
    main()
