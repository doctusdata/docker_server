# Agente de monitorizacion RoomFID: uno por maquina (servidor, Raspberrys).
# Contexto de build: ../monitor. Ligero a proposito: corre tambien en las Pi.
#
# Necesita del host (ver los compose):
#   /:/host:ro                              disco del host
#   /var/run/docker.sock:ro                 contenedores
#   network_mode: host                      sondas (tablets, lectores) por la red de la maquina
# CPU, memoria, carga, temperatura y uptime se leen de /proc y /sys, que son del host.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 TZ=Europe/Madrid
RUN apt-get update && apt-get install -y --no-install-recommends iputils-ping \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY packages/collectors_py ./packages/collectors_py
COPY agent ./agent
RUN pip install --no-cache-dir ./packages/collectors_py ./agent
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD ["roomfid-agent", "--config", "/etc/roomfid/agente.yaml", "--salud"]
CMD ["roomfid-agent", "--config", "/etc/roomfid/agente.yaml"]
