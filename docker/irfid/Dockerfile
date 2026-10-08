# Servicio irfid: almacen (ingesta + trazabilidad), orquestador y archivo.
# Una sola imagen; el compose elige el proceso con el comando.
# Contexto de build: ../irfid/servicio (ver docker-compose.yml).
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 TZ=Europe/Madrid \
    IRFID_SQL_DIR=/app/sql IRFID_TOPOLOGIA=/app/topologia.json
# pg_dump 18 (misma version que el servidor) para el backup; rsync/ssh para el archivado.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates gnupg rsync openssh-client \
 && install -d /usr/share/postgresql-common/pgdg \
 && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
 && . /etc/os-release \
 && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt $VERSION_CODENAME-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
 && apt-get update && apt-get install -y --no-install-recommends postgresql-client-18 \
 && apt-get purge -y gnupg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .
COPY sql ./sql
COPY topologia.json ./
RUN mkdir -p /data/spool /data/archivo
CMD ["python", "-m", "irfid", "almacen"]
