#!/bin/bash
# Lanza los 7 procesos batch (equivale al exec ssh del Node-RED original).
exec docker exec rfid-nodered curl -s --max-time 130 http://192.168.1.163:8081/run
