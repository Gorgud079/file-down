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

    while True:
        moved, dupes = sort_files(args.downloads, args.archive, subjects,
                                  args.include_unknown, args.dry_run)
        if moved or dupes or not args.watch:
            print(f"Перенесено: {moved}, дубликатов удалено: {dupes}")
        if not args.watch:
            break
        try:
            time.sleep(args.watch)
        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    main()
