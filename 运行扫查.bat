@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo 尚未安装运行环境，请先双击“一键安装并运行.bat”。
  pause
  exit /b 1
)
.venv\Scripts\python.exe run_scan.py
set CODE=%errorlevel%
echo.
echo 扫查结束，结果在 output 文件夹。
pause
exit /b %CODE%
