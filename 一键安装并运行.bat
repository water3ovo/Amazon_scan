@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ========================================
echo Amazon AE/SA 扫查 V2 - 首次安装并运行
echo ========================================

where py >nul 2>nul
if %errorlevel%==0 (
  set PYTHON=py
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo [错误] 未检测到 Python。请先安装 Python 3.10+ 并勾选 Add Python to PATH。
    pause
    exit /b 1
  )
  set PYTHON=python
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/3] 创建独立虚拟环境 .venv ...
  %PYTHON% -m venv .venv
  if errorlevel 1 goto :fail
)

echo [2/3] 安装/更新依赖 ...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto :fail

if not exist "input\scan_targets.xlsx" (
  echo [3/3] 创建空白输入模板 ...
  .venv\Scripts\python.exe run_scan.py --make-template
  echo.
  echo 已创建 input\scan_targets.xlsx。请先填入扫查目标，再双击“运行扫查.bat”。
  echo 也可以把完整的“扫查_2026-09.xlsx”拖到“使用指定Excel运行.bat”。
  pause
  exit /b 0
)

echo [3/3] 开始扫查 ...
.venv\Scripts\python.exe run_scan.py
set CODE=%errorlevel%
echo.
echo 程序结束，返回码 %CODE%。结果在 output 文件夹。
pause
exit /b %CODE%

:fail
echo.
echo [错误] 安装或运行失败，请截图本窗口并保留错误信息。
pause
exit /b 1
