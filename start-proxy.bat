@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Селектор ВкусВилл — локальный сервер
echo.
echo   http://127.0.0.1:8770/        (на этом компьютере)
echo   http://IP-компьютера:8770/    (с телефона в домашней сети — запускать с --lan)
echo.
echo Остановить: Ctrl+C
echo.
start "" http://127.0.0.1:8770/
python proxy\local_proxy.py 8770 %*
pause
