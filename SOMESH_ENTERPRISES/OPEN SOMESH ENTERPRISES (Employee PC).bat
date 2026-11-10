@echo off
rem ==================================================================
rem  SOMESH ENTERPRISES - EMPLOYEE PC launcher (client only)
rem  Opens the office app that runs on the Admin PC in Google Chrome.
rem  It does NOT start a server or a database and needs no Python,
rem  MySQL or Node.js. The only thing it may install is the office
rem  HTTPS certificate (office-ca.crt, for this Windows user) when that
rem  file sits next to this one.
rem  The address comes from the first argument or from
rem  somesh-server-url.txt next to this file, and is remembered there.
rem ==================================================================
setlocal EnableExtensions DisableDelayedExpansion
title SOMESH ENTERPRISES - Employee PC
pushd "%~dp0"
set "URL=%~1"
if not defined URL if exist "somesh-server-url.txt" set /p URL=<"somesh-server-url.txt"
if defined URL goto haveurl
echo.
echo  Type the address shown in the SERVER MODE window on the Admin PC,
echo  for example  https://192.168.1.20:8443  or  http://192.168.1.20:8080
echo.
set /p "URL= Address: "
if not defined URL goto nourl

:haveurl
if "%URL:~-1%"=="/" set "URL=%URL:~0,-1%"
echo %URL%| findstr /r /i "^https*://[A-Za-z0-9.:-]*$" >nul
if errorlevel 1 goto badurl
>"somesh-server-url.txt" echo %URL%

if not exist "office-ca.crt" goto check
certutil -user -verifystore Root "SOMESH ENTERPRISES Office CA" >nul 2>nul
if not errorlevel 1 goto check
echo  Installing the office HTTPS certificate for this Windows user.
echo  If Windows asks whether to install it, click Yes.
certutil -user -addstore Root "office-ca.crt" >nul
if errorlevel 1 echo  [!] The certificate was not installed; HTTPS pages will show a warning.

:check
set "CODE="
for /f %%C in ('curl.exe -s --ssl-no-revoke -o nul -m 6 -w "%%{http_code}" "%URL%/api/health" 2^>nul') do set "CODE=%%C"
if "%CODE%"=="200" goto open
echo.
echo  [!] Cannot reach %URL% right now (result %CODE%).
echo      - Is the SERVER MODE window open on the Admin PC?
echo      - Is this PC connected to the office network?
echo      - For an https address, is office-ca.crt next to this file?
echo  Chrome opens anyway so you can see the page when it is back.
echo.
timeout /t 5 >nul

:open
set "CHROME="
for %%P in ("%ProgramFiles%\Google\Chrome\Application\chrome.exe" "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" "%LocalAppData%\Google\Chrome\Application\chrome.exe") do if not defined CHROME if exist "%%~P" set "CHROME=%%~P"
if defined CHROME goto chrome
start "" "%URL%"
goto done
:chrome
start "" "%CHROME%" "%URL%"
goto done

:badurl
echo.
echo  [!] "%URL%" does not look like an address. Use the one shown on the
echo      Admin PC, for example https://192.168.1.20:8443
del "somesh-server-url.txt" >nul 2>nul
pause
goto done

:nourl
echo  No address entered.
pause

:done
popd
endlocal
exit /b 0
