@echo off
rem ==================================================================
rem  SOMESH ENTERPRISES - SERVER MODE (run this on the Admin PC only)
rem  1. finds Python 3.9+ (installs Python 3.12 if missing)
rem  2. installs the required packages if missing (backend\requirements.txt)
rem  3. backend\launcher.py checks settings, HTTPS files, database
rem     integrity and ports, backs up the database, then starts
rem     backend\app.py (frontend + API + live updates on one port),
rem     prints the office LAN address and opens Chrome.
rem  It reuses a running server, never stops other programs and
rem  never resets or reseeds data.
rem  Employee PCs use "OPEN SOMESH ENTERPRISES (Employee PC).bat",
rem  which only opens Chrome at this PC's address.
rem  Data is kept in .\data and files in .\storage (not in git).
rem ==================================================================
:main
setlocal EnableExtensions DisableDelayedExpansion
set "RC=1"
set "NOPAUSE="
for %%A in (%*) do if /i "%%~A"=="--no-pause" set "NOPAUSE=1"
title SOMESH ENTERPRISES - SERVER MODE
color F0
pushd "%~dp0"
if errorlevel 1 exit /b 1
echo.
echo  ==========================================================
echo     SOMESH ENTERPRISES  -  SERVER MODE (Admin PC)
echo  ==========================================================
echo.
echo  Folder: %CD%
echo.

rem ---------- 1. Python
set "PY="
call :findpy
if defined PY goto havepy

echo  Python is not installed on this PC. Installing Python 3.12 - this takes 1 to 3 minutes...
where winget >nul 2>nul
if errorlevel 1 goto download
winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
call :findpy
if defined PY goto havepy

:download
echo  Downloading Python 3.12 from python.org...
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = 'Tls12'; Invoke-WebRequest -UseBasicParsing -Uri 'https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe' -OutFile ($env:TEMP + '\se-python-setup.exe')"
if not exist "%TEMP%\se-python-setup.exe" goto nopython
echo  Installing Python...
"%TEMP%\se-python-setup.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_pip=1
call :findpy
if defined PY goto havepy

:nopython
echo.
echo  [!] Could not install Python automatically.
echo      Install it from https://www.python.org/downloads/
echo      and tick "Add python.exe to PATH" during setup.
echo      Then double-click START SOMESH ENTERPRISES.bat again.
goto done

:havepy
echo  [OK] Python found: %PY%

rem ---------- 2. Required packages
if not exist "backend\requirements.txt" goto nofiles
if not exist "backend\app.py" goto nofiles
if not exist "backend\launcher.py" goto nofiles
if not exist "frontend\index.html" goto nofiles
%PY% -c "import openpyxl, reportlab" >nul 2>nul
if not errorlevel 1 goto haveparts
echo  Installing required packages - one time only...
%PY% -m ensurepip --upgrade >nul 2>nul
%PY% -m pip install --user --disable-pip-version-check -r backend\requirements.txt
%PY% -c "import openpyxl, reportlab" >nul 2>nul
if not errorlevel 1 goto haveparts
echo.
echo  [!] Could not install the required packages.
echo      Check the internet connection and try again.
goto done

:haveparts
echo  [OK] Required packages installed
echo.
echo  Starting the server. Chrome opens in a few seconds.
echo  Keep this window open while people use the app: closing it
echo  stops the app for every office PC.
echo.

rem ---------- 3. Run
%PY% backend\launcher.py %*
set "RC=%ERRORLEVEL%"
echo.
echo  The app has stopped.
goto done

:nofiles
echo.
echo  [!] The backend or frontend folder is missing next to this file.
echo      Expected: backend\app.py, backend\requirements.txt, frontend\index.html
echo      Unzip the whole folder first (right-click the zip, Extract All),
echo      or clone the whole repository, then double-click this file there.
goto done

:done
echo.
echo  You can close this window.
if not "%RC%"=="0" if not defined NOPAUSE pause
popd
endlocal & exit /b %RC%

rem ---------- helpers
:findpy
call :try py -3
if defined PY exit /b 0
call :try python
if defined PY exit /b 0
call :try python3
if defined PY exit /b 0
call :try "%LOCALAPPDATA%\Programs\Python\Launcher\py.exe" -3
if defined PY exit /b 0
for %%V in (313 312 311 310 39) do call :tryfile "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
if defined PY exit /b 0
for %%V in (313 312 311 310 39) do call :tryfile "%ProgramFiles%\Python%%V\python.exe"
exit /b 0

:tryfile
if defined PY exit /b 0
if not exist "%~1" exit /b 0
call :try "%~1"
exit /b 0

:try
%* -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 7)" >nul 2>nul
if errorlevel 1 exit /b 0
set PY=%*
exit /b 0
