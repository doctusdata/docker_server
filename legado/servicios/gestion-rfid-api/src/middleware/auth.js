import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import logger from '../utils/logger.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const configPath = path.join(__dirname, '../../config/app.json');
const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));

/**
 * Middleware para validar la API Key en las solicitudes
 * @param {Object} req - Objeto de solicitud
 * @param {Object} res - Objeto de respuesta
 * @param {Function} next - Función para continuar al siguiente middleware
 */
export const validateApiKey = (req, res, next) => {
  const apiKey = req.headers['x-api-key'];
  
  if (!apiKey) {
    logger.warn('Intento de acceso sin API Key');
    return res.status(401).json({ 
      error: 'No se proporcionó una API Key' 
    });
  }
  
  if (apiKey !== config.apiKey) {
    logger.warn('Intento de acceso con API Key inválida', { 
      providedKey: apiKey 
    });
    return res.status(403).json({ 
      error: 'API Key inválida' 
    });
  }
  
  next();
};