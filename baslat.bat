@echo off
setlocal
cd /d "%~dp0"
call "%~dp0_python_bul.bat"
if not defined PY goto :eof
echo Program baslatiliyor... (bu pencereyi kapatmayin)
%PY% program.py %*
if errorlevel 1 (
    echo.
    echo Program hata ile kapandi. Yukaridaki mesaji kontrol edin.
    pause
)
