# micro-scanner-contratos

Escáner de PDF a JSON dinámico. Recibe un PDF y una lista de campos (clave +
label) que manda el **frontend** — no hay schema fijo por tipo de servicio en
este microservicio. Usa Gemini File API (PDF nativo) + `response_schema`
generado en runtime con `pydantic.create_model`.

Diseño completo: [`docs/investigaciones/plan-contratos-ia-fases.md`](../docs/investigaciones/plan-contratos-ia-fases.md)
en el monorepo (Bloque 1: F1-F4, campos dinámicos).

## Variables de entorno

El repositorio incluye `.env.example`. En el primer arranque con PowerShell,
`dev.ps1` lo copia automaticamente a `.env` cuando este archivo todavia no
existe. Luego se deben configurar los valores privados localmente:

```
SERVICE_NAME=micro-scanner-contratos
SERVICE_VERSION=0.1.0
ENVIRONMENT=development
HOST=0.0.0.0
PORT=4012
LOG_LEVEL=INFO

# Requerido para /api/extract-contrato
MICROSERVICE_TOKEN=

# Gemini File API + structured output
GEMINI_API_KEY=
GEMINI_MODEL=gemini-flash-latest

MAX_FILE_SIZE_MB=14
```

## Correr local

### Windows PowerShell

```powershell
.\dev.ps1
```

El script carga `.env`, crea `.venv` si falta, instala `requirements.txt`
solamente cuando no encuentra las dependencias esenciales y levanta Uvicorn en
`http://127.0.0.1:4012` con recarga automatica.

### Linux/macOS

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload --port 4012
```

## Endpoints

- `GET /health`
- `POST /api/extract-contrato` (requiere header `X-Service-Token`)
  - multipart: `file` (PDF), `fields` (JSON `[{"key","label"}, ...]`), `include_cronograma` (bool)
  - devuelve `{clave: valor|null, ...}` — solo las claves pedidas

## Test

```bash
.venv/bin/pytest
```
