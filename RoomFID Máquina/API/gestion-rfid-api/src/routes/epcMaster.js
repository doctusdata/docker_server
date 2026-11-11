import express from 'express';
import { 
  readAll, 
  readByEpc, 
  readByShortDescription,
  readByAlmacen,
  insertData, 
  updateData, 
  deleteData 
} from '../controllers/epcMasterController.js';

const router = express.Router();

/**
 * @route GET /api/epc-master
 * @desc Obtiene todos los registros de EPC_master
 * @access Privado (requiere API Key)
 */
router.get('/', readAll);

/**
 * @route GET /api/epc-master/epc/:epc
 * @desc Obtiene registros filtrados por EPC
 * @access Privado (requiere API Key)
 */
router.get('/epc/:epc', readByEpc);

/**
 * @route GET /api/epc-master/description/:description
 * @desc Obtiene registros filtrados por descripción
 * @access Privado (requiere API Key)
 */
router.get('/description/:description', readByShortDescription);

/**
 * @route GET /api/epc-master/almacen/:almacen
 * @desc Obtiene registros filtrados por almacén
 * @access Privado (requiere API Key)
 */
router.get('/almacen/:almacen', readByAlmacen);

/**
 * @route POST /api/epc-master
 * @desc Inserta un nuevo registro
 * @access Privado (requiere API Key)
 */
router.post('/', insertData);

/**
 * @route PUT /api/epc-master/:id
 * @desc Actualiza un registro existente
 * @access Privado (requiere API Key)
 */
router.put('/:id', updateData);

/**
 * @route DELETE /api/epc-master/:id
 * @desc Elimina un registro existente
 * @access Privado (requiere API Key)
 */
router.delete('/:id', deleteData);

export default router;
