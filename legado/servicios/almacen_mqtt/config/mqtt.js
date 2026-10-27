// Configuración del cliente MQTT con autenticación
module.exports = {
    port: 1883,
    host: '192.168.1.155',
    clientId: 'gwt',
    keepalive: 60,
    reconnectPeriod: 1000,
    protocolId: 'MQIsdp',
    protocolVersion: 3,
    clean: true,
    encoding: 'utf8',
    connectTimeout: 10000,
    username: 'gestion_rfid', // Agregar usuario
    password: 'rfid_room@' // Agregar contraseña
};
