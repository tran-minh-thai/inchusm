@echo off
rem IncHUSM - revision timings on the reference machine (i7-10750H).
rem Usage:  run_i7.bat            (all parts: alt, scale, k)
rem         run_i7.bat alt|scale|k (one part)
rem Needs only Java 17 or newer on PATH. Close other programs before running.
setlocal
cd /d "%~dp0"
if not exist results mkdir results
set JAR=inchusm-revision.jar
set J=java -Xmx16g
set PART=%1
if "%PART%"=="" set PART=all

java -version > results\machine.txt 2>&1
powershell -NoProfile -Command "Get-CimInstance Win32_Processor | Select-Object -ExpandProperty Name; (Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory/1GB" >> results\machine.txt 2>&1
echo started %DATE% %TIME% >> results\machine.txt

if "%PART%"=="alt"   goto ALT
if "%PART%"=="scale" goto SCALE
if "%PART%"=="k"     goto KSENS

:ALT
echo [1/3] Alternative strategies (about 5 minutes)
%J% -cp %JAR% edu.huflit.inchusm.cli.Baselines --snapshot-dir data\elliptic --util data\elliptic\utilities.tsv --minvalue 500 --max-edges 5 --out results\alt_elliptic.csv > results\alt_elliptic.log 2>&1
%J% -cp %JAR% edu.huflit.inchusm.cli.Baselines --snapshot-dir data\aml_k4 --util data\aml_k4\utilities.tsv --minvalue 2000 --max-edges 5 --out results\alt_amlworld.csv > results\alt_amlworld.log 2>&1
%J% -cp %JAR% edu.huflit.inchusm.cli.Baselines --snapshot-dir data\synth_N1500 --util data\synth_N1500\utilities.tsv --minvalue 800 --max-edges 5 --out results\alt_S.csv > results\alt_S.log 2>&1
%J% -cp %JAR% edu.huflit.inchusm.cli.Baselines --snapshot-dir data\synth_N3000 --util data\synth_N3000\utilities.tsv --minvalue 1600 --max-edges 5 --out results\alt_L.csv > results\alt_L.log 2>&1
if not "%PART%"=="all" goto END

:SCALE
echo [2/3] Scalability, n = 1500 .. 48000 (about 20-30 minutes)
%J% -cp %JAR% edu.huflit.inchusm.cli.Baselines --snapshot-dir data\synth_N1500  --util data\synth_N1500\utilities.tsv  --minvalue 800   --max-edges 5 --skip b1,b2 --out results\scale_N1500.csv  > results\scale_N1500.log 2>&1
%J% -cp %JAR% edu.huflit.inchusm.cli.Baselines --snapshot-dir data\synth_N3000  --util data\synth_N3000\utilities.tsv  --minvalue 1600  --max-edges 5 --skip b1,b2 --out results\scale_N3000.csv  > results\scale_N3000.log 2>&1
%J% -cp %JAR% edu.huflit.inchusm.cli.Baselines --snapshot-dir data\synth_N6000  --util data\synth_N6000\utilities.tsv  --minvalue 3200  --max-edges 5 --skip b1,b2 --out results\scale_N6000.csv  > results\scale_N6000.log 2>&1
%J% -cp %JAR% edu.huflit.inchusm.cli.Baselines --snapshot-dir data\synth_N12000 --util data\synth_N12000\utilities.tsv --minvalue 6400  --max-edges 5 --skip b1,b2 --out results\scale_N12000.csv > results\scale_N12000.log 2>&1
%J% -cp %JAR% edu.huflit.inchusm.cli.Baselines --snapshot-dir data\synth_N24000 --util data\synth_N24000\utilities.tsv --minvalue 12800 --max-edges 5 --skip b1,b2 --out results\scale_N24000.csv > results\scale_N24000.log 2>&1
%J% -cp %JAR% edu.huflit.inchusm.cli.Baselines --snapshot-dir data\synth_N48000 --util data\synth_N48000\utilities.tsv --minvalue 25600 --max-edges 5 --skip b1,b2 --out results\scale_N48000.csv > results\scale_N48000.log 2>&1
if not "%PART%"=="all" goto END

:KSENS
echo [3/3] AMLworld discretization k = 4, 2, 8 with static re-mining (about 1-1.5 hours)
%J% -jar %JAR% stream --snapshot-dir data\aml_k4 --util data\aml_k4\utilities.tsv --minvalue 2000 --measure utility --bound ceu --mer 1 --max-edges 5 --compare-static --out results\aml_k4.csv > results\aml_k4.log 2>&1
%J% -jar %JAR% stream --snapshot-dir data\aml_k2 --util data\aml_k2\utilities.tsv --minvalue 1200 --measure utility --bound ceu --mer 1 --max-edges 5 --compare-static --out results\aml_k2.csv > results\aml_k2.log 2>&1
%J% -jar %JAR% stream --snapshot-dir data\aml_k8 --util data\aml_k8\utilities.tsv --minvalue 3600 --measure utility --bound ceu --mer 1 --max-edges 5 --compare-static --out results\aml_k8.csv > results\aml_k8.log 2>&1

:END
echo finished %DATE% %TIME% >> results\machine.txt
echo Done. Copy the whole "results" folder back.
endlocal
