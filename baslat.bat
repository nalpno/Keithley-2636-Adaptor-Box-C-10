@echo off
setlocal
title UV Fotodedektor - Program
cd /d "%~dp0"
echo ================================================================
echo  UV Fotodedektor (XP surumu) - Program
echo ================================================================
echo Klasor    : %CD%
if not exist "%~dp0program.py" goto eksik
if not exist "%~dp0uvpd_xp\__init__.py" goto eksik
set "PY="
if exist "C:\Python34\python.exe" set PY="C:\Python34\python.exe"
if not defined PY if exist "%SystemDrive%\Python34\python.exe" set PY="%SystemDrive%\Python34\python.exe"
if not defined PY if exist "%ProgramFiles%\Python34\python.exe" set PY="%ProgramFiles%\Python34\python.exe"
if defined PY goto pybulundu
py -3.4 -c "import sys" >nul 2>&1
if not errorlevel 1 set "PY=py -3.4"
if defined PY goto pybulundu
python -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, 3) else 1)" >nul 2>&1
if not errorlevel 1 set "PY=python"
if defined PY goto pybulundu
goto pyyok
:pybulundu
echo Python    : %PY%
echo.
echo Program aciliyor... (bu siyah pencereyi KAPATMAYIN)
%PY% program.py %*
if errorlevel 1 goto hata
goto :eof

:eksik
echo.
echo [HATA] Program dosyalari bu klasorde bulunamadi:
echo        %~dp0
echo.
echo  Muhtemel sebep: dosyaya ZIP'in ICINDEN cift tiklandi.
echo  Windows XP, ZIP'in icindeki bir dosyayi tek basina calistirir;
echo  programin diger dosyalari yaninda olmaz.
echo.
echo  Cozum: ZIP dosyasina sag tiklayin, "Tumunu Ayikla" (Extract All)
echo  ile ornegin C:\Keithley_XP klasorune cikarin, sonra o klasordeki
echo  .bat dosyasina cift tiklayin.
goto son

:pyyok
echo.
echo [HATA] Python 3.4 bulunamadi.
echo.
echo  Windows XP icin Python 3.4.4 (32-bit) kurun:
echo    https://www.python.org/ftp/python/3.4.4/python-3.4.4.msi
echo  Kurulumda klasoru C:\Python34 olarak birakin ve "Tcl/Tk"
echo  bilesenini kaldirmayin. Ayrinti: README.md
goto son

:hata
echo.
echo [HATA] Program hata ile kapandi. Yukaridaki mesaji okuyun.
echo  Hata ayrintisi ayrica bu dosyaya yazildi (varsa):
echo    %~dp0hata_kaydi.txt
goto son

:son
echo.
pause
