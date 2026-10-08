# Visor RFID (raspi_visor): el backend FastAPI sirve tambien el frontend construido.
# Contexto de build: ../raspi_visor
FROM node:20-alpine AS frontend
RUN corepack enable && corepack prepare pnpm@9.15.9 --activate
WORKDIR /src
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 TZ=Europe/Madrid WEB_ROOT=/app/web
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY --from=frontend /src/dist ./web
EXPOSE 8020
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8020}"]
