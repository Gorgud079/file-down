#!/usr/bin/env python3
"""
USMLE Sorter: переносит файлы задач USMLE (json и картинки) из папки
«Загрузки» в архив, разложенный по предметам и месяцам:

    USMLE_Archive/
        Respiratory/
            2026-10/
                res-batch-11.json
                res-147.png
        Immunology/
            2026-10/
                batch-imm-002.json

Предмет определяется по коду в имени файла:
    res-batch-11.json  -> res
    batch-imm-002.json -> imm
    res-147.png        -> res
Месяц — по дате, когда файл был скачан (дата изменения файла).

После каждого запуска в корне архива обновляется USMLE_library.md —
перечень папок, файлов и занятых номеров. Этот файл можно отправить в Claude,
чтобы новые задачи не повторяли уже существующие названия.

Коды предметов и названия папок задаются в subjects.json рядом со скриптом.
Нужен только Python 3.8+, сторонние библиотеки не требуются.
"""

import argparse
import filecmp
import json
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SUBJECTS_FILE = SCRIPT_DIR / "subjects.json"
LIBRARY_NAME = "USMLE_library.md"

EXTENSIONS = {".json", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}

# [batch-]<код>-[batch-]<номер>, например res-batch-11, batch-imm-002, res-147
NAME_RE = re.compile(r"^(?:batch[-_ ]?)?([a-z]+)[-_ ](?:batch[-_ ]?)?(\d+)$", re.IGNORECASE)
# Хвост, который браузер добавляет к повторным загрузкам: "res-147 (1)"
COPY_SUFFIX_RE = re.compile(r"\s*\(\d+\)$")


def default_downloads():
    home = Path.home()
    for name in ("Downloads", "Загрузки"):
        if (home / name).is_dir():
            return home / name
    return home / "Downloads"


def load_subjects():
    try:
        with open(SUBJECTS_FILE, encoding="utf-8") as f:
            return {k.lower(): v for k, v in json.load(f).items()}
    except FileNotFoundError:
        print(f"Не найден {SUBJECTS_FILE}, предметы будут называться по коду.")
        return {}


def subject_code(path):
    """Возвращает код предмета ('res', 'imm', ...) или None, если файл не про USMLE."""
    if path.suffix.lower() not in EXTENSIONS:
        return None
    stem = COPY_SUFFIX_RE.sub("", path.stem)
    m = NAME_RE.match(stem)
    if not m:
        return None
    code = m.group(1).lower()
    return None if code == "batch" else code


def parse_name(path):
    """res-batch-11.json -> ('res-batch', 11, '11'); None, если имя не по схеме."""
    m = NAME_RE.match(path.stem)
    if not m:
        return None
    series = path.stem[:m.start(2)].rstrip("-_ ").lower()
    return series, int(m.group(2)), m.group(2)


def natural_key(path):
    """Сортировка «по-человечески»: res-batch-2 раньше res-batch-11."""
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", path.name.lower())]


def compress_ranges(numbers):
    """[1, 2, 3, 5, 7, 8] -> '1–3, 5, 7–8'"""
    parts = []
    nums = sorted(set(numbers))
    start = prev = nums[0]
    for n in nums[1:] + [None]:
        if n is not None and n == prev + 1:
            prev = n
            continue
        parts.append(str(start) if start == prev else f"{start}–{prev}")
        if n is not None:
            start = prev = n
    return ", ".join(parts)


def build_library(archive):
    """Пересобирает USMLE_library.md по текущему содержимому архива."""
    folders = {}   # предмет -> месяц -> [файлы]
    series = {}    # серия -> {"subject", "numbers", "width", "kinds", "files"}
    total = 0

    for subject_dir in sorted(d for d in archive.iterdir() if d.is_dir()):
        for month_dir in sorted(d for d in subject_dir.iterdir() if d.is_dir()):
            files = sorted((f for f in month_dir.iterdir() if f.is_file()), key=natural_key)
            if not files:
                continue
            folders.setdefault(subject_dir.name, {})[month_dir.name] = [f.name for f in files]
            total += len(files)
            for f in files:
                parsed = parse_name(f)
                if not parsed:
                    continue
                name, num, digits = parsed
                info = series.setdefault(name, {"subject": subject_dir.name, "numbers": set(),
                                                 "width": 0, "kinds": set(), "files": 0})
                info["numbers"].add(num)
                info["width"] = max(info["width"], len(digits))
                info["kinds"].add("json" if f.suffix.lower() == ".json" else "картинки")
                info["files"] += 1

    lines = [
        "# Библиотека задач USMLE",
        "",
        f"Обновлено: {datetime.now():%Y-%m-%d %H:%M} · файлов в архиве: {total}",
        "",
        "> Для Claude: ниже перечислены уже существующие задачи. При создании новых",
        "> не используй занятые названия и номера — продолжай нумерацию с",
        "> «следующего свободного» номера соответствующей серии.",
        "",
        "## Занятые номера",
        "",
        "| Серия | Предмет | Тип | Занятые номера | Файлов | Следующее свободное имя |",
        "|-------|---------|-----|----------------|--------|-------------------------|",
    ]
    for name in sorted(series, key=lambda n: (series[n]["subject"], n)):
        info = series[name]
        nxt = str(max(info["numbers"]) + 1).zfill(info["width"])
        lines.append(f"| {name} | {info['subject']} | {', '.join(sorted(info['kinds']))} "
                     f"| {compress_ranges(info['numbers'])} | {info['files']} | {name}-{nxt} |")
    if not series:
        lines.append("| — | — | — | — | 0 | — |")

    lines += ["", "## Все файлы по папкам", ""]
    for subject, months in folders.items():
        count = sum(len(v) for v in months.values())
        lines += [f"### {subject} ({count})", ""]
        for month, names in months.items():
            lines.append(f"- **{month}** ({len(names)}): " + ", ".join(names))
        lines.append("")

    library = archive / LIBRARY_NAME
    library.write_text("\n".join(lines), encoding="utf-8")
    return library


def unique_target(target):
    """res-147.png -> res-147_2.png, если такое имя уже занято."""
    n = 2
    candidate = target
    while candidate.exists():
        candidate = target.with_name(f"{target.stem}_{n}{target.suffix}")
        n += 1
    return candidate


def sort_files(downloads, archive, subjects, include_unknown, dry_run):
    moved = skipped_dupes = 0
    unknown_codes = set()

    for src in sorted(downloads.iterdir()):
        if not src.is_file():
            continue
        code = subject_code(src)
        if code is None:
            continue

        if code in subjects:
            subject = subjects[code]
        elif include_unknown:
            subject = code.upper()
        else:
            unknown_codes.add(code)
            continue

        month = datetime.fromtimestamp(src.stat().st_mtime).strftime("%Y-%m")
        dest_dir = archive / subject / month
        clean_name = COPY_SUFFIX_RE.sub("", src.stem) + src.suffix.lower()
        target = dest_dir / clean_name

        if target.exists() and filecmp.cmp(src, target, shallow=False):
            print(f"  дубликат, удаляю из Загрузок: {src.name}")
            if not dry_run:
                src.unlink()
            skipped_dupes += 1
            continue

        target = unique_target(target)
        print(f"  {src.name}  ->  {target.relative_to(archive)}")
        if not dry_run:
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(target))
        moved += 1

    if unknown_codes:
        print("Пропущены файлы с неизвестными кодами предметов: "
              + ", ".join(sorted(unknown_codes))
              + f"\n  Добавьте их в {SUBJECTS_FILE.name} или запустите с --include-unknown")
    return moved, skipped_dupes


def main():
    p = argparse.ArgumentParser(description="Раскладывает файлы USMLE из Загрузок по предметам и месяцам.")
    p.add_argument("--downloads", type=Path, default=default_downloads(),
                   help="папка с загрузками (по умолчанию ~/Downloads или ~/Загрузки)")
    p.add_argument("--archive", type=Path, default=Path.home() / "USMLE_Archive",
                   help="папка архива (по умолчанию ~/USMLE_Archive)")
    p.add_argument("--dry-run", action="store_true",
                   help="только показать, что будет перенесено, ничего не трогать")
    p.add_argument("--include-unknown", action="store_true",
                   help="переносить и файлы с кодами, которых нет в subjects.json")
    p.add_argument("--watch", type=int, metavar="СЕК", default=0,
                   help="не завершаться, а проверять папку каждые СЕК секунд")
    args = p.parse_args()

    if not args.downloads.is_dir():
        sys.exit(f"Папка загрузок не найдена: {args.downloads}")

    subjects = load_subjects()
    print(f"Загрузки: {args.downloads}\nАрхив:    {args.archive}"
          + ("\n(пробный запуск, файлы не переносятся)" if args.dry_run else ""))

    first = True
    while True:
        moved, dupes = sort_files(args.downloads, args.archive, subjects,
                                  args.include_unknown, args.dry_run)
        if moved or dupes or not args.watch:
            print(f"Перенесено: {moved}, дубликатов удалено: {dupes}")
        if not args.dry_run and args.archive.is_dir() and (moved or dupes or first):
            print(f"Библиотека обновлена: {build_library(args.archive)}")
        first = False
        if not args.watch:
            break
        try:
            time.sleep(args.watch)
        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    main()
