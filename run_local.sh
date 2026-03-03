#!/usr/bin/env bash
set -euo pipefail

# Script para configurar ambiente local e executar o servidor (desenvolvimento)
# Uso: ./run_local.sh

python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
python manage.py makemigrations
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
