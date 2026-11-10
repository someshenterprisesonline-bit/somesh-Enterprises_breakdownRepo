@echo off
rem Reloads only demo bills on a stopped instance; an existing server is reused safely.
setlocal EnableExtensions DisableDelayedExpansion
call "%~dp0START SOMESH ENTERPRISES.bat" --demo %*
exit /b %ERRORLEVEL%
