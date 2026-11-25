@echo off
chcp 65001 >nul
setlocal
rem ============================================================================
rem  koer_analyse.bat: kører trackpoint-værktøjet på analysen i denne mappe.
rem  Dobbeltklik, og vælg et trin. Ret kun variablerne herunder.
rem ============================================================================

rem Perioder: "A B" = før og efter.  "A" = kun én periode (ingen sammenligning).
set PERIODER=A B

rem Programmappen i værktøjet (værktøjsmappen\program, med analyse_v2.2.py). Sat af ny_analyse.bat.
set "VAERKTOEJ=__VAERKTOEJ__"

rem ---- herunder skal intet rettes ----------------------------------------------
set "MAPPE=%~dp0"
set "CONFIG=%MAPPE%config.yaml"
set "UD=%MAPPE%resultat"
rem config.yaml + bump-vinduer regnet ud fra radius_m (laves igen ved valg 3 og 4)
set "BEREGNET=%UD%\config_beregnet.yaml"
set "FORBERED=%VAERKTOEJ%\skabeloner\forbered.py"
set PYTHONUTF8=1
set HARB=0
set "BARG="
echo %PERIODER% | find "B" >nul && set HARB=1
if %HARB%==1 set BARG=--b "%UD%\B"

where python >nul 2>&1 || (echo Python blev ikke fundet. Installér Python 3.10 eller nyere, og prøv igen. & pause & exit /b 1)
if not exist "%VAERKTOEJ%\analyse_v2.2.py" (echo Værktøjsmappen findes ikke: "%VAERKTOEJ%" & echo Ret VAERKTOEJ øverst i koer_analyse.bat. & pause & exit /b 1)

echo.
echo  Analyse: %MAPPE%
echo  Perioder: %PERIODER%
echo.
echo  0 = Første gang: installér Python-pakker og test værktøjet (ca. 1 min)
echo  1 = Stoppesteder pr. retning med forslag (skriver stopnavne.txt)
echo  2 = Prøvekørsel på 300 ture (ca. 1 min)
echo  3 = Fuld analyse, turtabel og rapport (ca. 10-30 min)
echo  4 = Byg rapporten igen (efter du har rettet titel og tekster i config.yaml)
echo  5 = Tilføj resultat\konklusion.yaml til de nationale analysekonklusioner (efter 6 og udfyldning)
echo  6 = Lav din konklusionsfil med rapportens nøgletal (resultat\konklusion.yaml)
echo.
rem Et tal som argument (fx  koer_analyse.bat 3) springer menuen over.
set "VALG="
set "ARG=%~1"
if defined ARG set /a VALG=%ARG%+1
if defined VALG goto valgt
choice /c 0123456 /n /m "Vælg 0-6: "
set VALG=%errorlevel%
:valgt
if %VALG%==1 goto installer
if %VALG%==2 goto stopnavne
if %VALG%==3 goto proeve
if %VALG%==4 goto fuld
if %VALG%==5 goto rapport
if %VALG%==6 goto konklusioner
if %VALG%==7 goto konklusionsfil
goto slut

:konklusionsfil
if not exist "%UD%\rapportdata.json" goto mangler
python "%VAERKTOEJ%\lav_konklusion.py" --rapportdata "%UD%\rapportdata.json" --out "%UD%\konklusion.yaml" || goto fejl
echo.
echo Udfyld felterne med UDFYLD i resultat\konklusion.yaml, gem filen, og vælg 5.
if not defined ARG start "" notepad "%UD%\konklusion.yaml"
goto slut

:konklusioner
if exist "%UD%\konklusion.yaml" (
  python "%VAERKTOEJ%\lav_konklusioner_html.py" --tilfoej "%UD%\konklusion.yaml" || goto fejl
) else (
  echo resultat\konklusion.yaml findes ikke ^(vælg 6 først^). Laver kun oversigten igen.
  python "%VAERKTOEJ%\lav_konklusioner_html.py" || goto fejl
)
echo.
echo Oversigten er klar: nationale_analysekonklusioner.html og .md i værktøjsmappen, din fil i analyser\.
echo Del din fil og de to oversigtsfiler via repoet (pull request eller issue).
if not defined ARG start "" "%VAERKTOEJ%\..\nationale_analysekonklusioner.html"
goto slut

:installer
python -m pip install -r "%VAERKTOEJ%\requirements.txt" || goto fejl
python -m pip install pytest || goto fejl
python -m pytest "%VAERKTOEJ%\tests" -q -p no:cacheprovider || goto fejl
echo.
echo Værktøjet virker.
goto slut

:stopnavne
echo Læser stoppesteder pr. retning fra data\A (ca. 1 min) ...
python "%FORBERED%" stopnavne --config "%CONFIG%" --out "%MAPPE%stopnavne.txt" || goto fejl
echo Stoppestederne pr. retning står i stopnavne.txt, med forslag til start og slut.
echo Kopiér dem ind i config.yaml (punkt 4). Står der OBS nederst, så byt p1 og p2 først.
if not defined ARG start "" notepad "%MAPPE%stopnavne.txt"
goto slut

:proeve
python "%VAERKTOEJ%\analyse_v2.2.py" --config "%CONFIG%" --period A --max-trips 300 --output-dir "%UD%\proeve" || goto fejl
echo.
echo Se resultat\proeve\kvalitet.md: hvor mange ture blev beholdt, og hvorfor blev andre kasseret?
echo  - "flag afstand > 200 m" ved næsten alle ture: byt p1 og p2 i config.yaml.
echo  - "stop_ikke_fundet" ved næsten alle ture: ret stopnavnene i config.yaml (punkt 4).
echo Ret, og kør prøven igen, til næsten alle ture er beholdt uden afstandsflag.
if not defined ARG start "" notepad "%UD%\proeve\kvalitet.md"
goto slut

:fuld
python "%FORBERED%" config --config "%CONFIG%" --out "%BEREGNET%" || goto fejl
call :periode A || goto fejl
if %HARB%==0 goto turtabel
call :periode B || goto fejl
:turtabel
echo ==== Turtabel og overblik ====
python "%VAERKTOEJ%\turtabel.py" --config "%BEREGNET%" --a "%UD%\A" %BARG% --out "%UD%" || goto fejl
:zonetid
echo ==== Zonetid ====
python "%VAERKTOEJ%\zonetid.py" --config "%BEREGNET%" --a "%UD%\A" %BARG% --out "%UD%" || goto fejl
goto rapport

:rapport
if not exist "%UD%\zonetid.json" goto mangler
if not exist "%UD%\turtabel.csv" goto mangler
echo ==== Rapport ====
python "%FORBERED%" config --config "%CONFIG%" --out "%BEREGNET%" || goto fejl
python "%VAERKTOEJ%\rapport\lav_rapportdata_v1.2.py" --config "%BEREGNET%" --a "%UD%\A" %BARG% --turtabel "%UD%\turtabel.csv" --zonetid "%UD%\zonetid.json" --out "%UD%\rapportdata.json" || goto fejl
python "%VAERKTOEJ%\rapport\byg_rapport.py" --data "%UD%\rapportdata.json" --out "%UD%\rapport.html" || goto fejl
echo.
echo Rapporten er klar: resultat\rapport.html
echo Køretid pr. tur og time: resultat\turtabel.csv (Excel/Power BI) og resultat\overblik.md
if not defined ARG start "" "%UD%\rapport.html"
goto slut

:periode
echo.
echo ==== Periode %1: analyse (ca. 4-10 min) ====
python "%VAERKTOEJ%\analyse_v2.2.py" --config "%BEREGNET%" --period %1 --output-dir "%UD%\%1" --export-segments || exit /b 1
echo ==== Periode %1: komfort ====
python "%VAERKTOEJ%\komfort_v1.1.py" --segments "%UD%\%1\segmenter.csv" --config "%BEREGNET%" --out "%UD%\%1\komfort.csv" || exit /b 1
exit /b 0

:mangler
echo Kør først 3 = fuld analyse.
goto slut

:fejl
echo.
echo Der skete en fejl. Læs beskeden ovenfor. Hjælp: program\README.md i værktøjsmappen, afsnit "Hurtig fejlfinding".
if not defined ARG pause
exit /b 1

:slut
echo.
if not defined ARG pause
