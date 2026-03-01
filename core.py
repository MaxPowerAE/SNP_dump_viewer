from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from urllib import parse, request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


@dataclass
class SNPEntry:
    rsid: str
    content: str
    scraped_at: str | None
    attribution: str | None


@dataclass
class UserSNP:
    rsid: str
    genotype_plus: str


@dataclass
class MatchResult:
    rsid: str
    user_genotype_plus: str
    user_genotype_for_dump: str
    orientation: str
    classification: str
    interpretation: str
    title_interpretation: str
    trait: str
    risk_allele: str | None
    is_bad_homozygous: bool
    pubmed_articles: list[tuple[str, str]]
    entry: SNPEntry


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
    if lower_name in {"разнообразие популяции", "population diversity"}:
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


def parse_23andme_file(content: str) -> list[UserSNP]:
    snps: list[UserSNP] = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        rsid, genotype = parts[0], parts[3].upper()
        if rsid.lower().startswith("rs") and _is_valid_genotype(genotype):
            snps.append(UserSNP(rsid=rsid, genotype_plus=genotype))
    return snps


def _is_valid_genotype(genotype: str) -> bool:
    if len(genotype) not in {1, 2}:
        return False
    return all(base in {"A", "C", "G", "T", "-"} for base in genotype)


def detect_dump_orientation(content: str) -> str:
    patterns = [
        r"stabilizedorientation\s*=\s*(plus|minus)",
        r"orientation\s*=\s*(plus|minus)",
        r"orientation\s*[:=]\s*(plus|minus)",
    ]
    lowered = content.lower()
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            return match.group(1)
    return "plus"


def convert_genotype_for_orientation(genotype_plus: str, orientation: str) -> str:
    if orientation != "minus":
        return genotype_plus

    complement = {"A": "T", "T": "A", "C": "G", "G": "C", "-": "-"}
    converted = "".join(complement.get(base, base) for base in genotype_plus)
    return converted


def extract_genotype_interpretation(content: str, genotype: str) -> str:
    section_pattern = re.compile(
        rf"^==\s*{re.escape(genotype)}\s*==\s*$([\s\S]*?)(?=^==\s*.+?\s*==\s*$|\Z)",
        flags=re.MULTILINE,
    )
    section_match = section_pattern.search(content)
    if section_match:
        return section_match.group(1).strip()

    kv_pattern = re.compile(rf"\|\s*{re.escape(genotype)}\s*=\s*(.+)")
    kv_match = kv_pattern.search(content)
    if kv_match:
        return kv_match.group(1).strip()

    return "Специфичная интерпретация для генотипа не найдена. Показано общее описание SNP."


def interpretation_is_generic(text: str) -> bool:
    return text.strip() == "Специфичная интерпретация для генотипа не найдена. Показано общее описание SNP."


def extract_title_interpretation(content: str) -> str:
    section_pattern = re.compile(
        r"^==\s*title\s*==\s*$([\s\S]*?)(?=^==\s*.+?\s*==\s*$|\Z)",
        flags=re.IGNORECASE | re.MULTILINE,
    )
    section_match = section_pattern.search(content)
    if section_match:
        return section_match.group(1).strip()

    kv_pattern = re.compile(r"(?:^|\n)\s*\|?\s*title\s*=\s*([^\n\r|]+)", flags=re.IGNORECASE)
    kv_match = kv_pattern.search(content)
    if kv_match:
        return kv_match.group(1).strip()

    return ""


def extract_risk_allele(content: str) -> str | None:
    pattern = re.compile(r"(?:^|\n)\s*\|?\s*riskallele\s*=\s*([^|\n\r]+)", flags=re.IGNORECASE)
    match = pattern.search(content)
    if not match:
        return None
    allele = re.sub(r"[^ACGT-]", "", match.group(1).upper())
    return allele or None


def extract_trait(content: str) -> str:
    pattern = re.compile(r"(?:^|\n)\s*\|?\s*trait\s*=\s*([^|\n\r]+)", flags=re.IGNORECASE)
    match = pattern.search(content)
    if not match:
        return ""

    trait = match.group(1).strip()
    if trait.lower() == "none":
        return ""
    return trait


def is_bad_homozygous_genotype(genotype: str, risk_allele: str | None) -> bool:
    if not risk_allele or len(genotype) != 2:
        return False
    if genotype[0] != genotype[1]:
        return False
    return genotype[0] in set(risk_allele)


def build_interpretation_context(
    interpretation: str,
    title_interpretation: str,
    trait: str,
    risk_allele: str | None,
) -> str:
    notes: list[str] = []
    if title_interpretation:
        notes.append(f"Title: {title_interpretation}")
    if trait:
        notes.append(f"Trait: {trait}")
    if risk_allele:
        notes.append(f"RiskAllele: {risk_allele}")

    if not notes:
        return interpretation

    if interpretation_is_generic(interpretation):
        return "\n".join(notes)
    return "\n".join([interpretation, *notes])


def fetch_pubmed_links_for_snp(rsid: str, max_results: int = 3, timeout_s: int = 8) -> list[tuple[str, str]]:
    query = parse.urlencode(
        {
            "db": "pubmed",
            "term": f"{rsid}[Title/Abstract]",
            "retmax": str(max_results),
            "retmode": "json",
        }
    )
    search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?{query}"
    try:
        with request.urlopen(search_url, timeout=timeout_s) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return []

    ids = payload.get("esearchresult", {}).get("idlist", [])
    if not ids:
        return []

    summary_query = parse.urlencode(
        {
            "db": "pubmed",
            "id": ",".join(ids),
            "retmode": "json",
        }
    )
    summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?{summary_query}"
    try:
        with request.urlopen(summary_url, timeout=timeout_s) as response:  # noqa: S310
            summary_payload = json.loads(response.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return []

    result: list[tuple[str, str]] = []
    summary_data = summary_payload.get("result", {})
    for article_id in ids:
        item = summary_data.get(article_id)
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip() or f"PubMed {article_id}"
        result.append((title, f"https://pubmed.ncbi.nlm.nih.gov/{article_id}/"))
    return result


def classify_interpretation(text: str) -> str:
    lowered = text.lower()
    bad_markers = ["risk", "harm", "pathogenic", "bad", "опас", "риск", "вред"]
    good_markers = ["protect", "benefit", "good", "normal", "защит", "польз", "норм"]

    bad_hits = sum(marker in lowered for marker in bad_markers)
    good_hits = sum(marker in lowered for marker in good_markers)

    if bad_hits > good_hits:
        return "bad"
    if good_hits > bad_hits:
        return "good"
    return "neutral"


def scan_snps_with_progress(
    db_path: Path,
    snps: list[UserSNP],
    progress_path: Path,
    save_interval: int = 10,
    progress_callback: Callable[[int, int, list[MatchResult], dict[str, int]], None] | None = None,
) -> tuple[list[MatchResult], int, dict[str, int]]:
    progress = load_progress(progress_path)
    start_index = int(progress.get("next_index", 0))

    matches: list[MatchResult] = [
        _deserialize_match(match_payload)
        for match_payload in progress.get("matches", [])
        if isinstance(match_payload, dict)
    ]
    stats = {
        "found": int(progress.get("found", len(matches))),
        "good": int(progress.get("good", 0)),
        "bad": int(progress.get("bad", 0)),
    }

    checked_since_save = 0
    for idx in range(start_index, len(snps)):
        user_snp = snps[idx]
        entry = fetch_snp_entry(db_path, user_snp.rsid)
        if entry is None:
            checked_since_save += 1
            if progress_callback:
                progress_callback(idx + 1, len(snps), matches, stats)
            if checked_since_save >= save_interval:
                save_progress(progress_path, idx + 1, matches, stats)
                checked_since_save = 0
            continue

        orientation = detect_dump_orientation(entry.content)
        dump_genotype = convert_genotype_for_orientation(user_snp.genotype_plus, orientation)
        interpretation = extract_genotype_interpretation(entry.content, dump_genotype)
        title_interpretation = extract_title_interpretation(entry.content)
        trait = extract_trait(entry.content)
        risk_allele = extract_risk_allele(entry.content)
        is_bad_homozygous = is_bad_homozygous_genotype(dump_genotype, risk_allele)
        interpretation = build_interpretation_context(interpretation, title_interpretation, trait, risk_allele)
        classification = classify_interpretation(interpretation)

        match = MatchResult(
            rsid=entry.rsid,
            user_genotype_plus=user_snp.genotype_plus,
            user_genotype_for_dump=dump_genotype,
            orientation=orientation,
            classification=classification,
            interpretation=interpretation,
            title_interpretation=title_interpretation,
            trait=trait,
            risk_allele=risk_allele,
            is_bad_homozygous=is_bad_homozygous,
            pubmed_articles=fetch_pubmed_links_for_snp(entry.rsid),
            entry=entry,
        )
        matches.append(match)
        stats["found"] += 1
        if classification == "good":
            stats["good"] += 1
        elif classification == "bad":
            stats["bad"] += 1

        checked_since_save += 1
        if progress_callback:
            progress_callback(idx + 1, len(snps), matches, stats)
        if checked_since_save >= save_interval:
            save_progress(progress_path, idx + 1, matches, stats)
            checked_since_save = 0

    save_progress(progress_path, len(snps), matches, stats)
    return matches, len(snps), stats


def hash_upload_identity(db_name: str, snp_name: str) -> str:
    payload = f"{db_name}::{snp_name}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def build_match_report(matches: list[MatchResult]) -> str:
    lines: list[str] = []
    for i, match in enumerate(matches, start=1):
        lines.extend(
            [
                f"{i}. {match.rsid}",
                f"   - Генотип (23andMe +): {match.user_genotype_plus}",
                f"   - Генотип для дампа ({match.orientation}): {match.user_genotype_for_dump}",
                f"   - Классификация: {match.classification}",
                f"   - Заголовок/Title: {match.title_interpretation or '—'}",
                f"   - Trait: {match.trait or '—'}",
                f"   - RiskAllele: {match.risk_allele or '—'}",
                f"   - Плохая гомозигота: {'ДА' if match.is_bad_homozygous else 'нет'}",
                "   - Интерпретация:",
                f"{_indent_block(format_content_for_markdown(match.interpretation), 6)}",
                "   - PubMed:",
                f"{_indent_block(_format_pubmed_articles(match.pubmed_articles), 6)}",
                "",
            ]
        )
    return "\n".join(lines).strip()


def _format_pubmed_articles(articles: list[tuple[str, str]]) -> str:
    if not articles:
        return "Ничего не найдено."
    return "\n".join(f"- {title}: {url}" for title, url in articles)


def _indent_block(text: str, spaces: int) -> str:
    prefix = " " * spaces
    return "\n".join(f"{prefix}{line}" for line in text.splitlines())


def load_progress(progress_path: Path) -> dict:
    if not progress_path.exists():
        return {}
    try:
        return json.loads(progress_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_progress(
    progress_path: Path,
    next_index: int,
    matches: list[MatchResult],
    stats: dict[str, int],
) -> None:
    payload = {
        "next_index": next_index,
        "found": stats.get("found", 0),
        "good": stats.get("good", 0),
        "bad": stats.get("bad", 0),
        "matches": [_serialize_match(match) for match in matches],
    }
    progress_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _serialize_match(match: MatchResult) -> dict:
    return {
        "rsid": match.rsid,
        "user_genotype_plus": match.user_genotype_plus,
        "user_genotype_for_dump": match.user_genotype_for_dump,
        "orientation": match.orientation,
        "classification": match.classification,
        "interpretation": match.interpretation,
        "title_interpretation": match.title_interpretation,
        "trait": match.trait,
        "risk_allele": match.risk_allele,
        "is_bad_homozygous": match.is_bad_homozygous,
        "pubmed_articles": match.pubmed_articles,
        "entry": {
            "rsid": match.entry.rsid,
            "content": match.entry.content,
            "scraped_at": match.entry.scraped_at,
            "attribution": match.entry.attribution,
        },
    }


def _deserialize_match(payload: dict) -> MatchResult:
    entry_payload = payload.get("entry", {})
    entry = SNPEntry(
        rsid=entry_payload.get("rsid", payload.get("rsid", "")),
        content=entry_payload.get("content", ""),
        scraped_at=entry_payload.get("scraped_at"),
        attribution=entry_payload.get("attribution"),
    )
    return MatchResult(
        rsid=payload.get("rsid", ""),
        user_genotype_plus=payload.get("user_genotype_plus", ""),
        user_genotype_for_dump=payload.get("user_genotype_for_dump", ""),
        orientation=payload.get("orientation", "plus"),
        classification=payload.get("classification", "neutral"),
        interpretation=payload.get("interpretation", ""),
        title_interpretation=payload.get("title_interpretation", ""),
        trait=payload.get("trait", ""),
        risk_allele=payload.get("risk_allele"),
        is_bad_homozygous=bool(payload.get("is_bad_homozygous", False)),
        pubmed_articles=[tuple(item) for item in payload.get("pubmed_articles", [])],
        entry=entry,
    )
