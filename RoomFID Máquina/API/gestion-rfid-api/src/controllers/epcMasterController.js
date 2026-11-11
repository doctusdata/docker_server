import { query } from '../db/index.js';
import logger from '../utils/logger.js';

/**
 * Controlador para operaciones CRUD en la tabla EPC_master
 */

/**
 * Obtiene todos los registros de la tabla EPC_master
 * @param {Object} req - Objeto de solicitud
 * @param {Object} res - Objeto de respuesta
 * @param {Function} next - Función para continuar al siguiente middleware
 */
export const readAll = async (req, res, next) => {
  try {
    const result = await query(
      'SELECT id, "EPC" as epc, short_description, "Local_time", "Almacen" FROM "EPC_master" ORDER BY id',
      []
    );
    
    logger.info('Consulta de todos los registros de EPC_master ejecutada', { 
      count: result.rowCount 
    });
    
    res.json(result.rows);
  } catch (error) {
    logger.error('Error al obtener todos los registros de EPC_master', { error: error.message });
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
      'SELECT id, "EPC" as epc, short_description, "Local_time", "Almacen" FROM "EPC_master" WHERE "EPC" = $1 ORDER BY id',
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
 * Obtiene registros filtrados por descripción corta
 * @param {Object} req - Objeto de solicitud
 * @param {Object} res - Objeto de respuesta
 * @param {Function} next - Función para continuar al siguiente middleware
 */
export const readByShortDescription = async (req, res, next) => {
  try {
    const { description } = req.params;
    
    const result = await query(
      'SELECT id, "EPC" as epc, short_description, "Local_time", "Almacen" FROM "EPC_master" WHERE short_description ILIKE $1 ORDER BY id',
      [`%${description}%`]
    );
    
    logger.info('Consulta de registros por descripción ejecutada', { 
      description,
      count: result.rowCount 
    });
    
    res.json(result.rows);
  } catch (error) {
    logger.error('Error al obtener registros por descripción', { 
      description: req.params.description,
      error: error.message 
    });
    next(error);
  }
};

/**
 * Obtiene registros filtrados por almacén
 * @param {Object} req - Objeto de solicitud
 * @param {Object} res - Objeto de respuesta
 * @param {Function} next - Función para continuar al siguiente middleware
 */
export const readByAlmacen = async (req, res, next) => {
  try {
    const { almacen } = req.params;
    
    const result = await query(
      'SELECT id, "EPC" as epc, short_description, "Local_time", "Almacen" FROM "EPC_master" WHERE "Almacen" = $1 ORDER BY id',
      [almacen]
    );
    
    logger.info('Consulta de registros por almacén ejecutada', { 
      almacen,
      count: result.rowCount 
    });
    
    res.json(result.rows);
  } catch (error) {
    logger.error('Error al obtener registros por almacén', { 
      almacen: req.params.almacen,
      error: error.message 
    });
    next(error);
  }
};

/**
 * Inserta un nuevo registro en la tabla EPC_master
 * @param {Object} req - Objeto de solicitud
 * @param {Object} res - Objeto de respuesta
 * @param {Function} next - Función para continuar al siguiente middleware
 */
export const insertData = async (req, res, next) => {
  try {
    const { epc, short_description, almacen } = req.body;
    
    if (!epc || !short_description || !almacen) {
      return res.status(400).json({ 
        error: 'Se requieren los campos epc, short_description y almacen' 
      });
    }
    
    const result = await query(
      'INSERT INTO "EPC_master" ("EPC", short_description, "Almacen") VALUES ($1, $2, $3) RETURNING id, "EPC" as epc, short_description, "Local_time", "Almacen"',
      [epc, short_description, almacen]
    );
    
    logger.info('Nuevo registro insertado en EPC_master', { 
      id: result.rows[0].id,
      epc,
      short_description,
      almacen
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
 * Actualiza un registro existente en la tabla EPC_master
 * @param {Object} req - Objeto de solicitud
 * @param {Object} res - Objeto de respuesta
 * @param {Function} next - Función para continuar al siguiente middleware
 */
export const updateData = async (req, res, next) => {
  try {
    const { id } = req.params;
    const { epc, short_description, almacen } = req.body;
    
    if (!epc && !short_description && !almacen) {
      return res.status(400).json({ 
        error: 'Se requiere al menos un campo para actualizar (epc, short_description o almacen)' 
      });
    }
    
    let updateQuery = 'UPDATE "EPC_master" SET';
    const queryParams = [];
    const updateFields = [];
    
    if (epc) {
      queryParams.push(epc);
      updateFields.push(` "EPC" = $${queryParams.length}`);
    }
    
    if (short_description) {
      queryParams.push(short_description);
      updateFields.push(` short_description = $${queryParams.length}`);
    }
    
    if (almacen) {
      queryParams.push(almacen);
      updateFields.push(` "Almacen" = $${queryParams.length}`);
    }
    
    updateQuery += updateFields.join(',');
    queryParams.push(id);
    updateQuery += ` WHERE id = $${queryParams.length} RETURNING id, "EPC" as epc, short_description, "Local_time", "Almacen"`;
    
    const result = await query(updateQuery, queryParams);
    
    if (result.rowCount === 0) {
      return res.status(404).json({ 
        error: `No se encontró registro con id ${id}` 
      });
    }
    
    logger.info('Registro actualizado en EPC_master', { 
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
 * Elimina un registro existente de la tabla EPC_master
 * @param {Object} req - Objeto de solicitud
 * @param {Object} res - Objeto de respuesta
 * @param {Function} next - Función para continuar al siguiente middleware
 */
export const deleteData = async (req, res, next) => {
  try {
    const { id } = req.params;
    
    const result = await query(
      'DELETE FROM "EPC_master" WHERE id = $1 RETURNING id',
      [id]
    );
    
    if (result.rowCount === 0) {
      return res.status(404).json({ 
        error: `No se encontró registro con id ${id}` 
      });
    }
    
    logger.info('Registro eliminado de EPC_master', { id });
    
    res.json({ message: `Registro con id ${id} eliminado correctamente` });
  } catch (error) {
    logger.error('Error al eliminar registro', { 
      id: req.params.id,
      error: error.message 
    });
    next(error);
  }
};
