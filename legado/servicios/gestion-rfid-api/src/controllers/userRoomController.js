import { query } from '../db/index.js';
import logger from '../utils/logger.js';

/**
 * Controlador para operaciones CRUD en la tabla user_room
 */

/**
 * Obtiene todos los registros de la tabla user_room
 * @param {Object} req - Objeto de solicitud
 * @param {Object} res - Objeto de respuesta
 * @param {Function} next - Función para continuar al siguiente middleware
 */
export const readAll = async (req, res, next) => {
  try {
    const result = await query('SELECT id, epc, door, state FROM "user_room" ORDER BY id', []);
    
    logger.info('Consulta de todos los registros de user_room ejecutada', { 
      count: result.rowCount 
    });
    
    res.json(result.rows);
  } catch (error) {
    logger.error('Error al obtener todos los registros de user_room', { error: error.message });
    next(error);
  }
};

/**
 * Obtiene registros filtrados por EPC
 * @param {Object} req - Objeto de solicitud
 * @param {Object} res - Objeto de respuesta
 * @param {Function} next - Función para continuar al siguiente middleware
 */
export const readByEpc = async (req, res, next) => {
  try {
    const { epc } = req.params;
    
    const result = await query(
      'SELECT id, epc, door, state FROM "user_room" WHERE epc = $1 ORDER BY id',
      [epc]
    );
    
    logger.info('Consulta de registros por EPC ejecutada', { 
      epc,
      count: result.rowCount 
    });
    
    res.json(result.rows);
  } catch (error) {
    logger.error('Error al obtener registros por EPC', { 
      epc: req.params.epc,
      error: error.message 
    });
    next(error);
  }
};

/**
 * Obtiene registros filtrados por puerta
 * @param {Object} req - Objeto de solicitud
 * @param {Object} res - Objeto de respuesta
 * @param {Function} next - Función para continuar al siguiente middleware
 */
export const readByDoor = async (req, res, next) => {
  try {
    const { door } = req.params;
    
    const result = await query(
      'SELECT id, epc, door, state FROM "user_room" WHERE door = $1 ORDER BY id',
      [door]
    );
    
    logger.info('Consulta de registros por puerta ejecutada', { 
      door,
      count: result.rowCount 
    });
    
    res.json(result.rows);
  } catch (error) {
    logger.error('Error al obtener registros por puerta', { 
      door: req.params.door,
      error: error.message 
    });
    next(error);
  }
};

/**
 * Inserta un nuevo registro en la tabla user_room
 * @param {Object} req - Objeto de solicitud
 * @param {Object} res - Objeto de respuesta
 * @param {Function} next - Función para continuar al siguiente middleware
 */
export const insertData = async (req, res, next) => {
  try {
    const { epc, door, state } = req.body;
    
    // Validar que se proporcionen todos los campos requeridos
    if (!epc || !door || state === undefined) {
      return res.status(400).json({ 
        error: 'Se requieren los campos epc, door y state' 
      });
    }
    
    const result = await query(
      'INSERT INTO "user_room" (epc, door, state) VALUES ($1, $2, $3) RETURNING id, epc, door, state',
      [epc, door, state]
    );
    
    logger.info('Nuevo registro insertado en user_room', { 
      id: result.rows[0].id,
      epc,
      door,
      state 
    });
    
    res.status(201).json(result.rows[0]);
  } catch (error) {
    logger.error('Error al insertar nuevo registro', { 
      data: req.body,
      error: error.message 
    });
    next(error);
  }
};

/**
 * Actualiza un registro existente en la tabla user_room
 * @param {Object} req - Objeto de solicitud
 * @param {Object} res - Objeto de respuesta
 * @param {Function} next - Función para continuar al siguiente middleware
 */
export const updateData = async (req, res, next) => {
  try {
    const { id } = req.params;
    const { epc, door, state } = req.body;
    
    // Validar que se proporcione al menos un campo para actualizar
    if (!epc && !door && state === undefined) {
      return res.status(400).json({ 
        error: 'Se requiere al menos un campo para actualizar (epc, door o state)' 
      });
    }
    
    // Construir la consulta de actualización dinámicamente
    let updateQuery = 'UPDATE "user_room" SET';
    const queryParams = [];
    const updateFields = [];
    
    if (epc) {
      queryParams.push(epc);
      updateFields.push(` epc = $${queryParams.length}`);
    }
    
    if (door) {
      queryParams.push(door);
      updateFields.push(` door = $${queryParams.length}`);
    }
    
    if (state !== undefined) {
      queryParams.push(state);
      updateFields.push(` state = $${queryParams.length}`);
    }
    
    updateQuery += updateFields.join(',');
    queryParams.push(id);
    updateQuery += ` WHERE id = $${queryParams.length} RETURNING id, epc, door, state`;
    
    const result = await query(updateQuery, queryParams);
    
    if (result.rowCount === 0) {
      return res.status(404).json({ 
        error: `No se encontró registro con id ${id}` 
      });
    }
    
    logger.info('Registro actualizado en user_room', { 
      id,
      updatedFields: req.body 
    });
    
    res.json(result.rows[0]);
  } catch (error) {
    logger.error('Error al actualizar registro', { 
      id: req.params.id,
      data: req.body,
      error: error.message 
    });
    next(error);
  }
};

/**
 * Elimina un registro existente de la tabla user_room
 * @param {Object} req - Objeto de solicitud
 * @param {Object} res - Objeto de respuesta
 * @param {Function} next - Función para continuar al siguiente middleware
 */
export const deleteData = async (req, res, next) => {
  try {
    const { id } = req.params;
    
    const result = await query(
      'DELETE FROM "user_room" WHERE id = $1 RETURNING id',
      [id]
    );
    
    if (result.rowCount === 0) {
      return res.status(404).json({ 
        error: `No se encontró registro con id ${id}` 
      });
    }
    
    logger.info('Registro eliminado de user_room', { id });
    
    res.json({ message: `Registro con id ${id} eliminado correctamente` });
  } catch (error) {
    logger.error('Error al eliminar registro', { 
      id: req.params.id,
      error: error.message 
    });
    next(error);
  }
};

/**
 * Elimina todos los registros de la tabla user_room
 * @param {Object} req - Objeto de solicitud
 * @param {Object} res - Objeto de respuesta
 * @param {Function} next - Función para continuar al siguiente middleware
 */
export const deleteAllUserRoom = async (req, res, next) => {
  try {
    const result = await query(
      'DELETE FROM "user_room" RETURNING *',
      []
    );
    
    logger.info('Todos los registros de user_room eliminados', { 
      count: result.rowCount 
    });
    
    res.json({ 
      message: `${result.rowCount} registros de user_room eliminados correctamente` 
    });
  } catch (error) {
    logger.error('Error al eliminar todos los registros de user_room', { error: error.message });
    next(error);
  }
};