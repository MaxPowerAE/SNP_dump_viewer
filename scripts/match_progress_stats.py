from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

DISPLAY_FIELDS = [
    "rsid",
    "user_genotype_plus",
    "user_genotype_for_dump",
    "orientation",
    "classification",
    "risk_allele",
    "title_interpretation",
    "trait",
    "pubmed_articles",
]

ANSI_RESET = "\033[0m"
ANSI_MATCH_BAD = "\033[1;31m"
ANSI_MATCH_GOOD = "\033[1;32m"
ANSI_FIELD_BLUE = "\033[1;34m"


def _load_progress(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _find_latest_progress_file(base_dir: Path) -> Path:
    candidates = sorted(base_dir.glob("match_progress*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(f"Файлы match_progress*.json не найдены в: {base_dir}")
    return candidates[0]


def _resolve_progress_dir(progress_dir: Path) -> Path:
    if progress_dir.is_absolute():
        return progress_dir

    cwd_candidate = progress_dir
    script_root_candidate = Path(__file__).resolve().parent.parent / progress_dir

    if cwd_candidate.exists():
        return cwd_candidate
    if script_root_candidate.exists():
        return script_root_candidate

    return cwd_candidate


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


def _stringify_for_table(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if value is None:
        return "null"
    return str(value)


def _build_progress_rows(progress: dict[str, Any], match_count: int) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    known_keys = ["next_index", "found", "good", "bad"]

    for key in known_keys:
        if key in progress:
            rows.append((key, _stringify_for_table(progress.get(key))))

    rows.append(("matches", str(match_count)))

    for key in sorted(progress):
        if key in {*known_keys, "matches"}:
            continue
        rows.append((key, _stringify_for_table(progress.get(key))))

    return rows


def _normalize_trait(value: Any) -> str:
    return str(value).strip()


def _has_risk_allele_match(match: dict[str, Any]) -> bool:
    genotype = str(match.get("user_genotype_for_dump", "")).upper()
    risk = str(match.get("risk_allele") or "").upper().strip()
    if not genotype or not risk:
        return False
    return risk in genotype


def _match_label(match: dict[str, Any]) -> str:
    """Возвращает GOOD/BAD пометку для найденного совпадения."""
    for key in ("status", "label", "result", "mark"):
        raw = match.get(key)
        if raw is None:
            continue
        value = str(raw).strip().lower()
        if value in {"bad", "risk", "negative", "harmful"}:
            return "BAD"
        if value in {"good", "positive", "safe", "protective"}:
            return "GOOD"

    return "BAD" if _has_risk_allele_match(match) else "GOOD"


def _match_field_color(match: dict[str, Any]) -> str | None:
    classification = str(match.get("classification") or "").strip().lower()
    if classification == "neutral" or not _has_risk_allele_match(match):
        return None
    if classification == "bad":
        return ANSI_MATCH_BAD
    if classification == "good":
        return ANSI_MATCH_GOOD
    return None


def _colorize_match_value(key: str, value: str, match: dict[str, Any]) -> str:
    if key == "risk_allele" and value != "null":
        return f"{ANSI_MATCH_BAD}{value}{ANSI_RESET}"

    if key == "user_genotype_for_dump":
        base_value = f"{ANSI_FIELD_BLUE}{value}{ANSI_RESET}"
        match_color = _match_field_color(match)
        if match_color:
            return f"{match_color}{value}{ANSI_RESET}"
        return base_value

    if key == "rsid":
        match_color = _match_field_color(match)
        if match_color:
            return f"{match_color}{value}{ANSI_RESET}"

    return value


def _detailed_match_info(matches: list[dict[str, Any]], *, colorize: bool = False) -> str:
    if not matches:
        return "\nДетализация совпадений\nСовпадения отсутствуют"

    lines = ["\nДетализация совпадений"]
    for idx, match in enumerate(matches, start=1):
        lines.append(f"\n[{idx}] {_match_label(match)}")
        for key in DISPLAY_FIELDS:
            if key in match:
                value = _stringify_for_table(match.get(key))
                if colorize:
                    value = _colorize_match_value(key, value, match)
                lines.append(f"{key}: {value}")

    return "\n".join(lines)


def _default_report_path(source_path: Path) -> Path:
    return source_path.with_suffix(".report.txt")


def _colorize_report(report: str) -> str:
    colorized = re.sub(r"^(\[\d+\]\s+)BAD$", rf"\1{ANSI_MATCH_BAD}BAD{ANSI_RESET}", report, flags=re.MULTILINE)
    colorized = re.sub(r"^(\[\d+\]\s+)GOOD$", rf"\1{ANSI_MATCH_GOOD}GOOD{ANSI_RESET}", colorized, flags=re.MULTILINE)
    return colorized


def write_report(path: Path, report: str, output_path: Path | None = None) -> Path:
    target = output_path or _default_report_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(report, encoding="utf-8")
    return target


def _launch_gui(
    path: Path,
    report: str,
    stats_rows: list[tuple[str, str]],
    trait_rows: list[tuple[str, str]],
    matches: list[dict[str, Any]],
) -> None:
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title("SNP Match Progress Stats")
    root.geometry("1024x760")

    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("Header.TLabel", font=("Segoe UI", 14, "bold"))

    main = ttk.Frame(root, padding=16)
    main.pack(fill="both", expand=True)

    ttk.Label(main, text=f"Отчет по файлу: {path}", style="Header.TLabel").pack(anchor="w")

    tables = ttk.Frame(main)
    tables.pack(fill="x", pady=(12, 10))

    stats_frame = ttk.LabelFrame(tables, text="Краткая статистика", padding=8)
    stats_frame.pack(side="left", fill="both", expand=True, padx=(0, 8))
    stats_tree = ttk.Treeview(stats_frame, columns=("metric", "value"), show="headings", height=8)
    stats_tree.heading("metric", text="Метрика")
    stats_tree.heading("value", text="Значение")
    stats_tree.column("metric", width=230, anchor="w")
    stats_tree.column("value", width=160, anchor="w")
    for row in stats_rows:
        stats_tree.insert("", "end", values=row)
    stats_tree.pack(fill="both", expand=True)

    traits_frame = ttk.LabelFrame(tables, text="Топ trait", padding=8)
    traits_frame.pack(side="left", fill="both", expand=True)
    traits_tree = ttk.Treeview(traits_frame, columns=("trait", "count"), show="headings", height=8)
    traits_tree.heading("trait", text="Trait")
    traits_tree.heading("count", text="Совпадений")
    traits_tree.column("trait", width=200, anchor="w")
    traits_tree.column("count", width=120, anchor="w")
    for row in trait_rows:
        traits_tree.insert("", "end", values=row)
    traits_tree.pack(fill="both", expand=True)

    report_frame = ttk.LabelFrame(main, text="Детальный отчет", padding=8)
    report_frame.pack(fill="both", expand=True)
    text = tk.Text(report_frame, wrap="word", font=("Consolas", 10))
    text.tag_configure("match_bad", foreground="#b91c1c", font=("Consolas", 10, "bold"))
    text.tag_configure("match_good", foreground="#166534", font=("Consolas", 10, "bold"))
    text.tag_configure("allele_blue", foreground="#1d4ed8", font=("Consolas", 10, "bold"))

    details_title = "\nДетализация совпадений"
    header, _, _ = report.partition(details_title)
    text.insert("1.0", header + details_title)

    if not matches:
        text.insert("end", "\nСовпадения отсутствуют")
    else:
        for idx, match in enumerate(matches, start=1):
            text.insert("end", f"\n\n[{idx}] {_match_label(match)}\n")

            for key in DISPLAY_FIELDS:
                if key not in match:
                    continue

                line_start = text.index("end")
                value = _stringify_for_table(match.get(key))
                text.insert("end", f"{key}: {value}\n")
                value_start = f"{line_start}+{len(key) + 2}c"
                value_end = f"{value_start}+{len(value)}c"

                match_color = _match_field_color(match)
                if key == "risk_allele" and value != "null":
                    text.tag_add("match_bad", value_start, value_end)
                elif key == "user_genotype_for_dump":
                    text.tag_add("allele_blue", value_start, value_end)
                    if match_color == ANSI_MATCH_BAD:
                        text.tag_add("match_bad", value_start, value_end)
                    elif match_color == ANSI_MATCH_GOOD:
                        text.tag_add("match_good", value_start, value_end)
                elif key == "rsid":
                    if match_color == ANSI_MATCH_BAD:
                        text.tag_add("match_bad", value_start, value_end)
                    elif match_color == ANSI_MATCH_GOOD:
                        text.tag_add("match_good", value_start, value_end)

    start = "1.0"
    while True:
        bad_idx = text.search(" BAD", start, stopindex="end")
        if not bad_idx:
            break
        text.tag_add("match_bad", f"{bad_idx} linestart", f"{bad_idx} lineend")
        start = f"{bad_idx} lineend"

    start = "1.0"
    while True:
        good_idx = text.search(" GOOD", start, stopindex="end")
        if not good_idx:
            break
        text.tag_add("match_good", f"{good_idx} linestart", f"{good_idx} lineend")
        start = f"{good_idx} lineend"

    text.configure(state="disabled")
    text.pack(side="left", fill="both", expand=True)
    scrollbar = ttk.Scrollbar(report_frame, orient="vertical", command=text.yview)
    scrollbar.pack(side="right", fill="y")
    text.configure(yscrollcommand=scrollbar.set)

    root.mainloop()


def show_gui(
    path: Path,
    report: str,
    stats_rows: list[tuple[str, str]],
    trait_rows: list[tuple[str, str]],
    matches: list[dict[str, Any]],
) -> bool:
    try:
        _launch_gui(path, report, stats_rows, trait_rows, matches)
        return True
    except Exception:
        return False


def build_report(path: Path) -> str:
    progress = _load_progress(path)
    return _build_report_from_progress(path, progress)


def _build_report_from_progress(path: Path, progress: dict[str, Any], *, colorize: bool = False) -> str:
    matches: list[dict[str, Any]] = [m for m in progress.get("matches", []) if isinstance(m, dict)]
    stats_rows, trait_rows = _build_summary(progress)
    progress_rows = _build_progress_rows(progress, len(matches))
    return "\n\n".join(
        [
            f"Файл: {path}",
            _table(progress_rows, "Поля progress JSON"),
            _table(stats_rows, "Краткая статистика"),
            _table(trait_rows, "Топ-5 trait"),
            _detailed_match_info(matches, colorize=colorize),
        ]
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Парсит match_progress*.json, создает текстовый отчет и показывает статистику в GUI. "
            "Если путь не указан — берется самый свежий файл из .progress/."
        )
    )
    parser.add_argument("path", nargs="?", help="Путь до файла match_progress*.json")
    parser.add_argument(
        "--progress-dir",
        default=".progress",
        help="Каталог для автоматического поиска match_progress*.json (по умолчанию: .progress)",
    )
    parser.add_argument(
        "--report-out",
        help="Куда сохранить текстовый отчет (по умолчанию рядом с json: *.report.txt)",
    )
    parser.add_argument(
        "--no-gui",
        action="store_true",
        help="Не открывать GUI (только CLI-вывод и сохранение отчета)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.path:
        target = Path(args.path)
    else:
        progress_dir = _resolve_progress_dir(Path(args.progress_dir))
        target = _find_latest_progress_file(progress_dir)

    if not target.exists():
        raise FileNotFoundError(f"Файл не найден: {target}")

    progress = _load_progress(target)
    stats_rows, trait_rows = _build_summary(progress)
    report = _build_report_from_progress(target, progress)
    colorized_report = _colorize_report(_build_report_from_progress(target, progress, colorize=True))
    report_path = write_report(target, report, Path(args.report_out) if args.report_out else None)

    print(colorized_report)
    print(f"\nОтчет сохранен: {report_path}")

    if not args.no_gui:
        matches: list[dict[str, Any]] = [m for m in progress.get("matches", []) if isinstance(m, dict)]
        is_gui_opened = show_gui(target, report, stats_rows, trait_rows, matches)
        if not is_gui_opened:
            print("GUI недоступен в текущем окружении. Используйте --no-gui для подавления этого сообщения.")


if __name__ == "__main__":
    main()
