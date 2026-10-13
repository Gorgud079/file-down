@echo off
chcp 65001 >nul
python "%~dp0usmle_sorter.py" %*
pause
