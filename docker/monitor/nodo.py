#!/usr/bin/env python3
"""Lanzador del nodo de monitorizacion dentro del compose de RoomFID.

Equivale a monitor/node/demo/run_demo.py pero para uso real en la instalacion:
configuracion por fichero, escucha en todas las interfaces y sin envio a la central
(no hay central en este despliegue). Las claves se generan al arrancar: al no enviar
nada, no hace falta que persistan.
"""
from __future__ import annotations

import argparse
import logging
import os
import threading
import time
from pathlib import Path

import uvicorn

from roomfid_common.crypto import generate_signing_key
from roomfid_node.app import create_app
from roomfid_node.config import NodeConfig
from roomfid_node.inbox import Buzon
from roomfid_node.runner import NodeRunner
from roomfid_node.spool import Spool
from roomfid_node.state import NodeState


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="/etc/roomfid/node.yaml")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    config = NodeConfig.load(a.config)
    spool = Spool(Path(os.environ.get("ROOMFID_SPOOL", "/data/spool.sqlite")))
    state = NodeState(config.installation_id, config.name, config.timezone,
                      config.interval_s, config.node_version)
    # Informes de los agentes de la instalacion (un contenedor por maquina).
    buzon = Buzon()
    runner = NodeRunner(config, spool, state, master_secret=os.urandom(32),
                        signing_key=generate_signing_key(), buzon=buzon)

    def bucle() -> None:
        while True:
            try:
                runner.tick()
            except Exception:
                logging.exception("fallo en el ciclo de medida")
            time.sleep(config.interval_s)

    threading.Thread(target=bucle, daemon=True).start()
    web = config.web_root or Path("/app/ui/out")
    uvicorn.run(create_app(state, web_root=web, buzon=buzon, agentes=config.agentes_remotos(),
                           token=config.agentes_token),
                host="0.0.0.0", port=config.listen_port, log_level="warning")


if __name__ == "__main__":
    main()
