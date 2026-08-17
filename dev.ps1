$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Cargar la configuracion local sin mostrar secretos en consola.
$envFile = Join-Path $PSScriptRoot ".env"
if (Test-Path -LiteralPath $envFile) {
    Get-Content -LiteralPath $envFile | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) {
            return
        }

        $separatorIndex = $line.IndexOf("=")
        $key = $line.Substring(0, $separatorIndex).Trim()
        $value = $line.Substring($separatorIndex + 1).Trim().Trim('"').Trim("'")

        if ($key -match "^[A-Za-z_][A-Za-z0-9_]*$") {
            Set-Item -Path "Env:$key" -Value $value
        }
    }
}
else {
    $envExample = Join-Path $PSScriptRoot ".env.example"
    Write-Host "No existe .env. Creandolo desde .env.example..." -ForegroundColor Yellow
    Copy-Item -LiteralPath $envExample -Destination $envFile
    Write-Host "Configura MICROSERVICE_TOKEN y GEMINI_API_KEY en .env y vuelve a ejecutar .\dev.ps1" -ForegroundColor Yellow
    exit 1
}

# Evita UnicodeEncodeError con los logs en Windows.
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$venvDirectory = Join-Path $PSScriptRoot ".venv"
$python = Join-Path $venvDirectory "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    Write-Host "No existe .venv. Creando el entorno virtual..." -ForegroundColor Yellow

    $bootstrapPython = $null
    $localPythonRoot = Join-Path $env:LOCALAPPDATA "Programs\Python"
    if (Test-Path -LiteralPath $localPythonRoot) {
        $bootstrapPython = Get-ChildItem -Path $localPythonRoot -Filter python.exe -File -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -notmatch "\\.venv\\" } |
            Sort-Object FullName -Descending |
            Select-Object -First 1 -ExpandProperty FullName
    }

    if (-not $bootstrapPython) {
        $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
        if ($pythonCommand) {
            $bootstrapPython = $pythonCommand.Source
        }
    }

    if (-not $bootstrapPython) {
        Write-Host "Python no esta instalado. Instala Python 3.12 o superior y vuelve a ejecutar el script." -ForegroundColor Red
        Write-Host "winget install --id Python.Python.3.12 --exact --scope user" -ForegroundColor Yellow
        exit 1
    }

    & $bootstrapPython -m venv $venvDirectory
    if ($LASTEXITCODE -ne 0) {
        Write-Host "No se pudo crear .venv." -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

# Instalar requirements solamente cuando falten modulos esenciales.
& $python -c "import fastapi, uvicorn, pydantic, pydantic_settings, google.genai, multipart" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Faltan dependencias en .venv. Instalando requirements.txt..." -ForegroundColor Yellow
    & $python -m pip install --disable-pip-version-check --no-input -r (Join-Path $PSScriptRoot "requirements.txt")
    if ($LASTEXITCODE -ne 0) {
        Write-Host "No se pudieron instalar las dependencias. Revisa la conexion a PyPI." -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

$hostAddress = if ($env:HOST) { $env:HOST } else { "127.0.0.1" }
$port = if ($env:PORT) { [int]$env:PORT } else { 4012 }
$localUrl = "http://127.0.0.1:$port"

Write-Host "Levantando micro-scanner-contratos en $localUrl" -ForegroundColor Green
Write-Host "Swagger: $localUrl/docs" -ForegroundColor Cyan
Write-Host "Presiona Ctrl+C para detenerlo." -ForegroundColor DarkGray

& $python -m uvicorn app.main:app --reload --host $hostAddress --port $port
exit $LASTEXITCODE
