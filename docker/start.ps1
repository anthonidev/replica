# Levanta Postgres local para Replica si no está corriendo.
# Uso: .\docker\start.ps1
# Desde la raíz del proyecto (donde está app.py).

$ComposeFile = "$PSScriptRoot\docker-compose.yml"
$ContainerName = "clinicsay-replica-db"

function Test-DockerRunning {
    $null = docker info 2>&1
    return $LASTEXITCODE -eq 0
}

function Get-ContainerStatus {
    $status = docker inspect --format '{{.State.Status}}' $ContainerName 2>&1
    if ($LASTEXITCODE -ne 0) { return "missing" }
    return $status.Trim()
}

Write-Host ""
Write-Host "  Clinicsay Replica — PostgreSQL local" -ForegroundColor Cyan
Write-Host "  ─────────────────────────────────────" -ForegroundColor DarkGray
Write-Host ""

# 1. Verificar que Docker Desktop esté corriendo
if (-not (Test-DockerRunning)) {
    Write-Host "  [ERROR] Docker no está disponible. Abre Docker Desktop primero." -ForegroundColor Red
    Write-Host ""
    exit 1
}

$status = Get-ContainerStatus

switch ($status) {
    "running" {
        Write-Host "  [OK] El contenedor '$ContainerName' ya está corriendo." -ForegroundColor Green
    }
    "exited" {
        Write-Host "  Reiniciando contenedor parado '$ContainerName'..." -ForegroundColor Yellow
        docker start $ContainerName | Out-Null
        Write-Host "  [OK] Contenedor reiniciado." -ForegroundColor Green
    }
    "missing" {
        Write-Host "  Levantando Postgres por primera vez (postgres:17)..." -ForegroundColor Yellow
        docker compose -f $ComposeFile up -d
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  [ERROR] Falló docker compose up." -ForegroundColor Red
            exit 1
        }
        Write-Host "  [OK] Contenedor creado y corriendo." -ForegroundColor Green
    }
    default {
        Write-Host "  Estado desconocido '$status'. Intentando levantar..." -ForegroundColor Yellow
        docker compose -f $ComposeFile up -d
    }
}

# 2. Esperar a que Postgres acepte conexiones
Write-Host "  Esperando que Postgres esté listo..." -ForegroundColor DarkGray
$retries = 20
for ($i = 1; $i -le $retries; $i++) {
    $ready = docker exec $ContainerName pg_isready -U clinicsay -d clinicsay 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK] Postgres listo en localhost:5432" -ForegroundColor Green
        break
    }
    if ($i -eq $retries) {
        Write-Host "  [ERROR] Postgres no respondió tras $retries intentos." -ForegroundColor Red
        exit 1
    }
    Start-Sleep -Seconds 1
}

Write-Host ""
Write-Host "  BDs disponibles:" -ForegroundColor DarkGray
Write-Host "    clinicsay        → postgresql://clinicsay:clinicsay@localhost:5432/clinicsay" -ForegroundColor Gray
Write-Host "    clinicsay-backup → postgresql://clinicsay:clinicsay@localhost:5432/clinicsay-backup" -ForegroundColor Gray
Write-Host ""
Write-Host "  Ahora puedes ejecutar: python app.py" -ForegroundColor Cyan
Write-Host ""
