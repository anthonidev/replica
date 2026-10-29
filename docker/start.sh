#!/usr/bin/env bash
# Levanta Postgres local para Replica si no está corriendo.
# Uso: bash docker/start.sh
# Desde la raíz del proyecto (donde está app.py).

set -euo pipefail

COMPOSE_FILE="$(dirname "$0")/docker-compose.yml"
CONTAINER="clinicsay-replica-db"

echo ""
echo "  Clinicsay Replica — PostgreSQL local"
echo "  ─────────────────────────────────────"
echo ""

# 1. Verificar Docker
if ! docker info > /dev/null 2>&1; then
    echo "  [ERROR] Docker no está disponible. Abre Docker Desktop primero."
    echo ""
    exit 1
fi

STATUS=$(docker inspect --format '{{.State.Status}}' "$CONTAINER" 2>/dev/null || echo "missing")

case "$STATUS" in
    running)
        echo "  [OK] El contenedor '$CONTAINER' ya está corriendo."
        ;;
    exited)
        echo "  Reiniciando contenedor parado '$CONTAINER'..."
        docker start "$CONTAINER"
        echo "  [OK] Contenedor reiniciado."
        ;;
    missing)
        echo "  Levantando Postgres por primera vez (postgres:17)..."
        docker compose -f "$COMPOSE_FILE" up -d
        echo "  [OK] Contenedor creado y corriendo."
        ;;
    *)
        echo "  Estado desconocido '$STATUS'. Intentando levantar..."
        docker compose -f "$COMPOSE_FILE" up -d
        ;;
esac

# 2. Esperar a que Postgres acepte conexiones
echo "  Esperando que Postgres esté listo..."
for i in $(seq 1 20); do
    if docker exec "$CONTAINER" pg_isready -U clinicsay -d clinicsay > /dev/null 2>&1; then
        echo "  [OK] Postgres listo en localhost:5432"
        break
    fi
    if [ "$i" -eq 20 ]; then
        echo "  [ERROR] Postgres no respondió tras 20 intentos."
        exit 1
    fi
    sleep 1
done

echo ""
echo "  BDs disponibles:"
echo "    clinicsay        → postgresql://clinicsay:clinicsay@localhost:5432/clinicsay"
echo "    clinicsay-backup → postgresql://clinicsay:clinicsay@localhost:5432/clinicsay-backup"
echo ""
echo "  Ahora puedes ejecutar: python app.py"
echo ""
