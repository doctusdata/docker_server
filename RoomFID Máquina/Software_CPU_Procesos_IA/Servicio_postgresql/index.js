const { Pool } = require('pg');
const fs = require('fs');
const path = require('path');
const winston = require('winston');
const dbConfig = require('./config/database');

// Load configuration
const config = JSON.parse(fs.readFileSync(path.join(__dirname, 'config', 'app.json'), 'utf8'));

// Configure logger
const logDir = config.logDirectory || 'logs';
if (!fs.existsSync(logDir)) {
    fs.mkdirSync(logDir);
}

const logger = winston.createLogger({
    format: winston.format.combine(
        winston.format.timestamp(),
        winston.format.json()
    ),
    transports: [
        new winston.transports.Console(),
        new winston.transports.File({ 
            filename: path.join(logDir, `error-${new Date().toISOString().split('T')[0]}.log`),
            level: 'error'
        }),
        new winston.transports.File({ 
            filename: path.join(logDir, `combined-${new Date().toISOString().split('T')[0]}.log`)
        })
    ]
});

async function createDatabaseConnection() {
    try {
        const pool = new Pool(dbConfig);
        const client = await pool.connect();
        logger.info('Database connection established');
        return client;
    } catch (error) {
        logger.error('Failed to connect to database:', error);
        throw error;
    }
}

async function processForeignDelete(client) {
    try {
        const almacenId = config.Almacen_id;
        const query = `
            DELETE FROM "EPC_readings" er
            WHERE er."devid" = $1
            AND NOT EXISTS (
                SELECT 1 
                FROM "EPC_master" em 
                WHERE em."EPC" = er."EPC"
            )
        `;
        const result = await client.query(query, [almacenId]);
        logger.info(`Foreign delete process completed: ${result.rowCount} records deleted`);
    } catch (error) {
        logger.error('Error in foreign delete process:', error);
        throw error;
    }
}

async function processAsignacionAlmacen(client) {
    try {
        const almacenId = config.Almacen_id;
        const query = `
            UPDATE "EPC_master" em
            SET "Almacen" = $1
            FROM "EPC_readings" er
            WHERE er."EPC" = em."EPC"
            AND er."devid" = $1
        `;
        const result = await client.query(query, [almacenId]);
        logger.info(`Asignación Almacen completada: ${result.rowCount} registros actualizados`);
    } catch (error) {
        logger.error('Error en proceso de Asignación Almacen:', error);
        throw error;
    }
}

async function processAlmacen(client) {
    try {
        const scanTimeMinutes = config.Scan_time_nofound;
        const almacenId = config.Almacen_id;
        const query = `
            UPDATE "EPC_readings" 
            SET "Stock" = 0 
            WHERE (EXTRACT(EPOCH FROM (NOW() - "Local_time"))/60) > $1 
            AND "Used" IS NULL
            AND "devid" = $2
        `;
        const result = await client.query(query, [scanTimeMinutes, almacenId]);
        logger.info(`Almacen process completed: ${result.rowCount} records updated`);
    } catch (error) {
        logger.error('Error in Almacen process:', error);
        throw error;
    }
}

async function processPapelera(client) {
    try {
        const query = `
            UPDATE "EPC_readings" e
            SET "Used" = 1
            FROM "Bin" b
            WHERE e."EPC" = b."EPC"
            AND e."Used" IS NULL
            AND NOT EXISTS (
                SELECT 1 
                FROM "EPC_readings" e2 
                WHERE e2."EPC" = e."EPC" 
                AND e2."Used" = 1
            )
        `;
        const result = await client.query(query);
        logger.info(`Papelera process completed: ${result.rowCount} records updated`);
    } catch (error) {
        logger.error('Error in Papelera process:', error);
        throw error;
    }
}

async function processUsuarios(client) {
    try {
        const almacenId = config.Almacen_id;
        const accessDoor = config.Access_door;
        const query = `
            WITH latest_user AS (
                SELECT 
                    ur."EPC" AS user_epc,
                    ur."Local_time" AS user_time
                FROM "User_readings" ur
                WHERE ur."devid" = $2
                ORDER BY ur."Local_time" DESC
                LIMIT 1
            ),
            matched AS (
                SELECT 
                    er.id,
                    lu.user_epc,
                    lu.user_time
                FROM "EPC_readings" er
                CROSS JOIN latest_user lu
                WHERE er."Stock" = 0 
                AND er."Used" IS NULL
                AND er."Tmp" = 0
                AND er."devid" = $1
            )
            UPDATE "EPC_readings" e
            SET 
                "EPC_User" = m.user_epc,
                "Time_User" = m.user_time,
                "Tmp" = 1
            FROM matched m
            WHERE e.id = m.id
            AND e."Used" IS NULL
            AND e."Stock" = 0
            AND e."Tmp" = 0
        `;
        const result = await client.query(query, [almacenId, accessDoor]);
        logger.info(`Usuarios process completed: ${result.rowCount} records updated`);
    } catch (error) {
        logger.error('Error in Usuarios process:', error);
        throw error;
    }
}

async function processUsedDelete(client) {
    try {
        const almacenId = config.Almacen_id;
        const query = `
            DELETE FROM "EPC_readings" er
            WHERE er."devid" = $1
            AND er."Used" = 1
            AND EXISTS (
                SELECT 1 
                FROM "Bin" b 
                WHERE b."EPC" = er."EPC"
            )
        `;
        const result = await client.query(query, [almacenId]);
        logger.info(`Used delete process completed: ${result.rowCount} records deleted`);
    } catch (error) {
        logger.error('Error in used delete process:', error);
        throw error;
    }
}

async function processMasterDelete(client) {
    try {
        const query = `
            DELETE FROM "EPC_master" em
            WHERE EXISTS (
                SELECT 1 
                FROM "Bin" b 
                WHERE b."EPC" = em."EPC"
            )
        `;
        const result = await client.query(query);
        logger.info(`Master delete process completed: ${result.rowCount} records deleted`);
    } catch (error) {
        logger.error('Error in master delete process:', error);
        throw error;
    }
}

async function main() {
    let client;
    try {
        client = await createDatabaseConnection();
        
        logger.info('Starting database processing...');
        
        // Execute processes sequentially
        await processForeignDelete(client);
        await processAsignacionAlmacen(client);
        await processAlmacen(client);
        await processPapelera(client);
        await processUsuarios(client);
        await processUsedDelete(client);
        await processMasterDelete(client);
        
        logger.info('All processes completed successfully');
    } catch (error) {
        logger.error('Application failed:', error);
        process.exit(1);
    } finally {
        if (client) {
            await client.release();
            logger.info('Database connection closed');
        }
    }
}

// Run the application
main().catch(error => {
    logger.error('Unhandled error:', error);
    process.exit(1);
});
