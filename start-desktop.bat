@echo off
cd /d "%~dp0"
echo ========================================
echo 测试执行器 - 原生窗模式
echo ========================================
echo.
echo 检查 pywebview...
python -c "import pywebview" 2>nul
if errorlevel 1 (
    echo pywebview 未安装，正在安装...
    pip install pywebview
    echo.
)
echo 正在启动原生窗...
python app.py
