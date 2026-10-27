'use strict';
/**
 * Envoltorio HTTP del Servicio_postgresql.
 *
 * En el sistema real, Node-RED lanza el batch por SSH:
 *   ssh rfidroom@192.168.1.155 "node /opt/Servicio_postgresql/index.js"
 * Aqui se expone GET /run, que ejecuta index.js como proceso hijo. index.js
 * NO se modifica: sigue siendo el one-shot original y cada invocacion es un
 * proceso nuevo, con la misma semantica que el SSH.
 */
const http = require('http');
const path = require('path');
const { execFile } = require('child_process');

const PORT = Number(process.env.PORT || 8081);
const SCRIPT = path.join(__dirname, 'index.js');
let running = false;

http.createServer((req, res) => {
    const pathname = req.url.split('?')[0].replace(/\/+$/, '') || '/';

    if (pathname === '/health') {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        return res.end(JSON.stringify({ ok: true, running }));
    }
    if (pathname !== '/run') {
        res.writeHead(404, { 'Content-Type': 'application/json' });
        return res.end(JSON.stringify({ error: 'not found' }));
    }
    // El batch no es reentrante: si ya hay una pasada en curso, se rechaza.
    if (running) {
        res.writeHead(409, { 'Content-Type': 'application/json' });
        return res.end(JSON.stringify({ ok: false, error: 'batch ya en ejecucion' }));
    }

    running = true;
    const started = Date.now();
    console.log(`[${new Date().toISOString()}] Lanzando batch ${SCRIPT}`);

    execFile(process.execPath, [SCRIPT], { timeout: 120000, cwd: __dirname },
        (err, stdout, stderr) => {
            running = false;
            const ms = Date.now() - started;
            if (err) console.error(`Batch fallido (${ms} ms): ${err.message}`);
            else console.log(`Batch completado en ${ms} ms`);
            res.writeHead(err ? 500 : 200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ ok: !err, ms, stdout, stderr }));
        });
}).listen(PORT, '0.0.0.0', () => {
    console.log(`Servicio_postgresql escuchando en :${PORT} (GET /run)`);
});
