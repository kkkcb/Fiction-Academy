@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Fiction Academy 本地版

rem 依赖缺失时自动补装（只在第一次发生）
python -c "import fastapi, uvicorn" 2>nul || (
  echo [首次运行] 正在安装依赖，请稍等...
  python -m pip install -q -r backend\requirements.txt
)

rem 3 秒后自动打开浏览器
start "" cmd /c "timeout /t 3 /nobreak >nul & start http://localhost:%PORT%"

echo ================================================
echo   本地版启动中，浏览器马上会自动打开
echo.
echo   [改了代码] 会自动生效，刷新浏览器即可
echo   [停止本地] 直接关掉这个窗口
echo   [服务器版] 24小时在 http://YOUR_VPS_IP/
echo              不受本地开关机影响
echo ================================================
rem 8000 被其他项目占用时自动改用 8100
set PORT=8000
netstat -ano | findstr ":8000 " | findstr "LISTENING" >nul 2>&1 && set PORT=8100
echo 使用端口 %PORT%（浏览器将自动打开）
python -m uvicorn backend.main:app --host 127.0.0.1 --port %PORT% --reload
pause
