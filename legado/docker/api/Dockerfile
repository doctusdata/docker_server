# API REST de gestion RFID (Express, ESM)
FROM node:18-alpine
ENV TZ=Europe/Madrid
WORKDIR /app
COPY servicios/gestion-rfid-api/package*.json ./
RUN npm install --omit=dev --no-audit --no-fund
COPY servicios/gestion-rfid-api/ ./
RUN mkdir -p logs
EXPOSE 3000
CMD ["node", "src/index.js"]
