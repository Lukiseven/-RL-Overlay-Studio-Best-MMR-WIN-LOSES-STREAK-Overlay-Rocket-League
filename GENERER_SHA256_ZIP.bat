@echo off
setlocal
title Generer SHA256

echo.
echo Glissez le fichier ZIP de la release sur ce fichier .bat
echo ou indiquez son chemin.
echo.

if "%~1"=="" (
    set /p ZIPFILE=Chemin du fichier ZIP :
) else (
    set "ZIPFILE=%~1"
)

if not exist "%ZIPFILE%" (
    echo Fichier introuvable.
    pause
    exit /b 1
)

echo.
echo SHA256 de :
echo %ZIPFILE%
echo.
certutil -hashfile "%ZIPFILE%" SHA256

echo.
echo Copiez uniquement la grande ligne de hash sans les espaces.
echo.
pause
endlocal
