"""Configuracion del servicio, leida de variables de entorno o de un fichero .env."""
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="IRFID_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- MQTT ---------------------------------------------------------------
    mqtt_host: str = "127.0.0.1"
    mqtt_port: int = 1883
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    # Estable a proposito: identifica la sesion persistente ante el broker.
    mqtt_client_id: str = "irfid-ingesta"
    # Con sesion persistente el broker guarda los mensajes QoS 1 mientras el servicio
    # esta caido (no se pierden lecturas). En una prueba en sombra contra un broker de
    # produccion conviene desactivarla: al desconectar no queda nada encolado alli.
    mqtt_sesion_persistente: bool = True
    mqtt_topic: str = "TAG_readings/#"
    # Eventos de ventana del orquestador: RFID_control/<devid>
    mqtt_control_topic: str = "RFID_control"

    # --- PostgreSQL -----------------------------------------------------------
    # El servicio fuerza timezone=UTC en sus sesiones (ver db.connect); no hace falta
    # ponerlo aqui.
    pg_dsn: str = "host=localhost dbname=gestion_rfid"

    # --- Ingesta ----------------------------------------------------------------
    window_seconds: float = Field(default=5.0, gt=0)
    spool_path: str = "./irfid-spool.sqlite3"
    spool_max_rows: int = Field(default=500_000, gt=0)
    batch_size: int = Field(default=500, gt=0)
    flush_seconds: float = Field(default=2.0, gt=0)

    # --- Ventanas y ciclos de inventario -----------------------------------------
    # Sin tramas de un lector durante este tiempo, su ventana se da por cerrada.
    ventana_gap_s: float = Field(default=20.0, gt=0)
    # Ventana abierta por un "start" del orquestador: se espera su "stop". Si no llega
    # (orquestador caido), se cierra por inactividad pasado este tiempo.
    ventana_timeout_evento_s: float = Field(default=600.0, gt=0)
    # Una ventana mas corta no cuenta (aborto por puerta, corte de RF...).
    ventana_min_s: float = Field(default=30.0, ge=0)
    # Fraccion minima del stock vista en un ciclo para darlo por bueno. Por debajo se
    # asume fallo de lectura y NO se marca nada como temporal.
    cobertura_minima: float = Field(default=0.5, ge=0, le=1)
    # Con menos stock que esto no se aplica el criterio de cobertura.
    cobertura_stock_minimo: int = Field(default=10, ge=0)

    # --- Reglas de estado ---------------------------------------------------------
    # Un temporal pasa a circulante tras N ciclos sin leerse o T minutos, lo que antes ocurra.
    ciclos_para_circulante: int = Field(default=3, gt=0)
    minutos_para_circulante: float = Field(default=30.0, gt=0)
    # Minutos que una devolucion manual del visor protege a la etiqueta de volver a salir.
    # **Por encima de la sombra medida** -21 min el 26/10 en etiquetas que estaban en la
    # estanteria-: por debajo, la gracia expiraria antes de que la antena hubiera tenido
    # oportunidad de verla y no serviria de nada. A 0 se desactiva y la devolucion vuelve a
    # comportarse como antes.
    gracia_devolucion_min: float = Field(default=30.0, ge=0)
    # Registro de accesos: lecturas repetidas de un carnet en la misma puerta dentro de
    # este intervalo son el mismo acceso.
    acceso_dedup_s: float = Field(default=60.0, ge=0)

    # --- Salud de lectores y antenas (GET /estado, lo consume el monitor) --------------
    # Ventanas validas seguidas sin una sola lectura en una antena -> antena en fallo.
    antena_ventanas_fallo: int = Field(default=3, ge=1)
    # Un lector de inventario que no publica en este tiempo esta mal (con ciclos de 300 s,
    # tres ciclos). Los de puerta y papelera solo leen cuando pasa algo: no se juzgan.
    estado_lector_silencio_s: float = Field(default=900.0, gt=0)
    # Sin un ciclo valido en este tiempo, el almacen no esta inventariando.
    estado_ciclo_max_s: float = Field(default=1800.0, gt=0)
    antenas_volcado_s: float = Field(default=60.0, gt=0)

    # --- Alertas y correo -----------------------------------------------------------
    horas_alerta_temporal: float = Field(default=24.0, gt=0)
    alertas_intervalo_s: float = Field(default=300.0, gt=0)
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_starttls: bool = True
    smtp_from: str = "roomfid@localhost"
    # Zona horaria en la que se muestran las fechas en los correos.
    tz_presentacion: str = "Europe/Madrid"

    # --- Espejo en las tablas legacy -------------------------------------------------
    legacy_mirror: bool = False
    # Zona de las columnas "timestamp" / texto legacy (Local_time, Time_User, start_time).
    legacy_tz: str = "Europe/Madrid"
    # El batch original borraba de EPC_master todo lo consumido. Desactivado por defecto:
    # erosiona el catalogo y ya no hace falta.
    legacy_borrar_master: bool = False

    # --- API de papeleras (terminales papelerIA) -------------------------------------
    # Puerto propio: el 8090 es la salud, que no lee cuerpos de peticion.
    papelera_port: int = Field(default=8091, ge=0)   # 0 = sin API de papeleras
    # API de lectura del inventario, la que consume el visor. 0 la desactiva.
    # Puerto propio y no el de /estado porque ese servidor esta hecho a mano y no
    # admite query params, asi que no puede filtrar ni paginar una tabla.
    inventario_port: int = Field(default=8093, ge=0)
    # Se envia al terminal en GET /contexto: formato de la pulsera del paciente.
    papelera_paciente_regex: str = r"^[A-Za-z0-9\-]{4,50}$"
    # Aviso en la pantalla de la papelera si una sesion lleva demasiado abierta.
    papelera_aviso_sesion_min: int = Field(default=120, gt=0)
    # Tolerancia de reloj de la firma HMAC. Debe coincidir con VENTANA_S del terminal.
    papelera_ventana_firma_s: int = Field(default=300, gt=0)

    # --- Emisor hacia la plataforma de gestion --------------------------------------
    # Al cerrar un ciclo se le manda la lista de EPC vistos, y ella marca "en transito"
    # lo que tenia en stock y no aparece. Apagado por defecto: encenderlo hace que la
    # gestion empiece a mover estados y a crear movimientos de salida, y deshacerlo
    # alli es manual.
    gestion_activo: bool = False
    gestion_url: str | None = None          # raiz del servicio, sin la ruta
    gestion_token: str | None = None        # el token del almacen en la gestion
    # Respaldo si la ubicacion no trae gestion_store_id en base (instalacion de un solo
    # almacen). Lo normal es cargarlo desde topologia.json.
    gestion_store_id: str | None = None
    # El receptor procesa en la misma peticion: cientos de faltantes son cientos de
    # inserciones antes de responder. Generoso a proposito.
    gestion_timeout_s: float = Field(default=60.0, gt=0)
    gestion_intervalo_s: float = Field(default=60.0, gt=0)
    # Fraccion del stock que hay que haber visto para reportar el ciclo. Muy por encima
    # de cobertura_minima, y la asimetria es deliberada: un ciclo flojo aqui solo deja de
    # marcar temporales y el siguiente lo corrige, pero enviado a la gestion crea
    # movimientos de salida y asigna usuarios. El coste de equivocarse no es simetrico.
    gestion_cobertura_minima: float = Field(default=0.9, ge=0, le=1)
    # Tope de salidas de golpe. La cobertura relativa es ciega al tamano del almacen:
    # en uno de mil cajas, un 10 por ciento son cien salidas simultaneas, que ya es
    # sospechoso. 0 lo desactiva.
    gestion_max_faltantes: int = Field(default=100, ge=0)
    # Lo enviado se conserva para poder auditar, pero no para siempre. 0 lo desactiva.
    gestion_dias_retencion: int = Field(default=90, ge=0)

    # --- Vinculacion y canal de bajada (enfoque C) ----------------------------------
    # Cada cuanto sondea `vincular` mientras espera que alguien apruebe al otro lado.
    # La gestion puede sobrescribirlo en su respuesta: que lo diga ella permite
    # alargarlo sin entrar en la Pi.
    vinculacion_intervalo_s: float = Field(default=30.0, gt=0)
    # Cada cuanto se manda el latido a la gestion. Mueve su `last_ping`, que es lo que
    # pinta su pantalla, y detecta una revocacion. Cinco minutos sobran: no es un canal
    # de datos, y mas a menudo solo seria ruido en su registro.
    latido_intervalo_s: float = Field(default=300.0, gt=0)
    # Cuanto se retrocede el cursor de bajada en cada peticion. NO ponerlo a 0: la
    # sync_version de la gestion se asigna al ejecutar y no al confirmar, asi que dos
    # transacciones pueden hacerse visibles en orden distinto al de su version. Releer
    # de mas no cuesta nada porque aplicar es idempotente; perderse una fila es
    # silencioso y no se recupera hasta la siguiente sincronizacion completa.
    gestion_solape: int = Field(default=100, ge=1)

    # --- Salud ---------------------------------------------------------------------
    health_port: int = Field(default=8090, ge=0)  # 0 = sin endpoint

    # --- Orquestador -------------------------------------------------------------------
    orq_ventana_s: float = Field(default=120.0, gt=0)
    orq_pausa_s: float = Field(default=5.0, ge=0)
    orq_periodo_s: float = Field(default=300.0, gt=0)
    # Los lectores de un almacen leen a la vez. En serie, sus ventanas se suman:
    # con dos de 120 s una vuelta costaba 245 s en vez de 120. False vuelve al
    # comportamiento de Node-RED.
    orq_paralelo: bool = True
    # Cierra la ventana cuando el almacen ya esta leido: segundos sin ver un EPC
    # nuevo que se toman por "no queda nada". 0 = esperar siempre la ventana
    # entera. Requiere que la ingesta publique el recuento por lector.
    # 25 s: medido en el banco, el almacen se lee entero en 34 s y una etiqueta
    # se vuelve a reportar cada ~23 s (el TTL del lector). Por debajo de eso se
    # cerraria en falso; 25 deja margen sin regalar tiempo. 0 lo desactiva.
    orq_sin_nuevos_s: float = Field(default=25.0, ge=0)
    # Suelo: por rapido que parezca, nunca cerrar antes de esto.
    orq_ventana_min_s: float = Field(default=30.0, ge=0)
    orq_http_timeout_s: float = Field(default=10.0, gt=0)
    orq_reintentos: int = Field(default=3, ge=1)
    orq_fallos_para_alerta: int = Field(default=3, ge=1)
    orq_digest_user: str = "admin"
    orq_digest_password: str = "admin"
    # Puerto HTTP de la API de los lectores (80 en los AdvanReader).
    orq_lector_puerto: int = 80
    orq_gpio: bool = False
    orq_gpio_pines_aborto: str = ""   # p. ej. "21,16"
    # Un carnet en la puerta corta la ventana de inventario en curso. Es el mismo aborto
    # que los pines GPIO de presencia, por el camino que si esta cableado hoy: el acceso
    # llega por MQTT al proceso de almacen y este lo avisa por NOTIFY (ver
    # orquestador/accesos.py y sql/021_notify_acceso.sql).
    #
    # Con alguien dentro, lo que se lee no describe la estanteria: tapa antenas, mueve
    # cajas y lleva etiquetas encima. Dar por ausente lo que no se vio en esa pasada es
    # como se fabrica una acusacion falsa, asi que el ciclo se descarta entero.
    #
    # Solo abortan los lectores con rol 'puerta': lo que dispara esto es una fila en
    # traza.acceso, y esa la escribe la ingesta por el devid del lector. La papelera vive
    # en otra Pi y manda sus sesiones por HTTP, asi que no puede abortar un ciclo.
    #
    # **Ponerlo a false si un lector que no es de puerta publica con identidad de
    # puerta.** Llego a pasar: el mismo aparato hizo de puerta y de papelera (ver
    # rep_server/docs/lector-puerta.md), y con esa identidad cada consumo abortaria un
    # ciclo y el inventario no se completaria nunca. Hoy son equipos distintos.
    orq_abortar_por_acceso: bool = True

    # --- Archivo y backup ------------------------------------------------------------------
    archivo_meses_online: int = Field(default=1, ge=0)
    archivo_dir_local: str = "./archivo"
    # usuario@maquina:/ruta  (rsync sobre SSH). Vacio = solo copia local.
    archivo_destino: str = ""
    archivo_ssh_key: str | None = None
    archivo_ssh_opciones: str = "-o StrictHostKeyChecking=accept-new -o BatchMode=yes"
    archivo_dumps_retener: int = Field(default=14, ge=1)
    archivo_hora_utc: str = "03:30"
    # Dias que tiene que llevar terminada una unidad (usado o retirado) para salir de
    # la tabla viva al historico. Decision del 26/10: configurable. 0 lo desactiva.
    #
    # Generoso a proposito: lo que se gana es espacio e indices mas cortos, y lo que
    # se pierde al apurar es tener a mano lo reciente, que es justo lo que alguien
    # mira cuando pregunta por una unidad.
    archivo_dias_elemento: int = Field(default=180, ge=0)

    log_level: str = "INFO"
