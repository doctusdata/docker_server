const { Pool } = require('pg');
const dbConfig = require('../config/database');
const appConfig = require('../config/app.json');
const logger = require('./logger');

class DatabaseService {
    constructor() {
        this.pool = null;
        this.isClosing = false;
        this.tables = appConfig.database.tables;
    }

    connect() {
        try {
            this.pool = new Pool(dbConfig);
            
            this.pool.on('connect', () => {
                console.log('¡Conexión a base de datos exitosa!');
            });

            this.pool.on('error', (error) => {
                if (!this.isClosing) {
                    logger.logError(error, 'Error en base de datos');
                }
            });

            // Verificar la conexión
            this.pool.query('SELECT NOW()', (error) => {
                if (error) {
                    logger.logError(error, 'Conexión a base de datos');
                    process.exit(1);
                }
            });
        } catch (error) {
            logger.logError(error, 'Inicialización de base de datos');
        }
    }

    async findExistingEPC(tableName, EPC) {
        try {
            const query = `SELECT "id" FROM "${tableName}" WHERE "EPC" = $1 ORDER BY "id" DESC LIMIT 1`;
            const result = await this.pool.query(query, [EPC]);
            return result.rows.length > 0 ? result.rows[0] : null;
        } catch (error) {
            logger.logError(error, `Búsqueda de EPC en ${tableName}`);
            throw error;
        }
    }

    async updateSensorData(tableName, id, data) {
        try {
            const tableConfig = Object.values(this.tables).find(t => t.name === tableName);
            if (!tableConfig) {
                throw new Error(`Configuración de tabla no encontrada para ${tableName}`);
            }

            const fields = tableConfig.fields.filter(field => field in data);
            const setClause = fields.map((field, index) => `"${field}" = $${index + 1}`).join(', ');
            const values = fields.map(field => data[field]);

            let query;
            if (tableName === 'EPC_readings') {
                query = `
                    UPDATE "${tableName}"
                    SET ${setClause}, "Local_time" = now()
                    WHERE "id" = $${fields.length + 1}
                `;
            } else {
                query = `
                    UPDATE "${tableName}"
                    SET ${setClause}
                    WHERE "id" = $${fields.length + 1}
                `;
            }
            
            values.push(id);
            
            const result = await this.pool.query(query, values);
            return result;
        } catch (error) {
            logger.logError(error, `Actualización de datos en ${tableName}`);
            throw error;
        }
    }

    async insertSensorData(tableName, data) {
        try {
            const tableConfig = Object.values(this.tables).find(t => t.name === tableName);
            if (!tableConfig) {
                throw new Error(`Configuración de tabla no encontrada para ${tableName}`);
            }

            const fields = tableConfig.fields.filter(field => field in data);
            const placeholders = fields.map((_, index) => `$${index + 1}`).join(', ');
            const values = fields.map(field => data[field]);

            const query = `
                INSERT INTO "${tableName}" ("${fields.join('", "')}")
                VALUES (${placeholders})
                RETURNING "id"
            `;

            const result = await this.pool.query(query, values);
            return result;
        } catch (error) {
            logger.logError(error, `Inserción de datos en ${tableName}`);
            throw error;
        }
    }

    async processSensorData(tableName, data, operationType) {
        if (this.isClosing) return null;

        try {
            if (!data.EPC) {
                throw new Error('EPC inválido');
            }

            if (tableName === 'EPC_readings') {
                data.Stock = 1;
                data.Tmp = 0;
            }

            switch (operationType) {
                case '0':
                    const insertResult = await this.insertSensorData(tableName, data);
                    console.log(`Nuevo registro insertado para EPC ${data.EPC} en ${tableName}`);
                    return insertResult;

                case '1':
                    const existingRecord = await this.findExistingEPC(tableName, data.EPC);
                    if (existingRecord) {
                        const updateResult = await this.updateSensorData(tableName, existingRecord.id, data);
                        console.log(`Registro actualizado para EPC ${data.EPC} en ${tableName}`);
                        return updateResult;
                    }
                    console.log(`No se encontró registro existente para EPC ${data.EPC} en ${tableName}`);
                    return null;

                case '2':
                    const existing = await this.findExistingEPC(tableName, data.EPC);
                    if (existing) {
                        const result = await this.updateSensorData(tableName, existing.id, data);
                        console.log(`Registro actualizado para EPC ${data.EPC} en ${tableName}`);
                        return result;
                    } else {
                        const result = await this.insertSensorData(tableName, data);
                        console.log(`Nuevo registro insertado para EPC ${data.EPC} en ${tableName}`);
                        return result;
                    }

                default:
                    throw new Error(`Tipo de operación inválido: ${operationType}`);
            }
        } catch (error) {
            logger.logError(error, `Procesamiento de datos del sensor en ${tableName}`);
            throw error;
        }
    }

    async close() {
        if (!this.pool || this.isClosing) {
            return;
        }

        this.isClosing = true;
        try {
            await this.pool.end();
            console.log('Conexión a base de datos cerrada');
        } catch (error) {
            logger.logError(error, 'Cierre de conexión a base de datos');
        }
    }
}

const databaseService = new DatabaseService();
module.exports = databaseService;
