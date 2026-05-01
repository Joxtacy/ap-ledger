@echo off
REM Windows launcher. Double-click in Explorer to open a console window
REM and run the ap-text-client.exe that lives next to this script. If the
REM binary exits with a non-zero status (e.g. you cancelled at the prompt
REM or hit a connection error), pause so you can read the message before
REM the window closes.
cd /d "%~dp0"
ap-text-client.exe
if %ERRORLEVEL% NEQ 0 (
  echo.
  echo ap-text-client exited with status %ERRORLEVEL%. Press any key to close.
  pause >nul
)
