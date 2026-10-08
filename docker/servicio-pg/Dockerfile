# Software CPU Procesos: los 7 procesos batch, expuestos por HTTP en /run
FROM node:18-alpine
ENV TZ=Europe/Madrid
WORKDIR /app
COPY servicios/servicio_postgresql/package*.json ./
RUN npm install --omit=dev --no-audit --no-fund
COPY servicios/servicio_postgresql/ ./
RUN mkdir -p logs
EXPOSE 8081
CMD ["node", "server.js"]
