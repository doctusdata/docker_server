#!/usr/bin/env python3
"""
Parchea flows.json para la replica en Docker.

Solo dos sustituciones, porque no hay hardware detras:
  1. El nodo exec que lanzaba el batch por SSH -> http request al envoltorio.
  2. Los dos rpi-gpio in -> inject (no hay GPIO en un contenedor).

Todo lo demas se deja exactamente como lo entrego el cliente.
"""
import json, sys, shutil

PATH = 'docker/nodered/flows.json'
BATCH_URL = 'http://192.168.1.163:8081/run'

flows = json.load(open(PATH, encoding='utf-8'))
byid = {n['id']: n for n in flows}
changes = []

# --- 1. exec ssh -> http request -------------------------------------------
EXEC_ID = '183df94db72218e1'
ex = byid[EXEC_ID]
assert ex['type'] == 'exec', f'{EXEC_ID} no es un exec'
# El exec tiene 3 salidas y el flujo usa la tercera (rc); http request solo
# tiene una, asi que esos destinos pasan a ser la unica salida.
downstream = ex['wires'][2]
flows[flows.index(ex)] = {
    'id': EXEC_ID,
    'type': 'http request',
    'z': ex['z'],
    'name': 'Batch Servicio_postgresql',
    'method': 'GET',
    'ret': 'txt',
    'paytoqs': 'ignore',
    'url': BATCH_URL,
    'tls': '',
    'persist': False,
    'proxy': '',
    'insecureHTTPParser': False,
    'authType': '',
    'senderr': False,
    'headers': [],
    'x': ex['x'],
    'y': ex['y'],
    'wires': [downstream],
}
changes.append(f'exec ssh -> http request GET {BATCH_URL} (salida -> {downstream})')

# --- 2. rpi-gpio in -> inject ----------------------------------------------
# OJO: la funcion "function 10" compara msg.payload === 1 de forma estricta,
# asi que el inject debe ser numerico, no string.
for gid in ('6fba9d46ec5d2b5d', 'f1c2e7f27d291a8c'):
    g = byid[gid]
    assert g['type'] == 'rpi-gpio in', f'{gid} no es rpi-gpio in'
    flows[flows.index(g)] = {
        'id': gid,
        'type': 'inject',
        'z': g['z'],
        'name': g.get('name', ''),
        'props': [{'p': 'payload'}],
        'repeat': '',
        'crontab': '',
        'once': False,
        'onceDelay': 0.1,
        'topic': '',
        'payload': '1',
        'payloadType': 'num',
        'x': g['x'],
        'y': g['y'],
        'wires': g['wires'],
    }
    changes.append(f"rpi-gpio in '{g.get('name')}' (pin {g.get('pin')}) -> inject num 1")

json.dump(flows, open(PATH, 'w', encoding='utf-8'), indent=4, ensure_ascii=False)
print('flows.json parcheado:')
for c in changes:
    print('  -', c)
