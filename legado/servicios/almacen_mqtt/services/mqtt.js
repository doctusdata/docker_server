const mqtt = require('mqtt');
const mqttConfig = require('../config/mqtt');
const appConfig = require('../config/app.json');
const dbService = require('./database');
const logger = require('./logger');

class MQTTService {
    constructor() {
        this.client = null;
        this.isClosing = false;
        this.scenarios = appConfig.mqtt.scenarios;
        this.defaultChannel = appConfig.mqtt.defaultChannel;
    }

    connect() {
        try {
            const url = `mqtt://${mqttConfig.host}:${mqttConfig.port}`;
            this.client = mqtt.connect(url, mqttConfig);

            this.client.on('connect', () => {
                console.log('¡Conexión MQTT exitosa!');
                if (!this.isClosing) {
                    this.subscribeToChannels();
                }
            });

            this.client.on('error', (error) => {
                logger.logError(error, 'Error en cliente MQTT');
            });

            this.client.on('reconnect', () => {
                if (!this.isClosing) {
                    console.log('Cliente MQTT reconectando...');
                }
            });

            this.client.on('message', this.handleMessage.bind(this));
        } catch (error) {
            logger.logError(error, 'Inicialización de cliente MQTT');
        }
    }

    subscribeToChannels() {
        try {
            this.client.subscribe(this.defaultChannel + '/#', (error) => {
                if (error) {
                    logger.logError(error, `Suscripción a ${this.defaultChannel}/#`);
                } else {
                    console.log(`Suscrito a ${this.defaultChannel}/#`);
                }
            });

            this.scenarios.forEach(scenario => {
                this.client.subscribe(scenario.channel, (error) => {
                    if (error) {
                        logger.logError(error, `Suscripción a ${scenario.channel}`);
                    } else {
                        console.log(`Suscrito a ${scenario.channel}`);
                    }
                });
            });
        } catch (error) {
            logger.logError(error, 'Suscripción a canales MQTT');
        }
    }

    findScenarioForDevMac(devmac) {
        return this.scenarios.find(scenario => 
            scenario.devmacList.includes(devmac)
        );
    }

    async handleMessage(topic, message) {
        if (this.isClosing) return;

        try {
            const data = JSON.parse(message.toString());
            
            const requiredFields = ['devid', 'devip', 'devmac'];
            const missingFields = requiredFields.filter(field => !(field in data));
            
            if (missingFields.length > 0) {
                throw new Error(`Campos requeridos faltantes: ${missingFields.join(', ')}`);
            }

            if (!data.reads || !Array.isArray(data.reads) || data.reads.length === 0) {
                throw new Error('No hay lecturas válidas en el mensaje');
            }

            const scenario = this.findScenarioForDevMac(data.devmac);
            if (!scenario) {
                throw new Error(`No hay escenario configurado para MAC: ${data.devmac}`);
            }

            const tableConfig = appConfig.database.tables[scenario.tableId];
            if (!tableConfig) {
                throw new Error(`ID de tabla inválido: ${scenario.tableId}`);
            }

            for (const read of data.reads) {
                if (!read.EPC) {
                    logger.logError(new Error('Campo EPC faltante en la lectura'), 'Procesamiento de mensaje MQTT');
                    continue;
                }

                try {
                    const sensorData = {
                        ...data,
                        ...read
                    };

                    await dbService.processSensorData(
                        tableConfig.name,
                        sensorData,
                        scenario.operationType
                    );
                } catch (error) {
                    logger.logError(error, 'Guardado de datos del sensor');
                }
            }
        } catch (error) {
            logger.logError(error, 'Procesamiento de mensaje MQTT');
        }
    }

    close() {
        return new Promise((resolve) => {
            this.isClosing = true;
            if (this.client && this.client.connected) {
                this.client.end(false, () => {
                    console.log('Conexión MQTT cerrada');
                    resolve();
                });
            } else {
                resolve();
            }
        });
    }
}

module.exports = new MQTTService();