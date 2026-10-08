#!/bin/bash
# Acceso rapido a la base de datos de la replica.
exec docker exec -i rfid-postgres psql -U rfidroom -d gestion_rfid "$@"
