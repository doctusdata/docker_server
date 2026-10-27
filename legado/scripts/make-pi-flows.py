#!/usr/bin/env python3
"""
Genera el flows.json para la Raspberry REAL (192.168.0.64).

Parte del flow de la entrega (RoomFID Maquina) y lo reapunta a la replica,
que corre en 192.168.0.4 con los puertos publicados en la LAN. La Pi no ve
la subred interna 192.168.1.0/24, de ahi la traduccion.

A diferencia del flow del contenedor, aqui SI hay GPIO real: los nodos
rpi-gpio se conservan intactos.
"""
import json, os, re

# Las rutas son relativas a legado/, como en deploy-pi.sh: asi da igual
# desde donde se lance.
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

SRC = '../RoomFID Máquina/Raspberry PI4B2GB/Node-Red/flows(json).json'
DST = 'raspberry/flows.json'
HOST = '192.168.0.4'

# Lector .157/.158/.159/.205 -> puerto publicado en el host de la replica
READER_PORTS = {'157': 8157, '158': 8158, '159': 8159, '205': 8205}
ADVANNET_PORT = 8206   # el :3161 del lector de papeleras

flows = json.load(open(SRC, encoding='utf-8'))
changes = []

for n in flows:
    # --- URLs de los lectores -------------------------------------------
    if n.get('type') == 'http request' and n.get('url'):
        u = n['url']
        m = re.match(r'http://192\.168\.1\.(\d+)(:(\d+))?(/.*)?$', u)
        if m:
            octet, _, port, path = m.groups()
            newport = ADVANNET_PORT if port == '3161' else READER_PORTS.get(octet)
            if newport:
                n['url'] = f'http://{HOST}:{newport}{path or ""}'
                changes.append(f"  http request: {u} -> {n['url']}")

    # --- Conexiones a PostgreSQL ----------------------------------------
    if n.get('type') == 'postgreSQLConfig':
        old = f"{n.get('host')}:{n.get('port')}"
        n['host'] = HOST
        n['port'] = 15432          # el 5432 del host ya estaba ocupado
        changes.append(f"  postgres: {old} -> {HOST}:15432")

    # --- El batch: ssh -> http ------------------------------------------
    if n.get('type') == 'exec' and 'Servicio_postgresql' in (n.get('command') or ''):
        downstream = n['wires'][2]     # el exec usa la 3a salida (rc)
        n.clear()
        n.update({
            'id': '183df94db72218e1',
            'type': 'http request',
            'z': 'd19775192262c84c',
            'name': 'Batch Servicio_postgresql',
            'method': 'GET', 'ret': 'txt', 'paytoqs': 'ignore',
            'url': f'http://{HOST}:8081/run',
            'tls': '', 'persist': False, 'proxy': '',
            'insecureHTTPParser': False, 'authType': '', 'senderr': False,
            'headers': [], 'x': 1010, 'y': 700,
            'wires': [downstream],
        })
        changes.append(f"  exec ssh -> http request GET http://{HOST}:8081/run")

json.dump(flows, open(DST, 'w', encoding='utf-8'), indent=4, ensure_ascii=False)
print(f'{DST} generado desde la entrega. Cambios:')
for c in changes:
    print(c)
print('\nLos nodos rpi-gpio se conservan: en la Pi real SI hay GPIO.')
