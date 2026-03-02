from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def _load_progress(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _find_latest_progress_file(base_dir: Path) -> Path:
    candidates = sorted(base_dir.glob("match_progress*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(f"Файлы match_progress*.json не найдены в: {base_dir}")
    return candidates[0]


def _safe_percent(part: int, total: int) -> str:
    if total == 0:
        return "0.0%"
    return f"{(part / total) * 100:.1f}%"


def _table(rows: list[tuple[str, str]], title: str) -> str:
    key_header = "Метрика"
    value_header = "Значение"
    key_width = max(len(key_header), *(len(key) for key, _ in rows)) if rows else len(key_header)
    value_width = max(len(value_header), *(len(value) for _, value in rows)) if rows else len(value_header)

    line = f"+{'-' * (key_width + 2)}+{'-' * (value_width + 2)}+"
    header = f"| {key_header:<{key_width}} | {value_header:<{value_width}} |"
    body = [f"| {key:<{key_width}} | {value:<{value_width}} |" for key, value in rows]

    title_line = f"\n{title}\n" if title else ""
    return "\n".join([title_line + line, header, line, *body, line])


def _build_summary(progress: dict[str, Any]) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    matches: list[dict[str, Any]] = [m for m in progress.get("matches", []) if isinstance(m, dict)]

    found = int(progress.get("found", len(matches)))
    good = int(progress.get("good", 0))
    bad = int(progress.get("bad", 0))
    neutral = max(found - good - bad, 0)

    checked = int(progress.get("next_index", 0))
    risk_allele_matches = sum(1 for m in matches if _has_risk_allele_match(m))

    stats_rows = [
        ("Проверено SNP", str(checked)),
        ("Найдено совпадений", str(found)),
        ("Good", f"{good} ({_safe_percent(good, found)})"),
        ("Bad", f"{bad} ({_safe_percent(bad, found)})"),
        ("Neutral", f"{neutral} ({_safe_percent(neutral, found)})"),
        ("С risk-аллелем", f"{risk_allele_matches} ({_safe_percent(risk_allele_matches, found)})"),
    ]

    trait_counter = Counter(_normalize_trait(m.get("trait", "")) for m in matches)
    trait_counter.pop("", None)
    top_traits = trait_counter.most_common(5)
    trait_rows = [(trait, str(count)) for trait, count in top_traits] or [("—", "0")]
    return stats_rows, trait_rows


def _normalize_trait(value: Any) -> str:
    return str(value).strip()


def _has_risk_allele_match(match: dict[str, Any]) -> bool:
    genotype = str(match.get("user_genotype_for_dump", "")).upper()
    risk = str(match.get("risk_allele") or "").upper().strip()
    if not genotype or not risk:
        return False
    return risk in genotype


def build_report(path: Path) -> str:
    progress = _load_progress(path)
    stats_rows, trait_rows = _build_summary(progress)
    return "\n\n".join(
        [
            f"Файл: {path}",
            _table(stats_rows, "Краткая статистика"),
            _table(trait_rows, "Топ-5 trait"),
        ]
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Парсит match_progress*.json и выводит краткую таблицу статистики. "
            "Если путь не указан — берется самый свежий файл из .progress/."
        )
    )
    parser.add_argument("path", nargs="?", help="Путь до файла match_progress*.json")
    parser.add_argument(
        "--progress-dir",
        default=".progress",
        help="Каталог для автоматического поиска match_progress*.json (по умолчанию: .progress)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.path:
        target = Path(args.path)
    else:
        target = _find_latest_progress_file(Path(args.progress_dir))

    if not target.exists():
        raise FileNotFoundError(f"Файл не найден: {target}")

    print(build_report(target))


if __name__ == "__main__":
    main()
