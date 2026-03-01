from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass
class SNPEntry:
    rsid: str
    content: str
    scraped_at: str | None
    attribution: str | None


def split_wiki_sections(content: str) -> list[tuple[str, str]]:
    if not content.strip():
        return [("Описание", "Нет содержимого в поле content.")]

    heading_pattern = re.compile(r"^==\s*(.+?)\s*==\s*$", re.MULTILINE)
    matches = list(heading_pattern.finditer(content))

    if not matches:
        return [("Описание", content.strip())]

    sections: list[tuple[str, str]] = []
    first_start = matches[0].start()
    prefix = content[:first_start].strip()
    if prefix:
        sections.append(("Кратко", prefix))

    for i, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        body = content[start:end].strip()
        if body:
            sections.append((title, body))

    return sections or [("Описание", content.strip())]


def extract_wikilinks(text: str) -> list[str]:
    links = re.findall(r"\[\[(.+?)\]\]", text)
    cleaned: list[str] = []
    seen: set[str] = set()
    for link in links:
        normalized = link.split("|", maxsplit=1)[0].strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            cleaned.append(normalized)
    return cleaned


def format_content_for_markdown(text: str) -> str:
    text = _format_templates(text)
    text = re.sub(r"'''(.*?)'''", r"**\1**", text)
    text = re.sub(r"''(.*?)''", r"*\1*", text)

    def repl_link(match: re.Match[str]) -> str:
        inner = match.group(1)
        if "|" in inner:
            target, label = inner.split("|", maxsplit=1)
            return f"[{label.strip()}](https://www.snpedia.com/index.php/{target.strip()})"
        return f"[{inner.strip()}](https://www.snpedia.com/index.php/{inner.strip()})"

    text = re.sub(r"\[\[(.+?)\]\]", repl_link, text)
    text = re.sub(r"^\* ", "- ", text, flags=re.MULTILINE)
    return text


def _format_templates(text: str) -> str:
    parts: list[str] = []
    last_end = 0
    for match in re.finditer(r"\{\{.*?\}\}", text, flags=re.DOTALL):
        plain = text[last_end:match.start()]
        if plain:
            parts.append(plain)
        parts.append(_render_template(match.group(0)))
        last_end = match.end()

    tail = text[last_end:]
    if tail:
        parts.append(tail)

    return "\n\n".join(part.strip() for part in parts if part.strip())


def _render_template(template: str) -> str:
    body = template.strip()[2:-2].strip()
    if not body:
        return ""

    tokens = [token.strip() for token in body.split("|") if token.strip()]
    if not tokens:
        return ""

    name = tokens[0]
    key_values: list[tuple[str, str]] = []
    positional: list[str] = []
    for token in tokens[1:]:
        if "=" in token:
            key, value = token.split("=", maxsplit=1)
            key_values.append((key.strip(), value.strip()))
        else:
            positional.append(token)

    lower_name = name.lower()
    if lower_name == "разнообразие популяции":
        return _render_population_template(name, key_values, positional)
    if lower_name == "on chip":
        values = ", ".join(positional)
        return f"### {name}\n- {values}" if values else f"### {name}"

    lines = [f"### {name}"]
    if key_values:
        lines.extend(["| Поле | Значение |", "| --- | --- |"])
        for key, value in key_values:
            lines.append(f"| {key} | {value} |")
    if positional:
        lines.append("- " + "\n- ".join(positional))
    return "\n".join(lines)


def _render_population_template(
    name: str,
    key_values: list[tuple[str, str]],
    positional: list[str],
) -> str:
    revision_fields = [(key, value) for key, value in key_values if key.lower() == "hapmaprevision"]
    genotype_fields = [(key, value) for key, value in key_values if key.lower().startswith("geno")]

    headers = [value for _, value in sorted(genotype_fields, key=lambda item: item[0])]
    if len(headers) < 3:
        headers = ["geno1", "geno2", "geno3"]

    rows: list[tuple[str, str, str, str]] = []
    for i in range(0, len(positional), 4):
        chunk = positional[i : i + 4]
        if len(chunk) == 4:
            rows.append((chunk[0], chunk[1], chunk[2], chunk[3]))

    lines = [f"### {name}"]
    if rows:
        lines.extend(
            [
                f"| Популяция | {headers[0]} | {headers[1]} | {headers[2]} |",
                "| --- | --- | --- | --- |",
            ]
        )
        for pop, geno1, geno2, geno3 in rows:
            lines.append(f"| {pop} | {geno1} | {geno2} | {geno3} |")

    for key, value in revision_fields:
        lines.append(f"- {key}: {value}")
    return "\n".join(lines)


def fetch_snp_entry(db_path: Path, rsid: str) -> SNPEntry | None:
    query = """
        SELECT rsid, content, scraped_at, attribution
        FROM snps
        WHERE LOWER(rsid) = LOWER(?)
        LIMIT 1
    """
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(query, (rsid.strip(),)).fetchone()

    if row is None:
        return None

    return SNPEntry(rsid=row[0], content=row[1] or "", scraped_at=row[2], attribution=row[3])


def list_similar_rsids(db_path: Path, pattern: str, limit: int = 20) -> list[str]:
    if not pattern:
        return []

    like_pattern = f"%{pattern.lower()}%"
    query = """
        SELECT rsid FROM snps
        WHERE LOWER(rsid) LIKE ?
        ORDER BY rsid
        LIMIT ?
    """
    with sqlite3.connect(db_path) as connection:
        rows: Iterable[tuple[str]] = connection.execute(query, (like_pattern, limit)).fetchall()
    return [row[0] for row in rows]
