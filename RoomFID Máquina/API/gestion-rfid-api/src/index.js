import express from 'express';
import cors from 'cors';
import helmet from 'helmet';
import morgan from 'morgan';
import dotenv from 'dotenv';
import { fileURLToPath } from 'url';
import path from 'path';
import fs from 'fs';

// Importar rutas
import epcReadingsRoutes from './routes/epcReadings.js';
import userReadingsRoutes from './routes/userReadings.js';
import binRoutes from './routes/bin.js';
import userRoomRoutes from './routes/userRoom.js';
import epcMasterRoutes from './routes/epcMaster.js';

// Importar middleware
import { validateApiKey } from './middleware/auth.js';
import { errorHandler } from './middleware/errorHandler.js';

// Importar logger
import logger from './utils/logger.js';

// Configuración
dotenv.config();

// Cargar configuración desde app.json
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const configPath = path.join(__dirname, '../config/app.json');
const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));

const app = express();
const PORT = config.port || 3000;
const HOST = '0.0.0.0'; // Escuchar en todas las interfaces de red

// Middleware
app.use(helmet({
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      scriptSrc: ["'self'", "'unsafe-inline'", "cdnjs.cloudflare.com"],
      styleSrc: ["'self'", "'unsafe-inline'", "cdnjs.cloudflare.com"],
      imgSrc: ["'self'", "data:"],
      fontSrc: ["'self'", "cdnjs.cloudflare.com"]
    }
  }
}));
app.use(cors());
app.use(express.json());
app.use(morgan('combined'));

// Servir archivos estáticos desde la carpeta www
app.use(express.static(path.join(__dirname, '../www')));

// Ruta para obtener la API Key (solo para el cliente web)
app.get('/api/config', (req, res) => {
  const origin = req.headers.origin || req.headers.referer;
  const clientIp = req.ip || req.connection.remoteAddress;
  
  logger.info('Solicitud de API Key recibida', { 
    origin, 
    clientIp,
    headers: req.headers
  });
  
  const isLocalNetwork = clientIp.startsWith('192.168.') || 
                        clientIp.startsWith('10.') || 
                        clientIp.startsWith('172.16.') ||
                        clientIp.includes('127.0.0.1') || 
                        clientIp.includes('::1');
  
  if (isLocalNetwork) {
    res.json({ apiKey: config.apiKey });
    logger.info('API Key enviada al cliente', { clientIp });
  } else {
    logger.warn('Intento de acceso no autorizado a la API Key', { origin, clientIp });
    res.status(403).json({ error: 'Acceso no autorizado' });
  }
});

// Validación de API Key para rutas de la API
app.use('/api/epc-readings', validateApiKey);
app.use('/api/user-readings', validateApiKey);
app.use('/api/bin', validateApiKey);
app.use('/api/user-room', validateApiKey);
app.use('/api/epc-master', validateApiKey);

// Rutas de la API
app.use('/api/epc-readings', epcReadingsRoutes);
app.use('/api/user-readings', userReadingsRoutes);
app.use('/api/bin', binRoutes);
app.use('/api/user-room', userRoomRoutes);
app.use('/api/epc-master', epcMasterRoutes);

// Ruta principal para servir la interfaz web
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, '../www/api.html'));
});

// Ruta de prueba API
app.get('/api', (req, res) => {
  res.json({ message: 'API de Gestión RFID funcionando correctamente' });
});

// Middleware de manejo de errores
app.use(errorHandler);

// Iniciar servidor
app.listen(PORT, HOST, () => {
  logger.info(`Servidor iniciado en ${HOST}:${PORT}`);
  logger.info(`Modo: ${process.env.NODE_ENV || 'desarrollo'}`);
  logger.info(`Interfaz web disponible en http://${HOST}:${PORT}`);
});

export default app;
