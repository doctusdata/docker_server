# Nodo de monitorizacion local (monitor/node) con su panel estatico.
# Contexto de build: ../monitor. El envio a la central queda desactivado.
FROM node:20-alpine AS ui
# El panel importa packages/common_ts y contracts/ por ruta relativa: se reproduce la
# estructura del repositorio.
WORKDIR /repo/ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY contracts /repo/contracts
COPY packages/common_ts /repo/packages/common_ts
COPY ui/ ./
RUN npm run build:nodo

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 TZ=Europe/Madrid
# ping para las sondas icmp
RUN apt-get update && apt-get install -y --no-install-recommends iputils-ping \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
# Se conserva la estructura del repositorio: roomfid_common localiza contracts/ subiendo
# desde su propio fichero, por eso se instala en modo editable.
COPY contracts ./contracts
COPY packages/common_py ./packages/common_py
COPY packages/collectors_py ./packages/collectors_py
COPY node ./node
RUN pip install --no-cache-dir -e packages/common_py -e packages/collectors_py -e node
COPY --from=ui /repo/ui/out ./ui/out
COPY --from=despliegue --chmod=755 nodo.py /usr/local/bin/roomfid-nodo
EXPOSE 8080
CMD ["roomfid-nodo", "--config", "/etc/roomfid/node.yaml"]
