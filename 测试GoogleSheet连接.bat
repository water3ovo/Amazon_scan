@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo 尚未安装运行环境，请先运行“一键安装并运行.bat”或“升级V5依赖.bat”。
  pause
  exit /b 1
)
.venv\Scripts\python.exe run_scan.py --test-google
set CODE=%errorlevel%
echo.
if %CODE%==0 (
  echo Google Sheet 连接测试通过。
) else (
  echo Google Sheet 连接测试失败，请保留上方错误信息。
)
pause
exit /b %CODE%
