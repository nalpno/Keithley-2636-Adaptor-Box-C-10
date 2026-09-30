@echo off
setlocal
cd /d "%~dp0"
call "%~dp0_python_bul.bat"
if not defined PY goto :eof
echo Simulasyon modu: gercek cihaz kullanilmaz.
%PY% program.py --simulate
if errorlevel 1 pause
