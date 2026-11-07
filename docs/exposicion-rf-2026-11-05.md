# ¿Es perjudicial la potencia de RF que usamos? Revisión

> 5/11/2026. Revisión a petición del cliente. Calculada sobre la configuración **documentada
> y verificada** de la instalación, con los límites de ICNIRP 2020, la Recomendación
> 1999/519/CE y la Directiva 2013/35/UE. **No sustituye a la evaluación de riesgos que la
> Directiva obliga al empleador a hacer, ni a la declaración de conformidad de Keonn.** Al
> final se dice exactamente qué falta para cerrarla.

## Respuesta corta

**No, no hay riesgo de exposición para las personas.** A más de **30 cm** de la cara de una
antena ya se está por debajo del límite para **público general**, que es el más estricto, y
eso sin contar el ciclo de trabajo; contándolo son **10-15 cm**. Nadie trabaja con el torso
pegado a una antena de estantería.

**Pero la revisión ha encontrado dos cosas que sí hay que atender**, y ninguna es el
calentamiento de tejidos:

1. **Posible incumplimiento del límite legal de emisión** (ETSI EN 302 208): estamos entre
   2,4 y 3,0 W ERP frente a un techo de **2 W ERP**. Es un problema de certificación, no de
   salud. **Es el punto a escalar.**
2. **Implantes activos** (marcapasos, DAI). Es el riesgo real en un hospital, ocurre a
   potencias muy inferiores a las que calientan tejido, y se gestiona con **distancia de
   separación**, no con potencia.

## Lo que usamos de verdad

| | Valor | Fuente |
|---|---|---|
| Banda | 865,6-867,6 MHz (λ = 34,6 cm) | `estudio-cobertura`, config del simulador |
| Potencia conducida, lectores de inventario | **31,5 dBm = 1,41 W** (su máximo) | `lectores-mqtt.md:45`, confirmado el 1/11 |
| Antena | **Advantenna-p12**, 5,4 dBiC, haz 60°×90° | `ARQUITECTURA.md:264` |
| Antenas que irradian | **`.157`: 4 · `.158`: 2** | medido: `traza.lector_antena` |
| Ciclo de trabajo del lector | 90 s de cada 193 s = **46,6 %** | medido |
| Lector de puerta | potencia **15** | `lector-puerta.md:135` |
| Lector de papelera | **16 dBm** | `CLAUDE.md` |

**Las antenas 3 y 4 del `.158` no irradian**: 0 lecturas y 154 ventanas mudas. O están
deshabilitadas o no están conectadas. Conviene confirmarlo —un puerto activo contra un cable
sin terminar es mala práctica— y además es un asunto de cobertura.

**Dato que tranquiliza:** los dos lectores junto a los que una persona **sí** se pone —el de
la puerta, por el que se pasa, y el de la papelera— son los más débiles, **unos 15 dB por
debajo** (≈30 veces menos potencia) que los de estantería, que apuntan a los estantes.

### Potencia radiada

```
EIRP = 31,5 dBm − perdida_cable + 5,4 dBiC
ERP  = EIRP − 2,15 dB

sin perdida de cable:   EIRP 36,9 dBm = 4,90 W   ->  ERP 34,75 dBm = 2,98 W
con 1 dB de cable:      EIRP 35,9 dBm = 3,89 W   ->  ERP 33,75 dBm = 2,37 W
```

Todo lo que sigue usa el **peor caso, 4,90 W EIRP**.

## 1 · Exposición de personas: no hay problema, y por cuánto

Niveles de referencia a 866 MHz (densidad de potencia, promediada en 30 min, cuerpo completo):

```
publico general   S = f/200 =  4,33 W/m²     (E = 40,5 V/m)
profesional       S = f/40  = 21,7  W/m²     (E = 88,3 V/m)
```

Con `S = EIRP / 4πr²`, la distancia a la que se baja de cada límite:

| | Público general | Profesional |
|---|---|---|
| **Mientras esa antena transmite** | **30 cm** | 13 cm |
| Promediado 30 min · `.157` (4 antenas, 11,7 %) | **10 cm** | 5 cm |
| Promediado 30 min · `.158` (2 antenas, 23,3 %) | **15 cm** | 7 cm |

El lector **multiplexa**: sólo una antena irradia a la vez, así que cada antena transmite una
fracción del 46,6 %. Aun suponiendo que irradiaran todas a la vez, el límite de público
general se cumpliría a **21 cm**. **La conclusión no depende de ese supuesto.**

> Por debajo de ~15 cm se está en el campo cercano de un parche de este tamaño y la fórmula de
> espacio libre no vale. Por eso la respuesta de ingeniería no es un número fino, es una
> **distancia de respeto de 30 cm**, que cubre el caso peor con margen.

**En resumen: para la exposición de personas, esta instalación está holgadamente dentro de
los límites.** Y nótese que los límites de público general ya incluyen un factor 50 de
seguridad sobre el umbral de efecto térmico.

## 2 · El hallazgo que sí hay que atender: el límite legal de emisión

**ETSI EN 302 208** fija para 865,6-867,6 MHz un máximo de **2 W ERP (33 dBm)**. Las cifras
documentadas dan **2,37-2,98 W ERP**, es decir **0,8 a 1,8 dB por encima**.

**No es un riesgo para la salud** —está 10 veces por debajo de donde empezaría a serlo— pero
sí es un asunto de conformidad CE y de responsabilidad del producto, y en un hospital eso
pesa.

**Antes de dar nada por incumplido hay que comprobar dos cosas**, y no se pueden comprobar
desde aquí:

- **El perfil de región del lector.** Si el firmware está en modo ETSI, puede estar limitando
  el ERP él mismo contando una ganancia de antena declarada. En ese caso «31,5 dBm» no
  significa lo que parece y no hay nada que corregir.
- **La declaración de conformidad de Keonn** para la combinación AdvanReader-m4 +
  Advantenna-p12: dice qué pares potencia/antena están certificados. **Ese documento, y no
  este cálculo, es la respuesta legal.**

### Si hay que bajar la potencia, a cuánto

```
potencia_conducida_max = 33 + 2,15 − 5,4 + perdida_cable = 29,8 + perdida_cable  dBm
```

Es decir **29,5-30,5 dBm** en vez de 31,5: una bajada de **1 a 2 dB**.

**Y cuesta cobertura, que es la restricción que manda en este sistema.** El enlace lo limita
la sensibilidad de la etiqueta (−24 dBm), así que el alcance va como `√P`: 1,8 dB menos son
**~18 % de alcance**. Sobre una cobertura que hoy está en el 99,73 % y con 31 etiquetas
crónicas al límite de sensibilidad, eso se va a notar.

**Por eso la vía correcta no es la potencia, es la posición de las antenas** —el trabajo de
`etiquetas-a-recolocar-2026-11-03.md`—. El estudio de cobertura ya concluyó que **la potencia
no es una palanca porque ya estamos en el máximo**; lo que esta revisión añade es que
probablemente estamos **por encima** del máximo legal, así que recolocar deja de ser una
mejora y pasa a ser **la forma de poder cumplir sin perder cobertura**.

## 3 · El riesgo real en un hospital: implantes activos

Un marcapasos o un DAI puede verse perturbado por RFID UHF **muy por debajo** de las
potencias que calientan tejido: el mecanismo es interferencia electromagnética, no absorción.
Está documentado en la literatura y es la razón de que las instalaciones de RFID en hospitales
trabajen con distancias de separación.

Campo eléctrico de nuestras antenas, `E = √(30·EIRP)/r = 12,1/r`:

| Distancia | Campo |
|---|---|
| 30 cm | 40 V/m |
| 1 m | 12 V/m |
| 2 m | 6 V/m |
| **4 m** | **3 V/m** |

**Lo que hay que aplicar:**

- **30 cm mínimo** entre cualquier antena y una persona con implante cardiaco. Es la distancia
  que coincide con el límite de público general, lo cual simplifica: **una sola regla de 30 cm
  cubre las dos cosas.**
- **Señalización** en la sala advirtiendo de RFID activo, que es lo que permite a una persona
  con implante tomar sus precauciones. Sin señal, la medida no existe.
- **Equipos médicos a menos de ~4 m**: la inmunidad general que exige IEC 60601-1-2 es
  **3 V/m**, y nuestro campo la supera hasta los 4 m (y los 10 V/m de los equipos de soporte
  vital, hasta 1,2 m). En un almacén sin pacientes ni equipos de soporte vital no aplica,
  **pero hay que mirar qué hay al otro lado de las paredes**: un tabique de pladur no atenúa
  casi nada a 866 MHz.

## 4 · Mitigaciones, y dos que ya están puestas sin pretenderlo

**Ya funcionando:**

1. **El enclavamiento por acceso ya existe.** `IRFID_ORQ_ABORTAR_POR_ACCESO` está en `true`
   (por defecto, y no se sobreescribe en la sala): cuando alguien pasa el carnet por la
   puerta, **se corta la ventana de lectura en curso**. Se hizo por calidad del dato —una
   persona dentro tapa antenas— pero es, gratis, **la mejor mitigación posible: los lectores
   dejan de transmitir cuando entra una persona.**

   **Con una salvedad importante:** depende del lector de puerta, que hoy está **a medias**
   (`lector-puerta.md`). Si no registra accesos, el enclavamiento no dispara. **Terminar de
   configurarlo deja de ser sólo trazabilidad y pasa a ser una medida de seguridad.**

2. **El ciclo de trabajo y la multiplexación** ya dividen la exposición promediada entre 4 y 8.

**Por hacer, en orden de coste:**

3. **Señalización** y una distancia de respeto de **30 cm** marcada físicamente (borde de
   estante, canaleta, etiqueta). Coste casi nulo.
4. **Orientar el haz** de 60°×90° a los estantes y nunca a pasillos, sillas o puestos de
   trabajo. Revisar las seis antenas con ese criterio.
5. **Confirmar el perfil de región y la declaración de conformidad de Keonn.** Esto es lo que
   decide si hay algo que corregir en potencia.
6. **Aclarar las antenas 3 y 4 del `.158`**: deshabilitadas está bien; conectadas a un cable
   sin terminar, no.
7. **Si procede, bajar a 29,5-30,5 dBm**, y compensar la pérdida de alcance **recolocando**,
   no subiendo potencia.

## Qué falta para cerrar esto formalmente

Esta revisión es un **cálculo de ingeniería sobre valores documentados**. Para una respuesta
que se pueda entregar a un cliente sanitario hacen falta tres cosas que no están aquí:

- **La declaración de conformidad de Keonn** para este par lector/antena, y el ajuste de
  región del lector leído de su propia interfaz.
- **Una medida de campo con sonda calibrada** en los puntos donde hay personas. Es lo único
  que sustituye a la fórmula de espacio libre en el campo cercano, y lo único que vale si
  alguien pregunta por escrito.
- **La evaluación de riesgos por campos electromagnéticos** que la **Directiva 2013/35/UE**
  obliga a hacer al empleador, con atención específica a trabajadores con implantes activos y
  a trabajadoras embarazadas. **Es obligación del hospital, no nuestra**, pero necesita de
  nosotros las cifras de arriba.
