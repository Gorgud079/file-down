#!/bin/bash
# Запуск двойным щелчком на macOS
cd "$(dirname "$0")"
python3 usmle_sorter.py "$@"
echo
read -n 1 -s -r -p "Нажмите любую клавишу, чтобы закрыть окно..."
