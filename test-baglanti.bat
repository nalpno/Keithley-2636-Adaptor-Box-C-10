@echo off
setlocal
cd /d "%~dp0"
call "%~dp0_python_bul.bat"
if not defined PY goto :eof
%PY% baglanti_testi.py %*
echo.
pause
