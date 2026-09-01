@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo 请先运行“一键安装并运行.bat”完成环境安装。
  pause
  exit /b 1
)
if "%~1"=="" (
  echo 请把导出的 xlsx 文件直接拖到这个 bat 文件上运行。
  echo 例如：扫查_2026-09.xlsx
  pause
  exit /b 1
)
.venv\Scripts\python.exe run_scan.py --input "%~1"
set CODE=%errorlevel%
echo.
echo 扫查结束，结果在 output 文件夹。
pause
exit /b %CODE%
