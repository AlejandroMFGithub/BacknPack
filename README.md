# 🎒 Back&Pack

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
- **Personajes ocultos**: el jugador puede ocultar sus personajes al resto de jugadores (botón del ojo en
  «Mis personajes» o menú ⋯ de la ficha) y el DM puede ocultar o mostrar cualquiera (ojo en el panel).
  Un personaje oculto no aparece en el buscador de los demás jugadores y no pueden proponerle
  intercambios (su URL da 404). Si lo oculta el DM, el jugador no puede volver a mostrarlo. El DM y el
  propio dueño lo siguen viendo siempre. Los intercambios que ya existían no se ven afectados.

**DM**
- Panel con todo el grupo, efectos activos y actividad reciente.
- Ve y edita cualquier ficha; da y retira objetos; ajusta la bolsa.
- **Visibilidad**: objetos y efectos pueden estar ocultos al jugador (p. ej. un objeto maldito sin identificar).
- Bufos, maldiciones y estados con duración y descripción. El DM los crea, edita, activa/desactiva,
  oculta y **fija** (🔒: el jugador los ve pero no puede desactivarlos, editarlos ni quitarlos).
- Catálogo de objetos y divisas propias (con valor en pc o no convertibles).
- Tiendas: abrir/cerrar, stock limitado o infinito, permitir o no pagar con otras divisas.
- Botines (tras combate o de entorno), que se pueden revelar u ocultar.
- **Cualidades de objetos**: propiedades, bendiciones, maldiciones y usos limitados (con recarga),
  visibles u ocultas. Se definen en la plantilla del catálogo (se copian a cada ejemplar nuevo) o
  en un ejemplar concreto desde la ficha. Viajan con el objeto al intercambiarlo, ocultas incluidas.
  Los objetos solo se apilan si tienen las mismas cualidades y ninguna tiene usos.

**Avisos de intercambios**
- Campana 🔔 en la barra con el número de propuestas que ha recibido el personaje con el que
  juegas; su panel permite aceptar, rechazar o cancelar sin salir de la página.
- Aviso emergente la primera vez que llega una propuesta (queda marcada como vista en la base de
  datos). La página consulta `/notifications/state` cada 30 s, solo con la pestaña visible, así
  que el aviso llega sin recargar.
- Contadores en «Intercambios» (el DM ve los pendientes de su campaña) y en «¿Con quién juegas?».

**Ficha de 5e**
- **Puntos de golpe en combate**: PG actuales y **temporales** con botones − / + que guardan al momento sin
  recargar la página, y una cantidad (1, 5, 10 o la que escribas). El − de los PG actuales es daño: gasta antes
  los temporales (como en el reglamento). Curar no pasa del máximo (con efectos incluidos). La barra de vida
  muestra los temporales en azul. También se editan en «Editar ficha» y se ven en las listas («20/34 +7»).
- Iniciativa (modificador de DES + bonus extra opcional), bonificador de competencia (automático
  según el nivel o fijado a mano), percepción pasiva y puntos de inspiración (el DM los da,
  el jugador los gasta).
- Tiradas de salvación y las 18 habilidades con su total calculado: modificador + competencia
  (● competencia, ◉ pericia = el doble). Ej.: DES 20, competencia +2 y Acrobacias → +7.
  Las reglas están en `app/models/rules.py` (funciones puras).

**Catálogo del SRD 5.1** (todo lo que se puede usar legalmente de los manuales oficiales)
- **319 conjuros** y **611 objetos**: todas las armas, armaduras, equipo de aventurero, herramientas, monturas y
  vehículos, y los objetos mágicos (con sus variantes: armaduras +1/+2/+3 de cada tipo, cinturones de fuerza
  de gigante, pociones de curación y de resistencia, piedras Ioun, pergaminos de conjuro…).
- Nombres en castellano y **resúmenes propios** (no el texto del manual). Daño y propiedades de las armas,
  CA de las armaduras, peso (kg) y **precio de referencia** salen de los datos del SRD.
- **Efectos en la ficha** al equiparlos: armaduras y escudos (CA), armaduras mágicas, anillo y capa de
  protección, cinturones de fuerza de gigante, amuleto de salud, cinta de intelecto, guanteletes de fuerza de
  ogro, brazales de defensa, piedras Ioun, túnica del archimago, bastón de poder, varitas del mago de guerra…
  Las varitas, bastones y otros objetos **conceden sus conjuros** (aparecen en la pestaña de conjuros).
- Al actualizar una base de datos existente no se duplica nada: lo que ya existía con el mismo nombre solo se
  completa (efectos, precio) sin tocar lo que el DM haya cambiado.
- Lo que no está en el SRD (la mayoría de subclases y conjuros del *Player's Handbook*, objetos del *Xanathar*…)
  tiene copyright y no se incluye: el DM puede añadirlo como homebrew.
- Para regenerar los datos tras cambiar las traducciones: `tools/build_srd.py` (instrucciones dentro).

> Este trabajo incluye material del *System Reference Document 5.1* («SRD 5.1») de Wizards of the Coast LLC,
> disponible en https://dnd.wizards.com/resources/systems-reference-document, con licencia Creative Commons
> Attribution 4.0 International (https://creativecommons.org/licenses/by/4.0/legalcode). Datos estructurados
> de [5e-bits/5e-database](https://github.com/5e-bits/5e-database) (MIT).

**Clases y conjuros**
- Las 13 clases oficiales (con el artífice) y sus subclases vienen cargadas, con dado de golpe, salvaciones,
  tipo de lanzador, característica mágica y forma de preparar conjuros. También un catálogo inicial de
  ~70 conjuros (resumen propio de cada uno; `app/models/spell_data.py`).
- Al elegir clase y subclase en la ficha se rellenan sus **valores por defecto** (salvaciones, dado de golpe,
  PG al crear, magia), que el jugador y el DM pueden cambiar a mano: lo guardado es lo que cuenta.
  Subclases que añaden magia (caballero arcano, embaucador arcano) cambian el tipo de lanzador.
  Se puede elegir una clase/subclase **personalizada** escribiendo su nombre.
- El DM crea clases y subclases **homebrew** (*Herramientas → Clases*) y conjuros homebrew
  (*Herramientas → Conjuros*), y puede ajustar los oficiales. Un objeto del catálogo puede **conceder
  conjuros** mientras se lleva equipado.
- **Pestaña de conjuros** (si su clase lanza conjuros, tiene alguno apuntado o un objeto equipado se los da):
  característica mágica, CD de salvación y ataque de conjuro (con desglose y modificables por efectos),
  conjuros conocidos o preparados frente a su máximo, trucos, **espacios de conjuro** por nivel (tablas de
  lanzador completo, medio, tercio y pacto) que se gastan al lanzar o pulsando, descanso largo y corto,
  espacios ajustables a mano, conjuros por nivel con preparar / siempre preparado, lanzar a nivel superior
  y como ritual, y los conjuros de objetos equipados. Cada lanzamiento queda en el historial.
- Al actualizar, los personajes que ya existían reciben su clase por el nombre escrito («Exploradora» →
  Explorador) con sus valores por defecto; sus salvaciones no cambian.

**Estadísticas automáticas** (equipo, bufos, maldiciones y estados)
- Objetos del catálogo, cualidades de objetos y efectos del personaje pueden llevar **efectos en la
  ficha**: sobre una característica, la CA, la velocidad, la iniciativa, los PG máximos, la
  percepción pasiva, una o todas las salvaciones y una o todas las habilidades.
- Operaciones: `+/−` (escudo: CA +2), `armadura` (la CA pasa a ser valor + DES, con o sin límite:
  cuero 11 + DES, cota de malla 16 sin DES), `mínimo` (guanteletes de ogro: FUE 19), `×` (velocidad
  ×0,5) y `=` (agarrado: velocidad 0). Se aplican en ese orden: armadura, mínimo, +/−, ×, =.
- Los objetos y sus cualidades cuentan **solo si están equipados**; los efectos del personaje, siempre.
  Al añadir un estado del reglamento sin efectos (Agarrado, Prisa, Ralentizar, Paso largo…) se pone el suyo.
- La CA de la ficha es la CA **sin armadura** (10 + DES o armadura natural); con varias armaduras
  equipadas cuenta la mejor.
- Los cambios se propagan: subir DES cambia CA, iniciativa, salvación y habilidades de DES; FUE cambia
  la carga máxima.
- En la ficha: **verde** si equipo/efectos lo mejoran, **rojo** si lo empeoran, **ámbar** si hay de
  ambos. Al pasar el ratón, enfocar con el teclado o tocar cualquier valor se ve la operación paso a
  paso con el origen de cada cambio. Un efecto oculto se aplica igual, pero el jugador ve «???» como
  origen; el DM ve su nombre. Lo que viene del nivel o de lo escrito en la ficha no colorea.
- El motor está en `rules.sheet()` y los efectos en `app/models/effects.py` (JSON en la columna `effects`).

**Ataques e inventario por pestañas**
- Tarjeta **⚔ Ataques** en la ficha (como la CD de conjuros para un lanzador): cada arma equipada y el golpe sin
  armas con su **bonificador de ataque** y su **daño** calculados, alcance y propiedades, con el desglose al
  pulsar. FUE cuerpo a cuerpo, DES a distancia, la mejor de las dos con armas sutiles; + competencia; + el
  bonificador de las armas mágicas; + los efectos «Ataques con arma» y «Daño con arma» (estilos de combate,
  bendiciones…). Las armas versátiles muestran también el daño a dos manos.
- **Competencia automática** según las competencias de su clase (armas sencillas/marciales, armas de druida o
  armas concretas como la espada larga del bardo). Se puede fijar a mano por arma desde su menú ⋯ del inventario.
- Las armas del catálogo guardan sus datos de ataque (dado, tipo, sencilla/marcial, propiedades, alcance,
  bonificador mágico); el DM los edita en el bloque «Es un arma» del catálogo.
- El **inventario** se separa en pestañas: Armas (con su línea de ataque), Armaduras, Consumibles, Mágicos,
  Equipo y Otros, con el número de objetos de cada una; la página recuerda la última pestaña elegida.

**Secciones plegables**
- En la ficha (Tiradas, Bolsa, Efectos, Inventario, Historial), en la pestaña de conjuros (cada nivel, los de
  objetos y «Añadir conjuro») y en la actividad del panel del DM, cada sección se pliega con su flecha. La
  cabecera plegada sigue mostrando un resumen (p. ej. «6 conjuros · 4 preparados · 2/3 espacios»).
- El navegador recuerda qué secciones has plegado; «Desplegar todo / Plegar todo» en la de conjuros. Un enlace
  que apunta a una sección plegada la abre (p. ej. tras lanzar un conjuro).

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
- Crea sus propios efectos (furia, concentración, un conjuro…) con sus modificadores, y los
  **activa y desactiva** con un interruptor en la ficha: solo los activos cambian las estadísticas
  y cada cambio queda en el historial. Puede editar o quitar cualquier efecto que vea y no sea fijo.
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
