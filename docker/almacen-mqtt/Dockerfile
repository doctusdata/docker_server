# Software CPU comunicaciones: puente MQTT -> PostgreSQL
FROM node:18-alpine
ENV TZ=Europe/Madrid
WORKDIR /app
COPY servicios/almacen_mqtt/package*.json ./
RUN npm install --omit=dev --no-audit --no-fund
COPY servicios/almacen_mqtt/ ./
RUN mkdir -p logs
CMD ["node", "index.js"]
