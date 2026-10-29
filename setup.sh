#!/usr/bin/env bash
# Crea el entorno virtual e instala dependencias.
# Uso: bash setup.sh
# Desde la raíz del proyecto (donde está app.py).

set -euo pipefail

VENV_DIR="$(dirname "$0")/.venv"
PYTHON="${PYTHON:-python3}"

echo ""
echo "  Clinicsay Replica — Setup"
echo "  ──────────────────────────"
echo ""

# 1. Verificar Python 3.12+
if ! command -v "$PYTHON" &> /dev/null; then
    echo "  [ERROR] Python no encontrado. Instala Python 3.12+."
    echo ""
    exit 1
fi
echo "  Python: $($PYTHON --version)"

# 2. Crear venv si no existe
if [ -f "$VENV_DIR/bin/python" ]; then
    echo "  [OK] Entorno virtual ya existe en .venv/"
else
    echo "  Creando entorno virtual en .venv/ ..."
    "$PYTHON" -m venv "$VENV_DIR"
    echo "  [OK] Entorno virtual creado."
fi

# 3. Instalar dependencias
PIP="$VENV_DIR/bin/pip"
echo "  Instalando dependencias desde requirements.txt ..."
"$PIP" install --upgrade pip --quiet
"$PIP" install -r "$(dirname "$0")/requirements.txt"
echo "  [OK] Dependencias instaladas."

echo ""
echo "  Listo. Para ejecutar la app:"
echo ""
echo "    .venv/bin/python app.py"
echo ""
echo "  O activa el entorno primero:"
echo ""
echo "    source .venv/bin/activate"
echo "    python app.py"
echo ""
