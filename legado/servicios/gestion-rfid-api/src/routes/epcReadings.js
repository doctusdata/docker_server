import express from 'express';
import { getStock, getStockTemporal, deleteStockTemporal } from '../controllers/epcReadingsController.js';

const router = express.Router();

/**
 * @route GET /api/epc-readings/stock
 * @desc Obtiene los registros de stock (Stock = 1 and Used IS NULL)
 * @access Privado (requiere API Key)
 */
router.get('/stock', getStock);

/**
 * @route GET /api/epc-readings/stock-temporal
 * @desc Obtiene los registros de stock temporal (Stock = 0 and Used IS NULL)
 * @access Privado (requiere API Key)
 */
router.get('/stock-temporal', getStockTemporal);

/**
 * @route DELETE /api/epc-readings/stock-temporal
 * @desc Elimina todos los registros con Stock=0
 * @access Privado (requiere API Key)
 */
router.delete('/stock-temporal', deleteStockTemporal);

export default router;