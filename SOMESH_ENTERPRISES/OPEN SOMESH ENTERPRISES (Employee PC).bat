@echo off
rem ==================================================================
rem  SOMESH ENTERPRISES - EMPLOYEE PC launcher (client only)
rem  Opens the office app that runs on the Admin PC in Google Chrome.
rem  It does NOT start a server or a database and needs no Python,
rem  MySQL, Node.js or Git. Every employee uses the one shared database
rem  on the Admin PC through its HTTPS address.
rem
rem  1. Address: first argument, else somesh-server-url.txt next to this
rem     file (remembered there), else typed in.
rem  2. HTTPS: if the office CA certificate is not trusted yet, it checks
rem     that office-ca.crt next to this file is exactly the office CA
rem     (SHA-256 fingerprint pinned below by tools\make_office_cert.py),
rem     shows the fingerprint and installs it for this Windows user
rem     only after you confirm. Certificate checks are never switched off.
rem  3. Checks the Admin PC answers (with full HTTPS verification), shows
rem     a clear message if not, then opens Chrome at the address.
rem ==================================================================
setlocal EnableExtensions DisableDelayedExpansion
rem SHA-256 of the office CA (DER). Filled in for the Employee PC Kit by tools\make_office_cert.py.
set "CA_SHA256="
set "CA_NAME=SOMESH ENTERPRISES Office CA"
title SOMESH ENTERPRISES - Employee PC
pushd "%~dp0"
set "RC=0"
set "TESTMODE="
if "%SOMESH_LAUNCHER_TEST%"=="1" set "TESTMODE=1"
echo.
echo  ==========================================================
echo     SOMESH ENTERPRISES  -  Employee PC
echo  ==========================================================
echo.

rem ---------- 1. Address of the Admin PC
set "URL=%~1"
if not defined URL if exist "somesh-server-url.txt" set /p URL=<"somesh-server-url.txt"
if defined URL goto haveurl
if defined TESTMODE goto nourl
echo  Type the address shown in the SERVER MODE window on the Admin PC,
echo  for example  https://192.168.1.4:8443
echo.
set /p "URL= Address: "
if not defined URL goto nourl

:haveurl
if "%URL:~-1%"=="/" set "URL=%URL:~0,-1%"
echo %URL%| findstr /r /i "^https*://[A-Za-z0-9.:-]*$" >nul
if errorlevel 1 goto badurl
>"somesh-server-url.txt" echo %URL%
echo  Admin PC address: %URL%
set "HTTPS="
if /i "%URL:~0,8%"=="https://" set "HTTPS=1"
if not defined HTTPS goto check

rem ---------- 2. Office HTTPS certificate
if not exist "office-ca.crt" goto check
if not defined CA_SHA256 goto nopin
set "SE_CA=%CD%\office-ca.crt"
set "SE_PIN=%CA_SHA256%"
set "SE_NAME=%CA_NAME%"
set "CERTSTATE="
set "CERTHASH="
call :certstate
if "%CERTSTATE%"=="TRUSTED" echo  [OK] Office certificate is trusted on this PC
if "%CERTSTATE%"=="TRUSTED" goto check
if "%CERTSTATE%"=="UNTRUSTED" goto askcert
echo.
echo  [!] office-ca.crt next to this file is NOT the office certificate
echo      (result: %CERTSTATE% %CERTHASH%). It was not installed.
echo      Ask the office admin for a fresh Employee PC Kit.
echo.
goto check

:askcert
echo.
echo  This PC does not trust the office HTTPS certificate yet.
echo    Name:        %CA_NAME%
echo    SHA-256:     %CERTHASH%
echo  It matches the fingerprint in this Employee PC Kit. Installing it lets
echo  Chrome open the office address securely (this Windows user only).
set "ANSWER=N"
if defined TESTMODE goto askcertdone
choice /c YN /n /m " Install the office certificate now? [Y/N] "
if not errorlevel 2 set "ANSWER=Y"
:askcertdone
if /i not "%ANSWER%"=="Y" echo  Not installed. Chrome will warn that the connection is not private.
if /i not "%ANSWER%"=="Y" goto check
echo  If Windows shows a Security Warning about installing it, click Yes.
certutil -user -addstore Root "office-ca.crt" >nul
call :certstate
if "%CERTSTATE%"=="TRUSTED" echo  [OK] Office certificate installed and trusted
if not "%CERTSTATE%"=="TRUSTED" echo  [!] The certificate was not installed; HTTPS pages will show a warning.
goto check

:nopin
echo  [!] office-ca.crt is here but this launcher has no pinned fingerprint,
echo      so the certificate is not installed. Use the Employee PC Kit made by
echo      tools\make_office_cert.py on the Admin PC (certs\employee-pc-kit).

rem ---------- 3. Is the Admin PC reachable? (full certificate verification)
:check
where curl.exe >nul 2>nul
if errorlevel 1 goto open
set "CODE="
set "HEALTH=%TEMP%\somesh-health-%RANDOM%.txt"
curl.exe -s --ssl-no-revoke -o nul -m 6 -w "%%{http_code}" "%URL%/api/health" >"%HEALTH%" 2>nul
set "CURLRC=%ERRORLEVEL%"
if exist "%HEALTH%" set /p CODE=<"%HEALTH%"
del "%HEALTH%" >nul 2>nul
if "%CODE%"=="200" echo  [OK] The office server is answering
if "%CODE%"=="200" goto open
echo.
echo  ----------------------------------------------------------
echo  [!] SOMESH ENTERPRISES cannot be reached at %URL%
if "%CODE%"=="403" echo      The server refused this PC: it is not on an approved office network.
if "%CURLRC%"=="35" goto certfail
if "%CURLRC%"=="60" goto certfail
if "%CURLRC%"=="6" echo      The address could not be found. Check the address with the admin.
if "%CURLRC%"=="7" echo      Nothing answered. Is the SERVER MODE window open on the Admin PC?
if "%CURLRC%"=="28" echo      No answer in time. Is this PC on the office Wi-Fi / network?
goto unreach
:certfail
echo      The connection is not trusted: the office HTTPS certificate is not
echo      installed for this Windows user, or the Admin PC's address changed.
echo      Run this file from the Employee PC Kit and allow the certificate.
:unreach
echo      (details: curl %CURLRC%, HTTP %CODE%)
echo  ----------------------------------------------------------
echo.
set "RC=2"
if defined TESTMODE goto done
choice /c ROQ /n /m " [R] Try again   [O] Open Chrome anyway   [Q] Quit: "
if errorlevel 3 goto done
if errorlevel 2 goto open
set "RC=0"
goto check

rem ---------- 4. Open Chrome
:open
set "RC=0"
if defined TESTMODE echo  OPEN %URL%
if defined TESTMODE goto done
set "CHROME="
for %%P in ("%ProgramFiles%\Google\Chrome\Application\chrome.exe" "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" "%LocalAppData%\Google\Chrome\Application\chrome.exe") do if not defined CHROME if exist "%%~P" set "CHROME=%%~P"
if defined CHROME goto chrome
echo  Google Chrome was not found; opening the default browser instead.
start "" "%URL%"
goto done
:chrome
echo  Opening Chrome...
start "" "%CHROME%" "%URL%"
goto done

:badurl
echo.
echo  [!] "%URL%" does not look like an address. Use the one shown on the
echo      Admin PC, for example https://192.168.1.4:8443
del "somesh-server-url.txt" >nul 2>nul
set "RC=1"
if not defined TESTMODE pause
goto done

:nourl
echo  No address entered.
set "RC=1"
if not defined TESTMODE pause

:done
popd
endlocal & exit /b %RC%

rem ---------- helper: CERTSTATE = TRUSTED / UNTRUSTED / MISMATCH / NOTCA / BADFILE, CERTHASH = SHA-256
:certstate
set "CERTSTATE=BADFILE"
set "CERTHASH="
set "CERTOUT=%TEMP%\somesh-cert-%RANDOM%.txt"
powershell -NoProfile -NonInteractive -Command "try { $c = New-Object Security.Cryptography.X509Certificates.X509Certificate2 $env:SE_CA } catch { 'BADFILE -'; exit }; $h = -join ([Security.Cryptography.SHA256]::Create().ComputeHash($c.RawData) | ForEach-Object { $_.ToString('X2') }); $bc = $c.Extensions | Where-Object { $_.Oid.Value -eq '2.5.29.19' }; if (-not $bc -or -not $bc.CertificateAuthority -or $c.GetNameInfo('SimpleName', $false) -ne $env:SE_NAME) { 'NOTCA ' + $h; exit }; if ($h -ne $env:SE_PIN.ToUpper()) { 'MISMATCH ' + $h; exit }; $t = @(Get-ChildItem Cert:\CurrentUser\Root, Cert:\LocalMachine\Root | Where-Object { $_.Thumbprint -eq $c.Thumbprint }); if ($t.Count) { 'TRUSTED ' + $h } else { 'UNTRUSTED ' + $h }" >"%CERTOUT%" 2>nul
if exist "%CERTOUT%" for /f "usebackq tokens=1,2" %%A in ("%CERTOUT%") do (
  set "CERTSTATE=%%A"
  set "CERTHASH=%%B"
)
del "%CERTOUT%" >nul 2>nul
exit /b 0
