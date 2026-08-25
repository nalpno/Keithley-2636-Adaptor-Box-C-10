@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================================
echo   GPIB destegi kurulumu (ADLINK USB-3488A icin)
echo ============================================================
echo.
echo NI-VISA / Keithley I/O Layer, ADLINK gibi ucuncu parti GPIB
echo adaptorlerini goremez. Bu betik, ADLINK surucusunun kurdugu
echo gpib-32.dll uzerinden calisan saf Python yolunu kurar.
echo.

if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
) else (
    echo [UYARI] Sanal ortam yok. Once kurulum.bat calistirilmali.
)

python -m pip install pyvisa-py gpib-ctypes
if errorlevel 1 (
    echo [HATA] Kurulum basarisiz.
    pause
    exit /b 1
)

echo.
echo ------------------------------------------------------------
echo Kurulum bitti. Simdi baglanti deneniyor...
echo ------------------------------------------------------------
python baglanti_testi.py --kutuphane @py --kaynak "GPIB0::26::INSTR"

echo.
echo Basarili olduysa programda:
echo    VISA kutuphanesi : @py
echo    VISA kaynagi     : GPIB0::26::INSTR
echo.
pause
