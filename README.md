# micro-scanner-contratos

Escáner de PDF a JSON dinámico. Recibe un PDF y una lista de campos (clave +
label) que manda el **frontend** — no hay schema fijo por tipo de servicio en
este microservicio. Usa Gemini File API (PDF nativo) + `response_schema`
generado en runtime con `pydantic.create_model`.

Diseño completo: [`docs/investigaciones/plan-contratos-ia-fases.md`](../docs/investigaciones/plan-contratos-ia-fases.md)
en el monorepo (Bloque 1: F1-F4, campos dinámicos).

## Variables de entorno

No hay `.env.example` (bloqueado por permisos del entorno de desarrollo). Copiar
esta lista a un `.env` local:

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
GEMINI_MODEL=gemini-2.5-flash

MAX_FILE_SIZE_MB=15
```

## Correr local

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
