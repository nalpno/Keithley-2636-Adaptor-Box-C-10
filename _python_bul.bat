@echo off
rem Python 3.4 yorumlayicisini bulur ve PY degiskenine yazar.
rem Diger .bat dosyalari tarafindan "call" ile kullanilir.
rem Yol iceren degerler tirnakli saklanir (bosluklu klasorler icin).
set "PY="
if exist "C:\Python34\python.exe" set PY="C:\Python34\python.exe"
if not defined PY if exist "%SystemDrive%\Python34\python.exe" set PY="%SystemDrive%\Python34\python.exe"
if not defined PY if exist "%ProgramFiles%\Python34\python.exe" set PY="%ProgramFiles%\Python34\python.exe"
if defined PY goto bulundu
py -3.4 -c "import sys" >nul 2>&1
if not errorlevel 1 set "PY=py -3.4"
if defined PY goto bulundu
python -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, 3) else 1)" >nul 2>&1
if not errorlevel 1 set "PY=python"
if defined PY goto bulundu

echo.
echo [HATA] Python 3.4 bulunamadi.
echo.
echo  Windows XP icin Python 3.4.4 (32-bit) kurun:
echo    https://www.python.org/ftp/python/3.4.4/python-3.4.4.msi
echo  Kurulumda varsayilan klasoru (C:\Python34) degistirmeyin ve
echo  "Tcl/Tk" bilesenini kaldirmayin. Ayrinti: README.md
echo.
pause
goto :eof

:bulundu
