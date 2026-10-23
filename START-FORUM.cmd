@echo off
cd /d "%~dp0"
echo Starting the Louw forum at http://127.0.0.1:5000/
echo Keep this window open while using the forum.
echo.
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" app.py run
) else (
  python app.py run
)
echo.
echo The forum server has stopped. Press any key to close this window.
pause >nul
