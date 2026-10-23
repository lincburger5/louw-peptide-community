@echo off
cd /d "%~dp0"
set "ADB_EXE=%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"
if not exist "%ADB_EXE%" (
  echo Android platform-tools were not found. Use START-FORUM.cmd for laptop access.
  pause
  exit /b 1
)
"%ADB_EXE%" reverse tcp:5000 tcp:5000
if errorlevel 1 (
  echo Unlock the phone and allow USB debugging, then try again.
  pause
  exit /b 1
)
echo Phone connection is ready. Keep this cable connected.
echo Starting the forum at http://127.0.0.1:5000/
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" app.py run
) else (
  python app.py run
)
pause
