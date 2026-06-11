# Laboratorio de carga — datos estilo Tedial

Genera y carga datos sintéticos con la **misma estructura** que el índice
`content` real de Tedial (entidades `CONTAINER` / `LOCATOR` / `SUBCLIP` con
parent-child join), para hacer pruebas de rendimiento, diagnóstico y
optimización sobre un índice de pruebas con nombre controlado (`lab_content`).

> El mapping real se lee de `../datos/mapping_content.json` (fuera de git).
> Generado a partir del ejemplo de Tedial **sin el campo knn** (vectorial).

## Modelo de datos (lo importante)

- `CONTAINER` → `join_field: {name: "level_1"}` — la raíz (una media).
- `LOCATOR` → `join_field: {parent: <mediaid>, name: "level_2"}` — punto dentro
  del container (decenas/cientos por container). Documento **independiente**.
- `SUBCLIP` → es un `CONTAINER` con `join_field: {parent: <mediaid>, name: "subclip"}`.
- Locator de subclip → `join_field: {parent: <subclip_id>, name: "subclip_level_2"}`.

**Clave de rendimiento:** el join obliga a que toda la familia (raíz + locators
+ subclips + sus locators) viva en el **mismo shard**. Por eso **todos** los
documentos del árbol se indexan con `routing = MEDIAID del container raíz`.
Esto es el origen natural de los **hot shards** (una media con 500 locators
manda los 500 al mismo shard) → material ideal para el tema de routing/shards.

## Instalación (una vez)

```bash
cd carga
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

La conexión sale por defecto al cluster del curso. Para cambiarla, exporta
variables de entorno (ver `config.py`): `OS_URL`, `OS_USER`, `OS_PASS`,
`OS_INDEX`, `OS_SHARDS`, `OS_REPLICAS`.

## Uso

### 1. Crear el índice

```bash
python crear_indice.py                          # lab_content, 3 shards / 1 réplica
python crear_indice.py --recreate               # borra y recrea
python crear_indice.py --shards 1 --replicas 0  # mínimo, para línea base
python crear_indice.py --shards 4 --replicas 1  # replica su entorno real
```

Truco para carga masiva (más throughput): crear con `--replicas 0 --refresh-interval -1`,
cargar, y luego subir réplicas / restaurar refresh.

### 2. Cargar datos (un proceso, bulk multihilo)

```bash
python cargador.py --containers 1000
python cargador.py --containers 50000 --threads 8 --batch 1000 \
       --locators 10 50 --subclip-prob 0.4
```

Parámetros útiles: `--locators MIN MAX`, `--subclip-prob`, `--subclips MIN MAX`,
`--subclip-locators MIN MAX`, `--batch` (chunk_size), `--threads`, `--seed`.

Volumen aproximado: cada container genera 1 + `locators` (+ subclips y sus
locators). Con `--locators 5 30` salen ~15-20 docs por container de media.

### 3. Cargar en paralelo (varios procesos + bulk multihilo)

```bash
./lanzar_paralelo.sh <WORKERS> <CONTAINERS_POR_WORKER> [args extra]

./lanzar_paralelo.sh 4 5000
./lanzar_paralelo.sh 8 20000 --threads 4 --batch 1000 --locators 20 80
```

Cada worker usa un prefijo de MEDIAID distinto (`LAB0_`, `LAB1_`, …) para que
los `_id` no colisionen. Paralelismo en dos niveles (procesos × hilos) → sirve
para saturar el `write` thread pool y observar colas/rechazos.

## Qué mirar en el cluster mientras cargas

```bash
# Saturación de escritura (colas y rechazos)
GET /_cat/thread_pool/write?v
# Actividad de indexación y presión
GET /_nodes/stats/indices/indexing?pretty
GET /_nodes/stats?filter_path=nodes.*.indexing_pressure
# Hot shards (reparto desigual por el routing)
GET /_cat/shards/lab_content?v&s=docs:desc
# Segmentos y merges tras la carga
GET /_nodes/stats/indices/segments,merges?pretty
# Heap / GC (¡ojo, solo 2GB por nodo en este cluster!)
GET /_nodes/stats/jvm?pretty
```

## Búsquedas de ejemplo

Las búsquedas de `../datos/tedial.md` (has_child / has_parent / facetas /
simple_query_string) funcionan tal cual sobre `lab_content`, cambiando el
nombre del índice.
