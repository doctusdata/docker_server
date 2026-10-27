// Configuración de la base de datos PostgreSQL
module.exports = {
    host: "192.168.1.155",
    user: "rfidroom",
    password: "rfidroom@2025",
    database: "gestion_rfid",
    port: 5432,
    // Configuraciones específicas de PostgreSQL
    max: 20, // máximo de conexiones en el pool
    idleTimeoutMillis: 30000, // tiempo máximo que una conexión puede estar inactiva
    connectionTimeoutMillis: 2000 // tiempo máximo para establecer conexión
};
