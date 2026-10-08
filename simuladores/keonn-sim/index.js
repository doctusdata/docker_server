'use strict';
/**
 * Simulador de lector RFID Keonn AdvanReader-m4-160.
 *
 * Reproduce las dos interfaces que usa el sistema real:
 *   - REST /device/start y /device/stop con HTTP Digest (AdvanNetManager),
 *     que es lo que Node-RED invoca para abrir y cerrar la ventana de RF.
 *   - Publicacion MQTT de tramas TAG_READ mientras el lector esta "started".
 *
 * Todo se parametriza por variables de entorno para instanciar el mismo
 * servicio como lector de almacen, de puerta o de papeleras.
 */
const http = require('http');
const url = require('url');
const { DigestAuth } = require('./lib/digest');
const { EpcPool } = require('./lib/epcpool');
const { Publisher } = require('./lib/publisher');

const env = process.env;
const num = (v, d) => (v === undefined || v === '' ? d : Number(v));
const bool = (v, d) => (v === undefined || v === '' ? d : /^(1|true|yes)$/i.test(v));

const cfg = {
    mode: env.MODE || 'warehouse',            // warehouse | door | bin
    devid: env.DEVID || 'Almacen-1',
    devip: env.DEVIP || '127.0.0.1',
    devmac: env.DEVMAC || '00:00:00:00:00:00',
    httpPort: num(env.HTTP_PORT, 80),
    advannetPort: num(env.ADVANNET_PORT, 0),  // 3161 en el lector de papeleras
    rfPeriodMs: num(env.RF_PERIOD_MS, 1600),
    tagsPerCycle: num(env.TAGS_PER_CYCLE, 12),
    antennas: (env.ANTENNAS || '1,2').split(',').map((s) => s.trim()).filter(Boolean),
    // Antenas "averiadas": el lector sigue leyendo por las demas. Tambien en caliente con
    // /sim/antena?muerta=3 y /sim/antena?viva=3.
    antenasMuertas: new Set((env.ANTENAS_MUERTAS || '').split(',').map((s) => s.trim()).filter(Boolean)),
    rssiMin: num(env.RSSI_MIN, -70),
    rssiMax: num(env.RSSI_MAX, -40),
    epcSource: env.EPC_SOURCE || 'db',        // db | env
    epcList: (env.EPC_LIST || '').split(',').map((s) => s.trim()).filter(Boolean),
    poolSize: num(env.POOL_SIZE, 400),
    sweep: bool(env.SWEEP, false),
    foreignRatio: num(env.FOREIGN_RATIO, 0),
    startAuto: bool(env.START_AUTO, false),
    digest: {
        user: env.DIGEST_USER || 'admin',
        pass: env.DIGEST_PASS || 'admin',
        realm: env.DIGEST_REALM || 'AdvanNet'
    },
    mqtt: {
        url: env.MQTT_URL || 'mqtt://192.168.1.155:1883',
        user: env.MQTT_USER || 'gestion_rfid',
        pass: env.MQTT_PASS || 'rfid_room@',
        topic: env.MQTT_TOPIC || 'TAG_readings/scenario1',
        clientId: env.MQTT_CLIENT_ID || `keonn-sim-${env.DEVIP || 'x'}`
    },
    pg: {
        host: env.PGHOST || '192.168.1.155',
        port: num(env.PGPORT, 5432),
        user: env.PGUSER || 'rfidroom',
        password: env.PGPASSWORD || 'rfidroom@2025',
        database: env.PGDATABASE || 'gestion_rfid'
    }
};

const log = (msg) => console.log(`[${new Date().toISOString()}] [${cfg.devid}@${cfg.devip}] ${msg}`);

const pool = new EpcPool(cfg, log);
let door = null;
if (cfg.mode === 'door') {
    const { DoorAlarm } = require('./lib/door');
    door = new DoorAlarm(cfg, log);
    // Cada trama emitida se evalua contra user_room, como hace el lector real.
    cfg.onEmit = (frame) => door.onFrame(frame).catch((e) => log(`onFrame: ${e.message}`));
}
const publisher = new Publisher(cfg, pool, log);

const auth = new DigestAuth(cfg.digest);
const json = (res, code, body) => {
    res.writeHead(code, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(body));
};

const server = http.createServer(async (req, res) => {
    const parsed = url.parse(req.url, true);
    const path = parsed.pathname.replace(/\/+$/, '') || '/';

    // Endpoints auxiliares del simulador: sin auth, para healthcheck y pruebas.
    if (path === '/device/status') {
        return json(res, 200, {
            devid: cfg.devid, devip: cfg.devip, devmac: cfg.devmac, mode: cfg.mode,
            state: publisher.running ? 'started' : 'stopped',
            poolReady: pool.ready, poolSize: pool.tags.length,
            published: publisher.published, lastFrame: publisher.lastFrame
        });
    }
    if (path === '/device/alarms') {
        return json(res, 200, { alarms: door ? door.alarms : [] });
    }

    // A partir de aqui, todo exige HTTP Digest, como AdvanNetManager.
    if (!auth.check(req, res)) return;

    if (path === '/device/start') {
        const changed = publisher.start();
        return json(res, 200, { result: 'OK', state: 'started', changed });
    }
    if (path === '/device/stop') {
        const changed = publisher.stop();
        return json(res, 200, { result: 'OK', state: 'stopped', changed });
    }
    // Fuerza la lectura de un EPC concreto sin esperar al ciclo de RF.
    if (path === '/device/inject') {
        const epcs = (parsed.query.epc || '').split(',').map((s) => s.trim()).filter(Boolean);
        if (!epcs.length) return json(res, 400, { error: 'falta el parametro epc' });
        const frame = publisher.emit(epcs);
        if (door && frame) await door.onFrame(frame);
        return json(res, 200, { result: 'OK', frame });
    }
    // Solo simulador: sacar / devolver articulos del campo del lector.
    if (path === '/sim/retirar' || path === '/sim/devolver') {
        const epcs = (parsed.query.epc || '').split(',').map((s) => s.trim()).filter(Boolean);
        if (path === '/sim/retirar') pool.retirar(epcs); else pool.devolver(epcs);
        return json(res, 200, { result: 'OK', ausentes: [...pool.ausentes] });
    }
    if (path === '/sim/antena') {
        if (parsed.query.muerta) cfg.antenasMuertas.add(String(parsed.query.muerta));
        if (parsed.query.viva) cfg.antenasMuertas.delete(String(parsed.query.viva));
        return json(res, 200, { result: 'OK', muertas: [...cfg.antenasMuertas] });
    }
    // La API AdvanNet responde al identificador del dispositivo.
    if (path.startsWith('/device/')) {
        return json(res, 200, { result: 'OK', device: path.slice('/device/'.length) });
    }
    return json(res, 404, { error: 'not found' });
});

async function main() {
    publisher.connect();
    await pool.load();
    server.listen(cfg.httpPort, '0.0.0.0', () => {
        log(`REST AdvanNetManager en :${cfg.httpPort} (digest ${cfg.digest.user}), modo ${cfg.mode}`);
    });
    if (cfg.advannetPort) {
        // Segundo listener para la API AdvanNet del lector de papeleras (:3161).
        http.createServer(server.listeners('request')[0])
            .listen(cfg.advannetPort, '0.0.0.0', () => log(`API AdvanNet en :${cfg.advannetPort}`));
    }
    if (cfg.startAuto) {
        publisher.start();
        log('START_AUTO activo: el lector arranca emitiendo');
    } else {
        log('Lector en estado stopped, esperando /device/start');
    }
}

let closing = false;
async function shutdown() {
    if (closing) return;
    closing = true;
    log('Cerrando...');
    publisher.close();
    if (door) await door.close();
    server.close(() => process.exit(0));
    setTimeout(() => process.exit(0), 3000).unref();
}
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

main().catch((err) => { log(`Fallo al arrancar: ${err.stack}`); process.exit(1); });
