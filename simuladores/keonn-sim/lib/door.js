'use strict';
const { Pool } = require('pg');

/**
 * Emula el Read mode SQL_EAS_ALARM del lector de puerta: por cada EPC leido
 * consulta user_room por JDBC (aqui pg) y, si el EPC no esta autorizado para
 * esa puerta, dispara la alarma (GPO + buzzer en el lector real).
 *
 * OJO: user_room y sus columnas van en minusculas y SIN comillas; solo
 * Bin / EPC_master / EPC_readings / User_readings son case-sensitive.
 */
class DoorAlarm {
    constructor(cfg, log) {
        this.cfg = cfg;
        this.log = log;
        this.alarms = [];
        this.pool = new Pool({
            host: cfg.pg.host,
            port: cfg.pg.port,
            user: cfg.pg.user,
            password: cfg.pg.password,
            database: cfg.pg.database,
            max: 4,
            connectionTimeoutMillis: 5000
        });
        this.pool.on('error', (e) => this.log(`Pool puerta error: ${e.message}`));
        this.cache = new Map(); // epc -> { at, authorized }  (TTL 1500 ms como el lector)
    }

    async check(epc) {
        const hit = this.cache.get(epc);
        if (hit && Date.now() - hit.at < 1500) return hit.authorized;

        let authorized = false;
        try {
            const res = await this.pool.query(
                'SELECT state FROM user_room WHERE epc = $1 AND state = 1 AND door = $2',
                [epc, this.cfg.devid]
            );
            authorized = res.rowCount > 0;
        } catch (err) {
            this.log(`Error consultando user_room: ${err.message}`);
            return null; // error de BBDD: no se afirma nada
        }

        this.cache.set(epc, { at: Date.now(), authorized });
        if (authorized) {
            this.log(`[OK] devid=${this.cfg.devid} EPC=${epc} -> autorizado`);
        } else {
            this.log(`[ALARM] devid=${this.cfg.devid} EPC=${epc} -> NO AUTORIZADO. GPO pulse 200ms + buzzer`);
            this.alarms.unshift({ at: new Date().toISOString(), epc, devid: this.cfg.devid });
            this.alarms = this.alarms.slice(0, 50);
        }
        return authorized;
    }

    /** Evalua todos los EPCs de una trama recien emitida. */
    async onFrame(frame) {
        for (const read of frame.reads) {
            await this.check(read.EPC);
        }
    }

    close() { return this.pool.end().catch(() => {}); }
}

module.exports = { DoorAlarm };
