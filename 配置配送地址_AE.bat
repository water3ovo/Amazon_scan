@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo 请先运行“一键安装并运行.bat”完成环境安装。
  pause
  exit /b 1
)
.venv\Scripts\python.exe run_scan.py --setup-location AE
pause
