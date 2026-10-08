'use strict';
const { Client } = require('pg');
const crypto = require('crypto');

/** EPC inventado, 24 caracteres hex, con el prefijo que usa el sistema. */
function randomEpc(prefix = '9999') {
    const rest = crypto.randomBytes(16).toString('hex').slice(0, 24 - prefix.length);
    return prefix + rest;
}

/**
 * Pool de EPCs que emite el lector. Con EPC_SOURCE=db se cargan desde
 * EPC_master para que las lecturas correspondan a material catalogado
 * (si no, processForeignDelete las borraria en cada pasada del batch).
 */
class EpcPool {
    constructor(cfg, log) {
        this.cfg = cfg;
        this.log = log;
        this.tags = [];
        this.ready = false;
        // EPCs "fuera del campo": simulan un articulo que sale del almacen.
        this.ausentes = new Set();
        this.cursor = 0;
    }

    retirar(epcs) { epcs.forEach((e) => this.ausentes.add(e)); }
    devolver(epcs) { epcs.forEach((e) => this.ausentes.delete(e)); }

    async load() {
        if (this.cfg.epcSource === 'env') {
            this.tags = this.cfg.epcList;
            this.ready = true;
            this.log(`Pool de EPCs desde EPC_LIST: ${this.tags.length} tags`);
            return;
        }
        // Reintentos con backoff: postgres puede estar todavia restaurando el dump.
        const deadline = Date.now() + 60000;
        let delay = 1000;
        while (Date.now() < deadline) {
            try {
                const tags = await this.queryMaster();
                if (tags.length > 0) {
                    this.tags = tags;
                    this.ready = true;
                    this.log(`Pool de EPCs desde EPC_master: ${tags.length} tags`);
                    return;
                }
                this.log('EPC_master todavia vacio, reintentando...');
            } catch (err) {
                this.log(`Esperando a PostgreSQL: ${err.message}`);
            }
            await new Promise((r) => setTimeout(r, delay));
            delay = Math.min(delay * 2, 8000);
        }
        // Sin pool de BBDD no se aborta: se sigue con EPCs sinteticos y se
        // reintenta en segundo plano, para no tumbar el contenedor.
        this.log('AVISO: no se pudo cargar el pool desde EPC_master; usando EPCs sinteticos');
        this.tags = Array.from({ length: 20 }, () => randomEpc());
        this.ready = true;
        setTimeout(() => this.load().catch(() => {}), 30000);
    }

    async queryMaster() {
        const client = new Client({
            host: this.cfg.pg.host,
            port: this.cfg.pg.port,
            user: this.cfg.pg.user,
            password: this.cfg.pg.password,
            database: this.cfg.pg.database,
            connectionTimeoutMillis: 5000
        });
        await client.connect();
        try {
            // El filtro por almacen solo aplica a los lectores de almacen; para el
            // resto se coge cualquier EPC catalogado. Cada consulta lleva
            // exactamente los parametros que usa: un $1 sobrante da error.
            const res = this.cfg.mode === 'warehouse'
                ? await client.query(
                    'SELECT "EPC" FROM "EPC_master" WHERE "Almacen" = $1 ORDER BY random() LIMIT $2',
                    [this.cfg.devid, this.cfg.poolSize])
                : await client.query(
                    'SELECT "EPC" FROM "EPC_master" ORDER BY random() LIMIT $1',
                    [this.cfg.poolSize]);
            return res.rows.map((r) => r.EPC).filter(Boolean);
        } finally {
            await client.end().catch(() => {});
        }
    }

    /**
     * Devuelve n EPCs, mezclando foraneos segun FOREIGN_RATIO.
     * Con SWEEP=true recorre el pool en rueda, como un lector real que inventaria todo
     * el campo en cada ventana; si no, al azar (comportamiento original).
     */
    pick(n) {
        const out = [];
        const presentes = this.tags.filter((t) => !this.ausentes.has(t));
        for (let i = 0; i < n; i++) {
            if (this.cfg.foreignRatio > 0 && Math.random() < this.cfg.foreignRatio) {
                out.push(randomEpc());
            } else if (presentes.length > 0) {
                if (this.cfg.sweep) {
                    out.push(presentes[this.cursor % presentes.length]);
                    this.cursor += 1;
                } else {
                    out.push(presentes[Math.floor(Math.random() * presentes.length)]);
                }
            }
        }
        return out;
    }
}

module.exports = { EpcPool, randomEpc };
