# Raspberry Pi 4B replicada: Node-RED 4.0.9 con los modulos del sistema original
FROM nodered/node-red:4.0.9
ENV TZ=Europe/Madrid
USER root
RUN npm install --no-audit --no-fund --unsafe-perm --no-update-notifier \
      node-red-contrib-postgresql@~0.14.2 \
      node-red-dashboard@~3.6.5 \
      node-red-node-mysql@~2.0.0 \
      node-red-node-pi-gpio@~2.0.6 \
      node-red-node-ui-table@~0.4.4
# Los ficheros se copian a /data (no bind-mount): Node-RED los reescribe al
# hacer Deploy y no debe tocar los originales del repositorio.
COPY docker/nodered/settings.js      /data/settings.js
COPY docker/nodered/flows.json       /data/flows.json
COPY docker/nodered/flows_cred.json  /data/flows_cred.json
RUN chown -R node-red:node-red /data
USER node-red
