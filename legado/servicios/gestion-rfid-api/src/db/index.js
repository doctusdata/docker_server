import pg from 'pg';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import logger from '../utils/logger.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const configPath = path.join(__dirname, '../../config/app.json');
const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));

const { Pool } = pg;

// Crear pool de conexiones a PostgreSQL
const pool = new Pool({
  user: config.database.user,
  host: config.database.host,
  database: config.database.name,
  password: config.database.password,
  port: config.database.port,
  ssl: config.database.ssl ? { rejectUnauthorized: false } : false
});

// Evento para cuando se crea una conexión
pool.on('connect', () => {
  logger.info('Conexión a la base de datos establecida');
});

// Evento para cuando hay un error en la conexión
pool.on('error', (err) => {
  logger.error('Error en la conexión a la base de datos:', err);
});

/**
 * Ejecuta una consulta SQL en la base de datos
 * @param {string} text - Consulta SQL a ejecutar
 * @param {Array} params - Parámetros para la consulta
 * @returns {Promise} - Resultado de la consulta
 */
export const query = async (text, params) => {
  const start = Date.now();
  try {
    const res = await pool.query(text, params);
    const duration = Date.now() - start;
    logger.debug('Consulta ejecutada', { text, duration, rows: res.rowCount });
    return res;
  } catch (error) {
    logger.error('Error al ejecutar consulta', { text, error: error.message });
    throw error;
  }
};

export default {
  query,
  pool
};