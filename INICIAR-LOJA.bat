@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo Iniciando Loja Itamarandiba - Sistema de Gestao Local...

if not exist ".venv\Scripts\python.exe" (
  echo Ambiente Python nao encontrado. Criando .venv local...
  python -m venv .venv --copies
  if errorlevel 1 (
    echo [ERRO] Nao foi possivel criar o ambiente virtual Python.
    pause
    exit /b 1
  )
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\pip.exe" install -r requirements.txt
  if errorlevel 1 (
    echo [ERRO] Falha ao instalar dependencias do sistema.
    pause
    exit /b 1
  )
)

".venv\Scripts\python.exe" run.py
if errorlevel 1 (
  echo.
  echo [ERRO] O servidor foi encerrado com erro.
  pause
  exit /b 1
)
