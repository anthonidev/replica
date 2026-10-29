# Crea el entorno virtual e instala dependencias.
# Uso: .\setup.ps1
# Desde la raíz del proyecto (donde está app.py).

$VenvDir = "$PSScriptRoot\.venv"
$Python  = "python"

Write-Host ""
Write-Host "  Clinicsay Replica — Setup" -ForegroundColor Cyan
Write-Host "  ──────────────────────────" -ForegroundColor DarkGray
Write-Host ""

# 1. Verificar Python 3.12+
$version = & $Python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [ERROR] Python no encontrado. Instala Python 3.12+." -ForegroundColor Red
    exit 1
}
Write-Host "  Python: $version" -ForegroundColor DarkGray

# 2. Crear venv si no existe
if (Test-Path "$VenvDir\Scripts\python.exe") {
    Write-Host "  [OK] Entorno virtual ya existe en .venv\" -ForegroundColor Green
} else {
    Write-Host "  Creando entorno virtual en .venv\ ..." -ForegroundColor Yellow
    & $Python -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [ERROR] No se pudo crear el entorno virtual." -ForegroundColor Red
        exit 1
    }
    Write-Host "  [OK] Entorno virtual creado." -ForegroundColor Green
}

# 3. Instalar dependencias
$Pip = "$VenvDir\Scripts\pip.exe"
Write-Host "  Instalando dependencias desde requirements.txt ..." -ForegroundColor Yellow
& $Pip install --upgrade pip --quiet
& $Pip install -r "$PSScriptRoot\requirements.txt"
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [ERROR] Falló la instalación de dependencias." -ForegroundColor Red
    exit 1
}
Write-Host "  [OK] Dependencias instaladas." -ForegroundColor Green

Write-Host ""
Write-Host "  Listo. Para ejecutar la app:" -ForegroundColor Cyan
Write-Host ""
Write-Host "    .\.venv\Scripts\python.exe app.py" -ForegroundColor White
Write-Host ""
Write-Host "  O activa el entorno primero:" -ForegroundColor DarkGray
Write-Host ""
Write-Host "    .\.venv\Scripts\Activate.ps1" -ForegroundColor White
Write-Host "    python app.py" -ForegroundColor White
Write-Host ""
