@echo off
chcp 65001 >nul
rem Opretter en ny analysemappe ved siden af værktøjet (trackpoint_analyser\<navn>).
set PYTHONUTF8=1
where python >nul 2>&1 || (echo Python blev ikke fundet. Installér Python 3.10 eller nyere. & pause & exit /b 1)
python "%~dp0program\skabeloner\ny_analyse.py" %*
echo.
pause
