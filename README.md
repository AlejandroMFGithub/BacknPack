# 🎒 BacknPack

Gestor web de personajes e inventario para D&D 5e. Flask, organizado en MVC.
SQLite en local y PostgreSQL (Neon) en producción (Render).

## Arrancar

```powershell
# primera vez
py -3.12 -m venv .venv            # o: & "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# cada vez
.\.venv\Scripts\python.exe run.py
```

Abre http://127.0.0.1:5000. La primera vez se crea `instance/backnpack.sqlite` con datos de ejemplo:

| Usuario | Contraseña | Rol |
|---|---|---|
| `dm` | `dm` | Dungeon Master |
| `ana` | `ana` | Jugadora (Lyra Vientoalto) |
| `bruno` | `bruno` | Jugador (Thorgar Puñohierro) |

Reiniciar la base de datos (¡borra todo!):

```powershell
.\.venv\Scripts\flask.exe --app run init-db            # con datos de ejemplo
.\.venv\Scripts\flask.exe --app run init-db --no-demo  # solo DM, divisas y catálogo
```

## Producción (Render + Neon)

- **Render** — Web Service con Build `pip install -r requirements.txt` y Start `gunicorn run:app`.
- **Neon** — base de datos PostgreSQL; su cadena de conexión va en `DATABASE_URL`.
- Cada `git push` a `main` vuelve a desplegar. Las migraciones se aplican solas al arrancar.

Variables de entorno (en Render → *Environment*):

| Variable | Obligatoria | Para qué |
|---|---|---|
| `DATABASE_URL` | sí | Cadena de conexión de Neon (con *connection pooling*) |
| `BACKNPACK_SECRET` | sí | Clave para firmar las sesiones (cadena larga aleatoria) |
| `DM_PASSWORD` | la 1.ª vez | Contraseña inicial del DM al crear la base de datos vacía |
| `INVITE_CODE` | no | Código para registrarse. Sin él, el registro está **cerrado** |
| `PYTHON_VERSION` | no | Ya fijada en `.python-version` |

En producción la base de datos se crea **sin** datos de ejemplo: solo el DM, las divisas y el
catálogo básico. Cada usuario puede cambiar su contraseña pulsando su nombre arriba a la derecha.

**Copiar los datos locales a Neon** (borra lo que haya en Neon):

```powershell
$env:DATABASE_URL = "postgresql://...neon.tech/neondb?sslmode=require"
$env:DM_PASSWORD = "nueva-contraseña-del-dm"     # opcional: la cambia en la copia
.\.venv\Scripts\flask.exe --app run copy-to-postgres --exclude-users ana,bruno
Remove-Item Env:DATABASE_URL, Env:DM_PASSWORD
```

Seguridad incluida: token CSRF en todos los formularios, cookies de sesión `Secure`/`HttpOnly`/
`SameSite=Lax` en producción y operaciones de dinero/objetos serializadas (nadie gasta dos veces
la misma moneda aunque pulsen a la vez).

## Estructura MVC

```
app/
├── models/        MODELO: acceso a datos y reglas de juego (compra, botín, intercambio…)
├── views/         VISTA: plantillas Jinja2
├── controllers/   CONTROLADOR: rutas Flask (blueprints) → llaman al modelo y eligen la vista
├── static/        CSS
├── schema.sql     esquema base de la base de datos (versión 0)
├── migrations.py  cambios de esquema posteriores (se aplican solos al arrancar)
├── seed.py        datos iniciales
├── security.py    protección CSRF
└── db.py          conexión (SQLite/PostgreSQL), transacciones y comandos de consola
```

**Cambiar el esquema:** añade una entrada al final de `MIGRATIONS` en `migrations.py`
(nunca edites las ya existentes). Al arrancar se aplican las pendientes sin borrar datos.

Regla: los controladores **no** escriben SQL; las operaciones compuestas (comprar, recoger,
aceptar un intercambio) viven en el modelo y se ejecutan dentro de `transaction()`, así que
o se hace todo o no se hace nada. Los errores de reglas se lanzan como `RuleError` y el
controlador los muestra como mensaje.

## Qué hace la v1

**Campañas** (mundos separados)
- Cada personaje, tienda y botín pertenece a una campaña. El catálogo de objetos y las
  divisas son comunes a todas.
- El jugador elige al entrar con qué personaje juega (si solo tiene uno, se elige solo) y solo
  ve las tiendas, botines e intercambios de esa campaña. Se comprueba en el servidor: lo de otra
  campaña devuelve 404, y comprar, recoger o comerciar entre campañas es imposible en el modelo.
- El DM trabaja en una campaña activa (selector en la barra superior; recuerda la última) y
  gestiona las campañas en *Herramientas → Campañas*: crear, editar, cerrar a personajes
  nuevos, archivar (bloquea a los jugadores) y eliminar (solo si no tiene personajes).
- Mover un personaje de campaña (editando su ficha, solo el DM) cancela sus intercambios pendientes.
- **Código de campaña**: cada campaña tiene uno (p. ej. `K7QX-M4TP`) que el DM ve y copia en el
  menú de campañas y puede regenerar si se filtra. Un jugador entra en una campaña con su código
  y solo puede crear personajes en las campañas en las que está (el creador de personaje muestra
  un selector con ellas). Una campaña «cerrada» no admite jugadores ni personajes nuevos.
  El `INVITE_CODE` general sigue sirviendo solo para registrarse en la web.
- Al actualizar, todo lo que ya existía pasa a una «Campaña principal».

**DM**
- Panel con todo el grupo, efectos activos y actividad reciente.
- Ve y edita cualquier ficha; da y retira objetos; ajusta la bolsa.
- **Visibilidad**: objetos y efectos pueden estar ocultos al jugador (p. ej. un objeto maldito sin identificar).
- Bufos, maldiciones y estados con duración y descripción.
- Catálogo de objetos y divisas propias (con valor en pc o no convertibles).
- Tiendas: abrir/cerrar, stock limitado o infinito, permitir o no pagar con otras divisas.
- Botines (tras combate o de entorno), que se pueden revelar u ocultar.
- **Cualidades de objetos**: propiedades, bendiciones, maldiciones y usos limitados (con recarga),
  visibles u ocultas. Se definen en la plantilla del catálogo (se copian a cada ejemplar nuevo) o
  en un ejemplar concreto desde la ficha. Viajan con el objeto al intercambiarlo, ocultas incluidas.
  Los objetos solo se apilan si tienen las mismas cualidades y ninguna tiene usos.

**Ficha de 5e**
- Iniciativa (modificador de DES + bonus extra opcional), bonificador de competencia (automático
  según el nivel o fijado a mano), percepción pasiva y puntos de inspiración (el DM los da,
  el jugador los gasta).
- Tiradas de salvación y las 18 habilidades con su total calculado: modificador + competencia
  (● competencia, ◉ pericia = el doble). Ej.: DES 20, competencia +2 y Acrobacias → +7.
  Las reglas están en `app/models/rules.py` (funciones puras).

**Imagen de personaje**
- Cada personaje muestra un icono en listas, ficha, intercambios y buscador: su imagen o, si no
  tiene, la inicial sobre un color fijo.
- El jugador dueño y el DM pueden cambiarla desde la ficha (pulsando el icono o soltando una
  imagen encima). JPG, PNG, WebP o GIF de hasta 8 MB.
- Se guarda en la base de datos (tabla `character_avatars`), recortada a 256×256 en WebP
  (~10–30 KB) y sin metadatos EXIF (que pueden incluir la ubicación GPS de la foto).

**Búsqueda y listas** (pensado para catálogos de miles de objetos)
- Buscador desplegable para elegir objetos, personajes y jugadores: consulta `/api/...` mientras
  escribes y trae 20 resultados cada vez, con filtros (categoría, rareza) y «Cargar más».
- Búsqueda por palabras, sin tildes ni mayúsculas: «cur pocion» encuentra «Poción de curación».
- Barra de lista con búsqueda, filtros y **«Ordenar por»** en inventarios, catálogo, personajes,
  tiendas, botines e intercambios; paginación de 50 en 50.
- En tiendas y botines se elige una vez el personaje que actúa («Comprar como» / «Recoger como»).

**Jugador**
- Crea y edita sus personajes; ve solo lo que el DM le deja ver.
- Equipa y tira objetos; gasta usos de sus objetos (cargas de una varita, una bendición diaria…).
- Compra en tiendas abiertas con cualquier divisa convertible (conversión por valor en pc, redondeo hacia arriba).
- Recoge botín (el primero que llega se lo lleva).
- Propone intercambios de objetos y dinero; el otro jugador acepta o rechaza.

## Ideas para siguientes versiones
- Gestión de usuarios para el DM (borrar cuentas, restablecer contraseñas).
- Campañas (varios DMs / grupos separados).
- Botín asignado a personajes concretos y reparto equitativo de monedas.
- Pago combinado con varias divisas y devolución de cambio.
- Peso con límite de carga y estado «sobrecargado» automático.
- Vender objetos a tiendas.
- Actualización en tiempo real (WebSockets) para intercambios y botín.
- Tests automatizados (pytest).
