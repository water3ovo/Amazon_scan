@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ========================================
echo Amazon Scan V5 - 安装 Google Sheet 依赖
echo ========================================

if not exist ".venv\Scripts\python.exe" (
  echo [错误] 未检测到现有 .venv，请先运行“一键安装并运行.bat”。
  pause
  exit /b 1
)

echo 正在安装/更新 V5 依赖...
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto :fail

echo.
echo V5 依赖安装完成。
echo 下一步：把服务账号 JSON 放到 config\google_service_account.json
echo 然后运行“测试GoogleSheet连接.bat”。
pause
exit /b 0

:fail
echo.
echo [错误] V5 依赖安装失败，请保留本窗口错误信息。
pause
exit /b 1
