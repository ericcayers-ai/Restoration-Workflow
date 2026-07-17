@echo off
setlocal
cd /d "%~dp0"
title Restoration Workflow

echo.
echo  Restoration Workflow
echo  --------------------
echo  Starting local server and opening your browser...
echo  Close this window to stop the app.
echo.

if not exist "%~dp0RestorationWorkflow.exe" (
  echo  ERROR: RestorationWorkflow.exe was not found next to this file.
  echo  Re-run the Windows Setup installer, then try again.
  echo.
  pause
  exit /b 1
)

"%~dp0RestorationWorkflow.exe" %*
set EXITCODE=%ERRORLEVEL%

echo.
if not "%EXITCODE%"=="0" (
  echo  The app exited with an error ^(code %EXITCODE%^).
) else (
  echo  App closed.
)
echo.
pause
exit /b %EXITCODE%
