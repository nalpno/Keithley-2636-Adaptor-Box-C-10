@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================================
echo   UV Fotodedektor Olcum Arayuzu - Kurulum
echo   Keithley 2636 + Adapter Box C 10
echo ============================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [HATA] Python bulunamadi.
    echo.
    echo https://www.python.org/downloads/ adresinden Python 3.9 veya
    echo uzerini kurun ve kurulum sirasinda
    echo     "Add python.exe to PATH"
    echo kutucugunu MUTLAKA isaretleyin. Sonra bu dosyayi tekrar calistirin.
    echo.
    pause
    exit /b 1
)

for /f "delims=" %%v in ('python --version') do echo Bulunan Python: %%v
echo.

if not exist ".venv\Scripts\activate.bat" (
    echo Sanal ortam olusturuluyor [.venv] ...
    python -m venv .venv
    if errorlevel 1 (
        echo [HATA] Sanal ortam olusturulamadi.
        pause
        exit /b 1
    )
) else (
    echo Sanal ortam zaten var, kullaniliyor.
)

call ".venv\Scripts\activate.bat"

echo.
echo Paketler kuruluyor [numpy, matplotlib, pyvisa, PyQt5] ...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [HATA] Paket kurulumu basarisiz. Internet baglantisini kontrol edin.
    pause
    exit /b 1
)

echo.
echo ------------------------------------------------------------
echo VISA / GPIB kontrolu:
python -c "import pyvisa; rm=pyvisa.ResourceManager(); print('  Bulunan kaynaklar:', rm.list_resources() or '(yok)')" 2>nul
if errorlevel 1 (
    echo   [UYARI] VISA kutuphanesi bulunamadi.
    echo   USB-3488A surucusu ve VISA (NI-VISA / Keysight IO Libraries /
    echo   MCC VISA) kurulu olmali. 4PP programinda kullandiginiz kurulum
    echo   yeterlidir. Cihaz olmadan denemek icin simulasyon modunu kullanin.
)
echo ------------------------------------------------------------
echo.
echo Kurulum tamamlandi.
echo   * Programi calistirmak icin:            baslat.bat
echo   * Cihazsiz denemek icin:                baslat-simulasyon.bat
echo.
pause
