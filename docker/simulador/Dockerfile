# Simulador de lector Keonn AdvanReader (REST digest + MQTT)
FROM node:18-alpine
ENV TZ=Europe/Madrid
WORKDIR /app
COPY simuladores/keonn-sim/package*.json ./
RUN npm install --omit=dev --no-audit --no-fund
COPY simuladores/keonn-sim/ ./
CMD ["node", "index.js"]
