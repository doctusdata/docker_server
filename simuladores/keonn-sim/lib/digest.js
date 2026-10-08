'use strict';
const crypto = require('crypto');

const md5 = (s) => crypto.createHash('md5').update(s).digest('hex');

/**
 * Autenticacion HTTP Digest (RFC 2617, qop="auth"), tal como la piden
 * los lectores Keonn a traves de AdvanNetManager.
 */
class DigestAuth {
    constructor({ user, pass, realm }) {
        this.user = user;
        this.pass = pass;
        this.realm = realm;
        this.opaque = crypto.randomBytes(16).toString('hex');
        this.nonces = new Map(); // nonce -> { created, nc }
    }

    newNonce() {
        const nonce = crypto.randomBytes(16).toString('hex');
        this.nonces.set(nonce, { created: Date.now(), nc: new Set() });
        this.gc();
        return nonce;
    }

    gc() {
        const limit = Date.now() - 5 * 60 * 1000;
        for (const [nonce, info] of this.nonces) {
            if (info.created < limit) this.nonces.delete(nonce);
        }
    }

    challenge(res, stale = false) {
        const nonce = this.newNonce();
        res.writeHead(401, {
            'WWW-Authenticate': `Digest realm="${this.realm}", qop="auth", ` +
                `nonce="${nonce}", opaque="${this.opaque}"` +
                (stale ? ', stale=true' : ''),
            'Content-Type': 'text/plain'
        });
        res.end('Unauthorized');
    }

    /** Parsea la cabecera Authorization: Digest k=v, k="v", ... */
    static parse(header) {
        const out = {};
        const re = /(\w+)=(?:"([^"]*)"|([^,]*))/g;
        let m;
        while ((m = re.exec(header)) !== null) {
            out[m[1]] = m[2] !== undefined ? m[2] : (m[3] || '').trim();
        }
        return out;
    }

    /**
     * Devuelve true si la peticion esta autenticada. Si no, responde 401
     * con el challenge y devuelve false.
     */
    check(req, res) {
        const header = req.headers.authorization;
        if (!header || !header.startsWith('Digest ')) {
            this.challenge(res);
            return false;
        }

        const d = DigestAuth.parse(header.slice(7));
        const info = this.nonces.get(d.nonce);
        if (!info) {
            this.challenge(res, true); // nonce caducado o desconocido
            return false;
        }
        // Proteccion frente a replay: cada nc debe usarse una sola vez.
        if (d.nc && info.nc.has(d.nc)) {
            this.challenge(res, true);
            return false;
        }

        const uri = d.uri || req.url;
        const ha1 = md5(`${this.user}:${this.realm}:${this.pass}`);
        const ha2 = md5(`${req.method}:${uri}`);
        const expected = d.qop
            ? md5(`${ha1}:${d.nonce}:${d.nc}:${d.cnonce}:${d.qop}:${ha2}`)
            : md5(`${ha1}:${d.nonce}:${ha2}`);

        if (d.username !== this.user || d.response !== expected) {
            this.challenge(res);
            return false;
        }

        if (d.nc) info.nc.add(d.nc);
        return true;
    }
}

module.exports = { DigestAuth };
