import { query } from '../db/index.js';
import logger from '../utils/logger.js';

/**
 * Controlador para consultas relacionadas con la tabla User_readings
 */

/**
 * Obtiene los registros de usuarios en puertas
 * @param {Object} req - Objeto de solicitud
 * @param {Object} res - Objeto de respuesta
 * @param {Function} next - Función para continuar al siguiente middleware
 */
export const getUserDoor = async (req, res, next) => {
  try {
    const { devid, startDate, endDate } = req.query;
    
    let sqlQuery = `
      SELECT devid, "EPC", "Local_time"
      FROM "User_readings"
    `;
    
    const queryParams = [];
    let hasWhereClause = false;
    
    // Añadir filtros opcionales
    if (devid) {
      sqlQuery += ` WHERE devid = $${queryParams.length + 1}`;
      queryParams.push(devid);
      hasWhereClause = true;
    }
    
    if (startDate && endDate) {
      sqlQuery += hasWhereClause ? ` AND` : ` WHERE`;
      sqlQuery += ` "Local_time" BETWEEN $${queryParams.length + 1} AND $${queryParams.length + 2}`;
      queryParams.push(startDate, endDate);
    }
    
    // Ordenar por fecha
    sqlQuery += ` ORDER BY "Local_time" DESC`;
    
    const result = await query(sqlQuery, queryParams);
    
    logger.info('Consulta de usuarios en puertas ejecutada', { 
      count: result.rowCount,
      filters: { devid, startDate, endDate }
    });
    
    res.json(result.rows);
  } catch (error) {
    logger.error('Error al obtener usuarios en puertas', { error: error.message });
    next(error);
  }
};

/**
 * Elimina todos los registros de la tabla User_readings
 * @param {Object} req - Objeto de solicitud
 * @param {Object} res - Objeto de respuesta
 * @param {Function} next - Función para continuar al siguiente middleware
 */
export const deleteAllUserReadings = async (req, res, next) => {
  try {
    const result = await query(
      'DELETE FROM "User_readings" RETURNING *',
      []
    );
    
    logger.info('Todos los registros de User_readings eliminados', { 
      count: result.rowCount 
    });
    
    res.json({ 
      message: `${result.rowCount} registros de User_readings eliminados correctamente` 
    });
  } catch (error) {
    logger.error('Error al eliminar todos los registros de User_readings', { error: error.message });
    next(error);
  }
};