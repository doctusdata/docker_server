import { query } from '../db/index.js';
import logger from '../utils/logger.js';

/**
 * Controlador para consultas relacionadas con la tabla Bin
 */

/**
 * Obtiene los registros de consumo de stock
 * @param {Object} req - Objeto de solicitud
 * @param {Object} res - Objeto de respuesta
 * @param {Function} next - Función para continuar al siguiente middleware
 */
export const getStockConsumption = async (req, res, next) => {
  try {
    const { devid, patient, operating_room, startDate, endDate } = req.query;
    
    let sqlQuery = `
      SELECT devid, "EPC", patient, operating_room, "Local_time"
      FROM "Bin"
    `;
    
    const queryParams = [];
    let hasWhereClause = false;
    
    // Añadir filtros opcionales
    if (devid) {
      sqlQuery += ` WHERE devid = $${queryParams.length + 1}`;
      queryParams.push(devid);
      hasWhereClause = true;
    }
    
    if (patient) {
      sqlQuery += hasWhereClause ? ` AND` : ` WHERE`;
      sqlQuery += ` patient = $${queryParams.length + 1}`;
      queryParams.push(patient);
      hasWhereClause = true;
    }
    
    if (operating_room) {
      sqlQuery += hasWhereClause ? ` AND` : ` WHERE`;
      sqlQuery += ` operating_room = $${queryParams.length + 1}`;
      queryParams.push(operating_room);
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
    
    logger.info('Consulta de consumo de stock ejecutada', { 
      count: result.rowCount,
      filters: { devid, patient, operating_room, startDate, endDate }
    });
    
    res.json(result.rows);
  } catch (error) {
    logger.error('Error al obtener consumo de stock', { error: error.message });
    next(error);
  }
};

/**
 * Elimina todos los registros de la tabla Bin
 * @param {Object} req - Objeto de solicitud
 * @param {Object} res - Objeto de respuesta
 * @param {Function} next - Función para continuar al siguiente middleware
 */
export const deleteAllBin = async (req, res, next) => {
  try {
    const result = await query(
      'DELETE FROM "Bin" RETURNING *',
      []
    );
    
    logger.info('Todos los registros de Bin eliminados', { 
      count: result.rowCount 
    });
    
    res.json({ 
      message: `${result.rowCount} registros de Bin eliminados correctamente` 
    });
  } catch (error) {
    logger.error('Error al eliminar todos los registros de Bin', { error: error.message });
    next(error);
  }
};