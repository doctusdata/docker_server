const mqttService = require('./services/mqtt');
const dbService = require('./services/database');
const logger = require('./services/logger');

// Iniciar servicios
try {
    dbService.connect();
    mqttService.connect();
} catch (error) {
    logger.logError(error, 'Inicio de servicios');
    process.exit(1);
}

// Manejar cierre del programa
let isShuttingDown = false;

async function shutdown() {
    if (isShuttingDown) return;
    isShuttingDown = true;

    console.log('Cerrando conexiones...');
    
    try {
        await mqttService.close();
        await dbService.close();
        console.log('Todas las conexiones cerradas correctamente');
    } catch (error) {
        logger.logError(error, 'Cierre de aplicación');
    } finally {
        process.exit(0);
    }
}

// Manejar señales de terminación
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
process.on('uncaughtException', (error) => {
    logger.logError(error, 'Error no controlado');
    shutdown();
});