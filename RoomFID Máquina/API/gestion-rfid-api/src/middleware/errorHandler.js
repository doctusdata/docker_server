import logger from '../utils/logger.js';

/**
 * Middleware para manejar errores en la aplicación
 * @param {Error} err - Objeto de error
 * @param {Object} req - Objeto de solicitud
 * @param {Object} res - Objeto de respuesta
 * @param {Function} next - Función para continuar al siguiente middleware
 */
export const errorHandler = (err, req, res, next) => {
  // Registrar el error
  logger.error('Error en la aplicación:', {
    message: err.message,
    stack: err.stack,
    path: req.path,
    method: req.method,
    body: req.body,
    params: req.params,
    query: req.query
  });

  // Determinar el código de estado HTTP
  const statusCode = err.statusCode || 500;
  
  // Enviar respuesta al cliente
  res.status(statusCode).json({
    error: {
      message: err.message || 'Error interno del servidor',
      status: statusCode,
      timestamp: new Date().toISOString()
    }
  });
};