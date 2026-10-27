const fs = require('fs');
const path = require('path');

class Logger {
    constructor() {
        // Crear directorio de logs si no existe
        this.logsDir = path.join(__dirname, '..', 'logs');
        if (!fs.existsSync(this.logsDir)) {
            fs.mkdirSync(this.logsDir);
        }
    }

    // Generar nombre de archivo de log con fecha
    getLogFileName() {
        const date = new Date();
        return path.join(
            this.logsDir,
            `error-${date.getFullYear()}-${(date.getMonth() + 1).toString().padStart(2, '0')}-${date.getDate().toString().padStart(2, '0')}.log`
        );
    }

    // Registrar error en archivo
    logError(error, context = '') {
        const timestamp = new Date().toISOString();
        const logEntry = {
            timestamp,
            context,
            error: {
                message: error.message,
                stack: error.stack,
                name: error.name
            }
        };

        const logMessage = `[${timestamp}] ${context}\n${JSON.stringify(logEntry, null, 2)}\n\n`;

        // Escribir en archivo de log
        fs.appendFileSync(this.getLogFileName(), logMessage);
        
        // Mostrar en consola
        console.error(`Error en ${context}:`, error.message);
    }
}

module.exports = new Logger();