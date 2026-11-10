@echo off
rem SOMESH ENTERPRISES - back up the database and private settings now (Admin PC; safe while the app is running).
rem Backups go to data\backups\manual-YYYYMMDD-HHMMSS. Pass --dest "E:\SOMESH Backups" to use another drive.
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0"
set "PY="
py -3 -c "import sys" >nul 2>nul && set "PY=py -3"
if not defined PY python -c "import sys" >nul 2>nul && set "PY=python"
if not defined PY goto nopy
%PY% tools\backup_db.py %*
set "RC=%ERRORLEVEL%"
goto done
:nopy
echo Python was not found. Run START SOMESH ENTERPRISES.bat once first.
set "RC=1"
:done
pause
popd
endlocal & exit /b %RC%
