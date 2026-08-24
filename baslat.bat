@echo off
chcp 65001 >nul
cd /d "%~dp0"

if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
) else (
    echo [UYARI] Sanal ortam yok. Once kurulum.bat dosyasini calistirin.
    echo Sistem Python'u ile denenecek...
)

python run_gui.py %*
if errorlevel 1 (
    echo.
    echo Program hata ile kapandi. Yukaridaki mesaji kontrol edin.
    pause
)
