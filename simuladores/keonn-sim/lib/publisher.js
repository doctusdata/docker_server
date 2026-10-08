'use strict';
const mqtt = require('mqtt');

/**
 * Publicador MQTT del lector. Reproduce la trama que emiten los Keonn
 * (evento TAG_READ) tal como la espera almacen_mqtt:
 *   { devid, devip, devmac, reads: [ { EPC, Antenna, RSSI } ] }
 * Antenna y RSSI van como STRING, igual que el lector real.
 */
class Publisher {
    constructor(cfg, pool, log) {
        this.cfg = cfg;
        this.pool = pool;
        this.log = log;
        this.client = null;
        this.timer = null;
        this.published = 0;
        this.lastFrame = null;
    }

    connect() {
        const opts = {
            clientId: this.cfg.mqtt.clientId,
            username: this.cfg.mqtt.user,
            password: this.cfg.mqtt.pass,
            keepalive: 60,
            reconnectPeriod: 2000,
            connectTimeout: 10000,
            clean: true
        };
        this.client = mqtt.connect(this.cfg.mqtt.url, opts);
        this.client.on('connect', () => this.log(`MQTT conectado a ${this.cfg.mqtt.url}`));
        this.client.on('error', (e) => this.log(`MQTT error: ${e.message}`));
        this.client.on('reconnect', () => this.log('MQTT reconectando...'));
    }

    buildFrame(epcs) {
        const { rssiMin, rssiMax } = this.cfg;
        const muertas = this.cfg.antenasMuertas || new Set();
        const antennas = this.cfg.antennas.filter((a) => !muertas.has(a));
        if (!antennas.length) return null;
        return {
            devid: this.cfg.devid,
            devip: this.cfg.devip,
            devmac: this.cfg.devmac,
            reads: epcs.map((epc) => ({
                EPC: epc,
                Antenna: String(antennas[Math.floor(Math.random() * antennas.length)]),
                RSSI: String(Math.floor(rssiMin + Math.random() * (rssiMax - rssiMin)))
            }))
        };
    }

    /** Publica una trama con los EPCs dados (o del pool si no se indican). */
    emit(epcs) {
        const tags = epcs && epcs.length ? epcs : this.pool.pick(this.cfg.tagsPerCycle);
        if (!tags.length) return null;
        const frame = this.buildFrame(tags);
        if (!frame) return null;
        if (this.client && this.client.connected) {
            this.client.publish(this.cfg.mqtt.topic, JSON.stringify(frame), { qos: 0 });
            this.published += 1;
            this.lastFrame = { at: new Date().toISOString(), tags: tags.length };
        } else {
            this.log('AVISO: trama descartada, MQTT sin conexion');
        }
        return frame;
    }

    start() {
        if (this.timer) return false;
        this.log(`RF ON - emitiendo cada ${this.cfg.rfPeriodMs} ms en ${this.cfg.mqtt.topic}`);
        this.timer = setInterval(() => {
            try {
                const frame = this.emit();
                if (frame && this.cfg.onEmit) this.cfg.onEmit(frame);
            } catch (err) {
                this.log(`Error emitiendo trama: ${err.message}`);
            }
        }, this.cfg.rfPeriodMs);
        return true;
    }

    stop() {
        if (!this.timer) return false;
        clearInterval(this.timer);
        this.timer = null;
        this.log('RF OFF');
        return true;
    }

    get running() { return this.timer !== null; }

    close() {
        this.stop();
        if (this.client) this.client.end(true);
    }
}

module.exports = { Publisher };
