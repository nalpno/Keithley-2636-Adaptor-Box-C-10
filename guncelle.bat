@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================================
echo   Programi guncelle (git pull)
echo ============================================================
echo.

git --version >nul 2>&1
if errorlevel 1 (
    echo [HATA] Git bulunamadi.
    echo https://git-scm.com/download/win adresinden kurun.
    pause
    exit /b 1
)

if not exist ".git" (
    echo [HATA] Bu klasor bir git deposu degil.
    echo ZIP ile indirdiyseniz once README'deki "git clone" adimini uygulayin.
    pause
    exit /b 1
)

echo Guncellemeler indiriliyor...
git pull
if errorlevel 1 (
    echo.
    echo [HATA] git pull basarisiz. Yerel degisiklikleriniz varsa once
    echo   git stash    komutunu deneyin.
    pause
    exit /b 1
)

echo.
echo Paketler kontrol ediliyor...
if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
    python -m pip install -q -r requirements.txt
)

echo.
echo Guncelleme tamamlandi.
pause
