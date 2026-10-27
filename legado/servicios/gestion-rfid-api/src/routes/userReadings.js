import express from 'express';
import { getUserDoor, deleteAllUserReadings } from '../controllers/userReadingsController.js';

const router = express.Router();

/**
 * @route GET /api/user-readings/user-door
 * @desc Obtiene los registros de usuarios en puertas
 * @access Privado (requiere API Key)
 */
router.get('/user-door', getUserDoor);

/**
 * @route DELETE /api/user-readings
 * @desc Elimina todos los registros de User_readings
 * @access Privado (requiere API Key)
 */
router.delete('/', deleteAllUserReadings);

export default router;