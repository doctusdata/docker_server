import express from 'express';
import { getStockConsumption, deleteAllBin } from '../controllers/binController.js';

const router = express.Router();

/**
 * @route GET /api/bin/stock-consumption
 * @desc Obtiene los registros de consumo de stock
 * @access Privado (requiere API Key)
 */
router.get('/stock-consumption', getStockConsumption);

/**
 * @route DELETE /api/bin
 * @desc Elimina todos los registros de Bin
 * @access Privado (requiere API Key)
 */
router.delete('/', deleteAllBin);

export default router;