@echo off
chcp 65001 >nul
cd /d "%~dp0"

if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"

echo Simulasyon modu: gercek cihaz kullanilmaz, arayuz ve analizler denenebilir.
python run_gui.py --simulate
if errorlevel 1 pause
