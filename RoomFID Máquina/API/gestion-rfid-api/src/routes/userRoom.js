import express from 'express';
import { 
  readAll, 
  readByEpc, 
  readByDoor, 
  insertData, 
  updateData, 
  deleteData,
  deleteAllUserRoom
} from '../controllers/userRoomController.js';

const router = express.Router();

/**
 * @route GET /api/user-room
 * @desc Obtiene todos los registros de user_room
 * @access Privado (requiere API Key)
 */
router.get('/', readAll);

/**
 * @route GET /api/user-room/epc/:epc
 * @desc Obtiene registros filtrados por EPC
 * @access Privado (requiere API Key)
 */
router.get('/epc/:epc', readByEpc);

/**
 * @route GET /api/user-room/door/:door
 * @desc Obtiene registros filtrados por puerta
 * @access Privado (requiere API Key)
 */
router.get('/door/:door', readByDoor);

/**
 * @route POST /api/user-room
 * @desc Inserta un nuevo registro
 * @access Privado (requiere API Key)
 */
router.post('/', insertData);

/**
 * @route PUT /api/user-room/:id
 * @desc Actualiza un registro existente
 * @access Privado (requiere API Key)
 */
router.put('/:id', updateData);

/**
 * @route DELETE /api/user-room/:id
 * @desc Elimina un registro existente
 * @access Privado (requiere API Key)
 */
router.delete('/:id', deleteData);

/**
 * @route DELETE /api/user-room
 * @desc Elimina todos los registros de user_room
 * @access Privado (requiere API Key)
 */
router.delete('/', deleteAllUserRoom);

export default router;