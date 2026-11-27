@echo off
chcp 65001 >nul
setlocal
rem ============================================================================
rem  koer_analyse.bat: kører trackpoint-værktøjet på analysen i denne mappe.
rem  Dobbeltklik, og vælg et trin. Ret kun variablerne herunder.
rem ============================================================================

rem Perioder: auto = som i config.yaml (A, og B hvis config.yaml har data for B). Eller A B, eller A (uden anførselstegn).
set PERIODER=auto

rem Programmappen i værktøjet (værktøjsmappen\program). Sat af ny_analyse.bat.
set "VAERKTOEJ=__VAERKTOEJ__"

rem ---- herunder skal intet rettes ----------------------------------------------
rem Programmerne, kæden kalder (ét sted: en ny version af et program rettes kun her).
set "ANALYSE=analyse_v2.2.py"
set "KOMFORT=komfort_v1.1.py"
set "TURTABEL=turtabel.py"
set "ZONETID=zonetid.py"
rem Rapportdata v1.3 regner også standsning ved stop (standsning_v1.0.py) ud fra segmenter.csv og rapport.stoppesteder: intet eget trin.
set "RAPPORTDATA=rapport\lav_rapportdata_v1.3.py"
set "BYGRAPPORT=rapport\byg_rapport.py"
set "KRYDSRAPPORT=rapport\lav_kryds_rapport.py"
set "KONKLUSION=lav_konklusion.py"
set "KONKLUSIONER=lav_konklusioner_html.py"
set "FORBERED=%VAERKTOEJ%\skabeloner\forbered.py"
set "TJEK=%VAERKTOEJ%\skabeloner\tjek_config.py"

set "MAPPE=%~dp0"
set "CONFIG=%MAPPE%config.yaml"
set "UD=%MAPPE%resultat"
rem config.yaml + absolutte stier, bump-vinduer og fundne stoppesteder (laves igen ved valg 2, 3 og 4)
set "BEREGNET=%UD%\config_beregnet.yaml"
set PYTHONUTF8=1

where python >nul 2>&1 || (echo Python blev ikke fundet. Installér Python 3.10 eller nyere, og prøv igen. & pause & exit /b 1)
if not exist "%VAERKTOEJ%\%ANALYSE%" (echo Værktøjsmappen findes ikke: "%VAERKTOEJ%" & echo Ret VAERKTOEJ øverst i koer_analyse.bat. & pause & exit /b 1)

rem Analysetype, perioder og strækninger fra config.yaml (en fejl i filen meldes af tjekket nedenfor)
set "CFG_TYPE=straekning"
set "CFG_PERIODER=A"
set "CFG_STRAEKNINGER="
set "CFG_ANTAL=1"
set "CFG_ELEMENTER=1"
for /f "usebackq tokens=1,* delims==" %%a in (`python "%FORBERED%" info --config "%CONFIG%" 2^>nul`) do set "%%a=%%b"
set PERIODER=%PERIODER:"=%
if /i "%PERIODER%"=="auto" set "PERIODER=%CFG_PERIODER%"
if not defined PERIODER set PERIODER=A
set HARB=0
set "BARG="
if not "%PERIODER:B=%"=="%PERIODER%" set HARB=1
if %HARB%==1 set BARG=--b "%UD%\B"
set PROEVE_TURE=300
if /i "%CFG_TYPE%"=="kryds" set PROEVE_TURE=2000

echo.
echo  Analyse: "%MAPPE%"
echo  Type: %CFG_TYPE%   Perioder: %PERIODER%   Strækninger: %CFG_STRAEKNINGER%
echo.
echo  0 = Første gang: installér Python-pakker og test værktøjet (ca. 1 min)
echo  1 = Stoppesteder pr. retning og kontrolkort (skriver stopnavne.txt og kontrolkort.html)
echo  2 = Prøvekørsel på %PROEVE_TURE% ture (ca. 1 min)
echo  3 = Fuld analyse, turtabel og rapport (ca. 10-30 min)
echo  4 = Byg rapporten igen (efter du har rettet titel og tekster i config.yaml)
echo  5 = Tilføj resultat\konklusion.yaml til de nationale analysekonklusioner (efter 6 og udfyldning)
echo  6 = Lav din konklusionsfil med rapportens nøgletal (resultat\konklusion.yaml)
echo  7 = Tjek config.yaml og tegn kontrolkortet igen
echo.
rem Et tal som argument (fx  koer_analyse.bat 3) springer menuen over.
set "VALG="
set "ARG=%~1"
if defined ARG for %%v in (0 1 2 3 4 5 6 7) do if "%ARG%"=="%%v" set /a VALG=%%v+1
if defined ARG if not defined VALG (echo Ukendt valg: %ARG%. Skriv et tal fra 0 til 7, fx  koer_analyse.bat 3 & exit /b 1)
if defined VALG goto valgt
choice /c 01234567 /n /m "Vælg 0-7: "
set VALG=%errorlevel%
:valgt
if %VALG%==1 goto installer
if %VALG%==2 goto stopnavne
if %VALG%==3 goto proeve
if %VALG%==4 goto fuld
if %VALG%==5 goto rapport
if %VALG%==6 goto konklusioner
if %VALG%==7 goto konklusionsfil
if %VALG%==8 goto tjek
goto slut

:tjek
python "%TJEK%" --config "%CONFIG%" --perioder "%PERIODER%"
set TJEKFEJL=%errorlevel%
python "%FORBERED%" kort --config "%CONFIG%" --out "%MAPPE%kontrolkort.html"
if not defined ARG start "" "%MAPPE%kontrolkort.html"
if not %TJEKFEJL%==0 goto fejl
goto slut

:konklusionsfil
if /i "%CFG_TYPE%"=="kryds" (
  if not exist "%UD%\overblik.csv" goto mangler
  python "%VAERKTOEJ%\%KONKLUSION%" --overblik "%UD%\overblik.csv" --config "%CONFIG%" --out "%UD%\konklusion.yaml" || goto fejl
  goto konklusionsfil_klar
)
if not exist "%UD%\rapportdata.json" goto mangler
if %CFG_ANTAL% GTR 1 (
  for %%s in (%CFG_STRAEKNINGER%) do python "%VAERKTOEJ%\%KONKLUSION%" --rapportdata "%UD%\rapportdata.json" --straekning %%s --out "%UD%\konklusion_%%s.yaml" || goto fejl
  echo.
  echo Én konklusionsfil pr. strækning: resultat\konklusion_^<id^>.yaml. Udfyld felterne med UDFYLD, og vælg 5.
  goto slut
)
python "%VAERKTOEJ%\%KONKLUSION%" --rapportdata "%UD%\rapportdata.json" --out "%UD%\konklusion.yaml" || goto fejl
:konklusionsfil_klar
echo.
echo Udfyld felterne med UDFYLD i resultat\konklusion.yaml, gem filen, og vælg 5.
if not defined ARG start "" notepad "%UD%\konklusion.yaml"
goto slut

:konklusioner
set FUNDET=0
for %%f in ("%UD%\konklusion*.yaml") do (
  set FUNDET=1
  python "%VAERKTOEJ%\%KONKLUSIONER%" --tilfoej "%%f" || goto fejl
)
if %FUNDET%==0 (
  echo resultat\konklusion.yaml findes ikke ^(vælg 6 først^). Laver kun oversigten igen.
  python "%VAERKTOEJ%\%KONKLUSIONER%" || goto fejl
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
python "%TJEK%" --config "%CONFIG%" --trin stopnavne --perioder "%PERIODER%" || goto fejl
echo Læser stoppesteder pr. retning fra data\A (ca. 1 min pr. GB) ...
python "%FORBERED%" stopnavne --config "%CONFIG%" --out "%MAPPE%stopnavne.txt" || goto fejl
python "%FORBERED%" kort --config "%CONFIG%" --out "%MAPPE%kontrolkort.html" || goto fejl
echo Stoppestederne pr. retning står i stopnavne.txt, med forslag til start og slut.
echo Kopiér dem ind i config.yaml (stops). Står der OBS, så ret point_order først, og vælg 1 igen.
echo Tjek alle punkter og stoppesteder på kontrolkort.html, og ret koordinaterne i config.yaml, hvis de ligger forkert.
if not defined ARG start "" notepad "%MAPPE%stopnavne.txt"
if not defined ARG start "" "%MAPPE%kontrolkort.html"
goto slut

:proeve
python "%TJEK%" --config "%CONFIG%" --trin proeve --perioder "%PERIODER%" || goto fejl
python "%FORBERED%" config --config "%CONFIG%" --out "%BEREGNET%" || goto fejl
python "%VAERKTOEJ%\%ANALYSE%" --config "%BEREGNET%" --period A --max-trips %PROEVE_TURE% --output-dir "%UD%\proeve" || goto fejl
echo.
echo Se resultat\proeve\kvalitet.md: hvor mange ture blev beholdt, og hvorfor blev andre kasseret?
echo  - "flag afstand > 200 m" ved næsten alle ture: retningen er byttet om (vælg 1 og læs OBS).
echo  - "stop_ikke_fundet" ved næsten alle ture: ret stopnavnene i config.yaml (stops).
if /i "%CFG_TYPE%"=="kryds" echo  - Kryds: ture i den anden retning kasseres som ingen_point_order_direction_N; det er rigtigt.
echo Ret, og kør prøven igen, til næsten alle ture er beholdt uden afstandsflag.
if not defined ARG start "" notepad "%UD%\proeve\kvalitet.md"
goto slut

:fuld
python "%TJEK%" --config "%CONFIG%" --trin fuld --perioder "%PERIODER%" || goto fejl
python "%FORBERED%" config --config "%CONFIG%" --out "%BEREGNET%" --laes-data || goto fejl
for %%p in (%PERIODER%) do (
  call :periode %%p || goto fejl
)
echo ==== Turtabel og overblik ====
python "%VAERKTOEJ%\%TURTABEL%" --config "%BEREGNET%" --a "%UD%\A" %BARG% --out "%UD%" || goto fejl
if /i "%CFG_TYPE%"=="kryds" goto krydsrapport
if exist "%UD%\zonetid.json" del "%UD%\zonetid.json"
if "%CFG_ELEMENTER%"=="0" (
  echo ==== Zonetid springes over: ingen elementer i strækningerne ====
  goto rapport_byg
)
echo ==== Zonetid ====
python "%VAERKTOEJ%\%ZONETID%" --config "%BEREGNET%" --a "%UD%\A" %BARG% --out "%UD%" || goto fejl
goto rapport_byg

:rapport
python "%TJEK%" --config "%CONFIG%" --trin rapport --perioder "%PERIODER%" || goto fejl
if not exist "%UD%\turtabel.csv" goto mangler
if /i "%CFG_TYPE%"=="kryds" goto krydsrapport
python "%FORBERED%" config --config "%CONFIG%" --out "%BEREGNET%" || goto fejl
:rapport_byg
echo ==== Rapport ====
set "ZARG="
if exist "%UD%\zonetid.json" set ZARG=--zonetid "%UD%\zonetid.json"
python "%VAERKTOEJ%\%RAPPORTDATA%" --config "%BEREGNET%" --a "%UD%\A" %BARG% --turtabel "%UD%\turtabel.csv" %ZARG% --out "%UD%\rapportdata.json" || goto fejl
python "%VAERKTOEJ%\%BYGRAPPORT%" --data "%UD%\rapportdata.json" --out "%UD%\rapport.html" || goto fejl
echo.
echo Rapporten er klar: resultat\rapport.html
echo Køretid pr. tur og time: resultat\turtabel.csv (Excel/Power BI) og resultat\overblik.md
if not defined ARG start "" "%UD%\rapport.html"
goto slut

:krydsrapport
echo ==== Kryds-rapport ====
python "%FORBERED%" config --config "%CONFIG%" --out "%BEREGNET%" || goto fejl
python "%VAERKTOEJ%\%KRYDSRAPPORT%" --config "%BEREGNET%" --turtabel "%UD%\turtabel.csv" --out "%UD%\kryds_rapport.html" || goto fejl
echo.
echo Kryds-rapporten er klar: resultat\kryds_rapport.html
echo Køretid pr. tur og stykke: resultat\turtabel.csv (Excel/Power BI) og pr. time: resultat\overblik.md
if not defined ARG start "" "%UD%\kryds_rapport.html"
goto slut

:periode
echo.
echo ==== Periode %1: analyse (ca. 4-10 min) ====
python "%VAERKTOEJ%\%ANALYSE%" --config "%BEREGNET%" --period %1 --output-dir "%UD%\%1" --export-segments || exit /b 1
if /i "%CFG_TYPE%"=="kryds" exit /b 0
echo ==== Periode %1: komfort ====
python "%VAERKTOEJ%\%KOMFORT%" --segments "%UD%\%1\segmenter.csv" --config "%BEREGNET%" --out "%UD%\%1\komfort.csv" || exit /b 1
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
