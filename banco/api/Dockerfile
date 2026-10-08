# API REST de gestion RFID, version de PRODUCCION (irfid/gestion-rfid-api: esquema con
# start_time/end_time/incidence). Contexto de build: ../../irfid/gestion-rfid-api
FROM node:18-alpine
ENV TZ=Europe/Madrid
WORKDIR /app
COPY package*.json ./
RUN npm install --omit=dev --no-audit --no-fund
COPY . ./
RUN mkdir -p logs
EXPOSE 3000
CMD ["node", "src/index.js"]
