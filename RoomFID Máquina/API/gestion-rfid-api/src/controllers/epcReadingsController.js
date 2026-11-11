import { query } from '../db/index.js';
import logger from '../utils/logger.js';

/**
 * Controlador para consultas relacionadas con la tabla EPC_readings
 */

/**
 * Obtiene los registros de stock
 * @param {Object} req - Objeto de solicitud
 * @param {Object} res - Objeto de respuesta
 * @param {Function} next - Función para continuar al siguiente middleware
 */
export const getStock = async (req, res, next) => {
  try {
    const { devid, startDate, endDate } = req.query;
    
    let sqlQuery = `
      SELECT devid, "EPC", "Local_time"
      FROM "EPC_readings"
      WHERE "Stock" = 1 AND "Used" IS NULL
    `;
    
    const queryParams = [];
    
    // Añadir filtros opcionales
    if (devid) {
      sqlQuery += ` AND devid = $${queryParams.length + 1}`;
      queryParams.push(devid);
    }
    
    if (startDate && endDate) {
      sqlQuery += ` AND "Local_time" BETWEEN $${queryParams.length + 1} AND $${queryParams.length + 2}`;
      queryParams.push(startDate, endDate);
    }
    
    // Ordenar por fecha
    sqlQuery += ` ORDER BY "Local_time" DESC`;
    
    const result = await query(sqlQuery, queryParams);
    
    logger.info('Consulta de stock ejecutada', { 
      count: result.rowCount,
      filters: { devid, startDate, endDate }
    });
    
    res.json(result.rows);
  } catch (error) {
    logger.error('Error al obtener stock', { error: error.message });
    next(error);
  }
};

/**
 * Obtiene los registros de stock temporal
 * @param {Object} req - Objeto de solicitud
 * @param {Object} res - Objeto de respuesta
 * @param {Function} next - Función para continuar al siguiente middleware
 */
export const getStockTemporal = async (req, res, next) => {
  try {
    const { devid, startDate, endDate } = req.query;
    
    let sqlQuery = `
      SELECT devid, "EPC", "Local_time", "EPC_User", "Time_User"
      FROM "EPC_readings"
      WHERE "Stock" = 0 AND "Used" IS NULL
    `;
    
    const queryParams = [];
    
    // Añadir filtros opcionales
    if (devid) {
      sqlQuery += ` AND devid = $${queryParams.length + 1}`;
      queryParams.push(devid);
    }
    
    if (startDate && endDate) {
      sqlQuery += ` AND "Time_User" BETWEEN $${queryParams.length + 1} AND $${queryParams.length + 2}`;
      queryParams.push(startDate, endDate);
    }
    
    // Ordenar por fecha
    sqlQuery += ` ORDER BY "Time_User" DESC`;
    
    const result = await query(sqlQuery, queryParams);
    
    logger.info('Consulta de stock temporal ejecutada', { 
      count: result.rowCount,
      filters: { devid, startDate, endDate }
    });
    
    res.json(result.rows);
  } catch (error) {
    logger.error('Error al obtener stock temporal', { error: error.message });
    next(error);
  }
};

/**
 * Elimina todos los registros con Stock=0
 * @param {Object} req - Objeto de solicitud
 * @param {Object} res - Objeto de respuesta
 * @param {Function} next - Función para continuar al siguiente middleware
 */
export const deleteStockTemporal = async (req, res, next) => {
  try {
    const result = await query(
      'DELETE FROM "EPC_readings" WHERE "Stock" = 0 RETURNING *',
      []
    );
    
    logger.info('Registros de stock temporal eliminados', { 
      count: result.rowCount 
    });
    
    res.json({ 
      message: `${result.rowCount} registros de stock temporal eliminados correctamente` 
    });
  } catch (error) {
    logger.error('Error al eliminar registros de stock temporal', { error: error.message });
    next(error);
  }
};