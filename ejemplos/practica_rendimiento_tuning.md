# Práctica: líneas base, carga y tuning de rendimiento (terminal)

Cuaderno **reproducible desde terminal** (bash + curl) para la sesión de hoy.
Continúa el `analisis_avanzado_cluster.md` (que es para Dev Tools); este es la
parte de **medir → cargar/estresar → cambiar configuración → volver a medir**.

> Estado de partida (medido hoy): `lab_content` = **10.103.441 docs**
> (9.427.100 LOCATOR + 676.341 CONTAINER), 3 primarios / 1 réplica, ~12.4 GB,
> cluster 3 nodos (heap 4 GB, RAM limit 6 GB, **CPU limit 4 cores/nodo** — ver 4.0),
> OpenSearch 2.19.1.

---

## 0. Setup (pegar una vez en la terminal)

```bash
export OS_URL='https://opensearch.iochannel.tech'
export OS_AUTH='admin:Pa$$w0rd2026'
export OS_INDEX='lab_content'

# atajo curl
osq() { curl -s -k -u "$OS_AUTH" "$OS_URL$1" "${@:2}"; }

# medir 'took' de una query: warmup + N repeticiones -> min/med/p95/max
# uso: medir "nombre" '/indice/_search?filter_path=took' '{json...}' [runs]
medir() {
  local name="$1" path="$2" body="$3" runs="${4:-25}" warm=5
  for i in $(seq 1 $warm); do osq "$path" -H 'Content-Type: application/json' -d "$body" >/dev/null; done
  local t=()
  for i in $(seq 1 $runs); do
    t+=("$(osq "$path" -H 'Content-Type: application/json' -d "$body" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("took","NA"))')")
  done
  echo "${t[@]}" | python3 -c "import sys;v=sorted(float(x) for x in sys.stdin.read().split());n=len(v);print(f'  $name  min={v[0]:.0f} med={v[n//2]:.0f} p95={v[int(n*0.95)-1]:.0f} max={v[-1]:.0f} ms (n={n})')"
}
```

---

## 1. Foto del cluster (read-only)

```bash
osq "/_cluster/health?filter_path=status,number_of_nodes,active_shards,unassigned_shards"
osq "/_cat/nodes?v&h=name,master,heap.percent,ram.percent,cpu,disk.used_percent"
osq "/_cat/indices/$OS_INDEX?v&h=health,docs.count,docs.deleted,store.size,pri,rep,pri.store.size"
osq "/_cat/shards/$OS_INDEX?v&h=shard,prirep,docs,store,node&s=shard,prirep"
```

Recordatorio de interpretación (dia5): `ram.percent` al 95-100% **es bueno**
(es el filesystem cache de Lucene lleno). El `heap.percent` NO se lee aislado:
sube con la "basura" entre GC; el mínimo en reposo es lo realmente cacheado.

---

## 2. Líneas base sobre 10.1M

```bash
echo "=== LINEAS BASE (took ms) ==="
medir "Q1 term->1 (MEDIAID)        " "/$OS_INDEX/_search?filter_path=took" '{"size":1,"query":{"bool":{"filter":[{"term":{"doc_type.keyword":"CONTAINER"}},{"term":{"EDITORIAL--CONTAINER.MEDIAID.keyword":"BIG_0_00000001"}}]}}}'
medir "Q2 term->muchos (size0)     " "/$OS_INDEX/_search?filter_path=took" '{"size":0,"query":{"term":{"doc_type.keyword":"LOCATOR"}}}'
medir "Q3 join has_child           " "/$OS_INDEX/_search?filter_path=took" '{"size":0,"query":{"has_child":{"type":"level_2","query":{"term":{"doc_type.keyword":"LOCATOR"}}}}}'
medir "Q4 agg terms TYPEID (size0) " "/$OS_INDEX/_search?filter_path=took" '{"size":0,"query":{"term":{"doc_type.keyword":"LOCATOR"}},"aggs":{"t":{"terms":{"field":"STRATA--LOCATOR.TYPEID.keyword","size":100}}}}'
medir "Q5 agg anidada engine>kw    " "/$OS_INDEX/_search?filter_path=took" '{"size":0,"aggs":{"e":{"terms":{"field":"STRATA--LOCATOR.SOURCEENGINE.keyword","size":50},"aggs":{"k":{"terms":{"field":"STRATA--LOCATOR.KEYWORDS.keyword","size":50}}}}}}'
medir "Q6 cardinality PARTICIPANTS " "/$OS_INDEX/_search?filter_path=took" '{"size":0,"aggs":{"c":{"cardinality":{"field":"STRATA--LOCATOR.PARTICIPANTS.keyword"}}}}'
```

### Resultado medido hoy (referencia) y comparación 1M -> 10M

| Query                         | 1M (med) | 10M (med) | Escala |
| ----------------------------- | -------: | --------: | -----: |
| Q1 term -> 1 (MEDIAID)        |     9 ms |     17 ms |   ~2x  |
| Q2 term -> muchos (size:0)    |     6 ms |      7 ms |  plano |
| **Q3 join has_child**         | **35 ms**| **311 ms**| **~9x**|
| Q4 agg facetas (terms)        |     8 ms |     10 ms |  plano |
| Q5 agg anidada                |    17 ms |     15 ms |  plano |
| Q6 cardinality (warm)         |        - |     13 ms | (cache)|

**CONCLUSIONES (para contar):**
- Con cachés/segmentos calientes, las búsquedas por `term` y las **agregaciones
  con `size:0` apenas se inmutan** al multiplicar x10 los datos: los índices
  invertidos son O(log n) y el `request_cache` sirve las aggs repetidas.
- El **`join` (has_child/has_parent) es lo que se degrada de verdad: ~9x** al
  pasar de 1M a 10M. Es la operación a vigilar y la primera candidata a
  rediseño si pesa en producción.
- OJO con el "warm": la 1a vez que se hace una `cardinality`/agg sobre un keyword
  de alta cardinalidad construye global ordinals y es MUCHO más lenta; las
  siguientes van por cache. Medir SIEMPRE con warmup (lo hace `medir`).

---

## 2b. Benchmark CONCURRENTE sostenido (mediana / p95, caché OFF)

Los disparos sueltos de la sección 2 van "en caliente" y con caché: enga&ntilde;an.
Para medir como en producción hay que lanzar **varias peticiones concurrentes
sostenidas** y, sobre todo, **parametrizar la query para que la caché no la sirva
ya hecha**. Para eso está `carga/bench.py`:

```bash
cd carga && . .venv/bin/activate

# 5 concurrentes, 20s, cache OFF (por defecto) y queries PARAMETRIZADAS:
python bench.py --query term1 -c 5 -d 20
python bench.py --query filter -c 5 -d 20
python bench.py --query agg    -c 5 -d 20
python bench.py --query join   -c 5 -d 25

# comparar el efecto de la cache en la MISMA familia:
python bench.py --query agg  -c 5 -d 15 --cache    # cache ON
python bench.py --query join -c 5 -d 15 --cache    # cache ON
```

Cómo evita la caché (2 capas):
1. **Query parametrizada**: cada petición usa un valor aleatorio (MEDIAID, SUBTYPE,
   SOURCEENGINE...) -> cambia el cache key y toca datos distintos.
2. **`request_cache=false`** en cada búsqueda (se puede reactivar con `--cache`).

### Resultado medido hoy (10.1M, concurrencia 5, caché OFF)


| Query                         | 1M (med) | 10M (med) | Escala |
| ----------------------------- | -------: | --------: | -----: |
| Q1 term -> 1 (MEDIAID)        |     9 ms |     17 ms |   ~2x  |
| Q2 term -> muchos (size:0)    |     6 ms |      7 ms |  plano |
| **Q3 join has_child**         | **35 ms**| **311 ms**| **~9x**|
| Q4 agg facetas (terms)        |     8 ms |     10 ms |  plano |
| Q5 agg anidada                |    17 ms |     15 ms |  plano |
| Q6 cardinality (warm)         |        - |     13 ms | (cache)|


| Query (familia)        | req/s | took med | took p95 | e2e med | e2e p95 |
| ---------------------- | ----: | -------: | -------: | ------: | ------: |
| term1 (id exacto)      |  56.7 |    75 ms |   148 ms |   83 ms |  159 ms |
| filter (count x subtype)| 164.1 |    11 ms |    57 ms |   22 ms |   70 ms |
| agg (faceta + filtro)  |  23.7 |   174 ms |   396 ms |  187 ms |  433 ms |
| **join (has_child)**   | **4.8**| **985 ms**|**1618 ms**|**1021 ms**|**1676 ms**|

> e2e = tiempo extremo-a-extremo (incluye cola+red); took = lo que dice el servidor.
> Bajo concurrencia el e2e > took porque las peticiones esperan turno.

### Efecto de la CACHÉ (misma query, OFF vs ON)

| Query | Caché OFF (med / req/s) | Caché ON (med / req/s) |
| ----- | ----------------------: | ---------------------: |
| agg   |      174 ms / 23.7 req/s |  **6 ms / 216.6 req/s** |
| join  |      985 ms /  4.8 req/s |     962 ms /  4.7 req/s |

**CONCLUSIONES (para contar):**
- La **caché de peticiones (request_cache) es brutal en agregaciones repetidas**:
  la misma faceta pasa de 174 ms a **6 ms** y de 24 a **217 req/s** (~30x). Por eso
  los **dashboards** (mismas aggs, `size:0`, filtros estables) vuelan... siempre
  que las consultas se REPITAN. Si cada usuario filtra distinto, no hay cache.
- La **caché NO ayuda al `join`**: 985 vs 962 ms. El has_child se recalcula casi
  siempre -> aquí no hay atajo de caché, hay que **rediseñar** (¿de verdad
  necesito la relación en esta consulta?).
- Medir con caché ON da números preciosos y FALSOS para capacity planning. Para
  dimensionar, medir como aquí: **concurrente + parametrizado + caché OFF**.
- El throughput es el reverso del coste: filter 164 req/s, agg 24, **join 4.8**.
  Con 5 usuarios concurrentes haciendo joins, el cluster ya va a ~1 s de mediana.

---

## 3. Variante BAJO CARGA (degradación en directo)

Idea: medir las mismas queries **mientras** se está indexando, para ver subir
el `took`, las colas del `write` pool y, si apretamos, los rechazos.

**Terminal A** (generador de carga — usa el script ya documentado en `carga/`):

```bash
cd carga && . .venv/bin/activate
# 4 workers, prefijo nuevo para no colisionar _id (ver carga/README.md)
PREFIX_BASE=CARGA_ ./lanzar_paralelo.sh 4 5000 --index lab_content --threads 3 --batch 500
```

**Terminal B** (mientras carga, repetir varias veces):

```bash
# latencia de busqueda bajo carga
medir "Q3 join BAJO CARGA " "/$OS_INDEX/_search?filter_path=took" '{"size":0,"query":{"has_child":{"type":"level_2","query":{"term":{"doc_type.keyword":"LOCATOR"}}}}}'
# saturacion del pool de escritura: vigilar queue y rejected
osq "/_cat/thread_pool/write?v&h=node_name,active,queue,rejected,completed"
# presion de indexacion y breakers
osq "/_nodes/stats?filter_path=nodes.*.indexing_pressure.memory.current.combined_coordinating_and_primary_in_bytes,nodes.*.breakers.parent.tripped"
```

Qué esperar / contar:
- El `took` de Q3 sube respecto a la línea base (CPU/disco compartidos con la ingesta).
- Si subimos workers/threads, aparece `queue` > 0 y eventualmente `rejected` > 0
  en el `write` pool (lección dia4: **más paralelismo NO es más throughput** una
  vez saturado; en la sesión anterior 6 workers rindieron MENOS que 4).
- `ram.percent` se mantiene ~100% (normal). Si el `parent.tripped` sube, hay
  agregaciones/queries pidiendo más memoria de la permitida.

> Limpieza opcional al acabar: los docs con prefijo CARGA_ se pueden borrar con
> `POST /lab_content/_delete_by_query` filtrando por `EDITORIAL--CONTAINER.MEDIAID.keyword: CARGA_*`
> (o `STRATA--LOCATOR.MEDIAID.keyword`). No es necesario para la práctica.

---

## 4. Experimentos de TUNING (antes / después)

Metodología en todos: **medir línea base -> aplicar cambio -> esperar verde ->
volver a medir -> comparar**. Cambiar 1 cosa cada vez.

### 4.0 CPU del contenedor: 1 -> 4 cores (límite del operador)  [dia4 punto 2]  — MEDIDO

El cluster corre sobre Kubernetes con el **OpenSearch Operator** (`opensearch.org/v1`,
CR `opensearch/opensearch`). Cada nodo tenía `limits.cpu: 1` (1 core) y `requests.cpu: 500m`.
Con 1 core/nodo, al subir la concurrencia del `join` el cluster no solo se ralentizaba:
**dejaba de aceptar conexiones** (los 3 cores al 100% sin hilos para el handshake).

> OJO: NO se parchea el StatefulSet (el operador lo revierte). Se parchea el **Custom
> Resource**; el operador hace un rolling restart pod-a-pod (estrategia `OnDelete`),
> esperando verde entre cada nodo. Tarda unos minutos y mueve shards al reincorporar.

```bash
# ver el límite actual del nodePool
kubectl get opensearchcluster.opensearch.org opensearch -n opensearch \
  -o jsonpath='{.spec.nodePools[0].resources}{"\n"}'

# subir SOLO limits.cpu a 4 (request y memoria se dejan igual)
kubectl patch opensearchcluster.opensearch.org opensearch -n opensearch --type='json' \
  -p='[{"op":"replace","path":"/spec/nodePools/0/resources/limits/cpu","value":"4"}]'

# seguir el rollout: el operador recrea los pods uno a uno (esperar a 4/4 y green)
kubectl get pods -n opensearch -o custom-columns=\
'POD:.metadata.name,CPU:.spec.containers[0].resources.limits.cpu,READY:.status.containerStatuses[0].ready' | grep nodes
# revertir: mismo patch con "value":"1"
```

**Antes (1 core) vs Después (4 cores)** — caché OFF, mismas queries/duraciones:

Concurrencia 5 (req/s · took med):

| Query  | req/s (1c -> 4c) | took med (1c -> 4c) | took p95 (1c -> 4c) |
| ------ | ---------------: | ------------------: | ------------------: |
| term1  |    79.9 -> 72.7  |     34 -> 42 ms     |    103 -> 102 ms    |
| filter |   158.8 -> 186.4 |      7 -> 6 ms      |     18 -> 10 ms     |
| agg    |   35.0 -> **68.5** |  110 -> **48 ms** |   214 -> **97 ms**  |
| join   |    5.2 -> **11.7** |  915 -> **397 ms**| 1521 -> **751 ms**  |

Concurrencia 10 (req/s · took med):

| Query  | req/s (1c -> 4c) | took med (1c -> 4c) | took p95 (1c -> 4c) |
| ------ | ---------------: | ------------------: | ------------------: |
| term1  |  107.6 -> **133.4** |   60 -> **20 ms** |    159 -> 146 ms    |
| filter |  211.3 -> **275.3** |    8 -> 6 ms      |     33 -> **13 ms** |
| agg    |   32.3 -> **81.2** |  209 -> **79 ms**  |   365 -> **129 ms** |
| **join** | ⛔ **0 (CAÍDO)** -> ✅ **12.6** | — -> **747 ms** | — -> **1291 ms** |

**CONCLUSIONES (para contar):**
- **El `join` a c=10 con 1 core NO devolvía resultados: el cluster se caía**
  (`ConnectTimeout`, 0 peticiones / 10 errores). Con 4 cores: **12.6 req/s, 0 errores**.
  El mismo test pasa de *caída de disponibilidad* a solo *"lento"*. La CPU no era un
  lujo, era el factor que evitaba el colapso.
- **`agg` es la gran beneficiada**: ~2x throughput y mitad de latencia en ambos niveles
  (c10: 32 -> 81 req/s, 209 -> 79 ms). Las agregaciones son CPU-bound puro -> casi lineal.
- **`filter`/`term1`** (ya baratas) mejoran de forma moderada: más cores = menos
  contención de hilos -> p95 más bajos a c=10.
- Confirma la tabla de prioridades (dia4): **"CPU *** barato, alto impacto (concurrencia)"**.
  Más cores no aceleran tanto la query suelta como **multiplican cuántas caben en paralelo**.
- Matiz que NO cambia: el `join` sigue siendo la query más cara (el `LateParsingQuery`
  no desaparece); 4 cores lo hacen *usable*, no *barato*. El rediseño (sección 7) sigue
  siendo la recomendación de fondo.

### 4.1 Réplicas 1 -> 2  (más concurrencia de LECTURA)  [dia4 punto 3]

Caso "contenidos": muchas búsquedas, poca ingesta -> interesa otra réplica.
Operación **dinámica y reversible** (no recrea el índice).

```bash
# ANTES
medir "Q3 (rep=1)" "/$OS_INDEX/_search?filter_path=took" '{"size":0,"query":{"has_child":{"type":"level_2","query":{"term":{"doc_type.keyword":"LOCATOR"}}}}}'

# subir a 2 replicas (OJO: copia ~6 GB por la red -> fuera de hora punta)
osq "/$OS_INDEX/_settings" -X PUT -H 'Content-Type: application/json' -d '{"index":{"number_of_replicas":2}}'
# esperar a que recupere (vuelve a green cuando termina de copiar)
osq "/_cluster/health/$OS_INDEX?wait_for_status=green&timeout=300s&filter_path=status,active_shards,relocating_shards"

# DESPUES (idealmente con varias busquedas concurrentes para notar la mejora)
medir "Q3 (rep=2)" "/$OS_INDEX/_search?filter_path=took" '{"size":0,"query":{"has_child":{"type":"level_2","query":{"term":{"doc_type.keyword":"LOCATOR"}}}}}'
```

Matices a contar:
- Una sola query secuencial puede NO mejorar (un shard atiende toda la consulta).
- La mejora se ve con **CONCURRENCIA**: más réplicas = más copias donde repartir
  búsquedas simultáneas. Demostrarlo lanzando N búsquedas en paralelo.
- Con 3 nodos, 3 shards y 2 réplicas = 9 copias -> 3 por nodo. (dia4: "1 primario
  + 2 réplicas" para el índice de contenidos; con `wait_for_active_shards=2` en la
  ingesta para no penalizar escritura, ver 4.5).
- Volver atrás: `{"index":{"number_of_replicas":1}}` (instantáneo, solo borra copias).

### 4.2 Réplicas 1 -> 0 para INGESTA masiva (y volver)

Para una carga grande puntual, quitar réplicas casi **duplica** el throughput de
escritura (no hay que replicar). Se reponen al terminar.

```bash
osq "/$OS_INDEX/_settings" -X PUT -H 'Content-Type: application/json' -d '{"index":{"number_of_replicas":0,"refresh_interval":"-1"}}'
#  ... lanzar la carga (Terminal A) ...
# al terminar: reactivar refresh y replicas, y forzar un refresh
osq "/$OS_INDEX/_settings" -X PUT -H 'Content-Type: application/json' -d '{"index":{"number_of_replicas":1,"refresh_interval":"1s"}}'
osq "/$OS_INDEX/_refresh"
```

`refresh_interval:-1` durante la carga evita crear segmentos cada segundo
(menos merges, más velocidad). Riesgo: los docs no son visibles hasta el refresh.

### 4.3 Primarios: SPLIT 3 -> 6 y SHRINK 6 -> 3  [dia4 punto 3]

Cambiar nº de primarios NO es dinámico. Reglas (dia4): doblar/mitad es fácil
(`_split` / `_shrink`); números "custom" obligan a recrear. Para no tocar el
índice de la práctica, se hace sobre un **clon barato** (hard-links, sin recargar
datos):

```bash
# 0) clonar lab_content -> lab_clone (requiere poner el origen en solo-lectura)
osq "/$OS_INDEX/_settings" -X PUT -H 'Content-Type: application/json' -d '{"index":{"blocks.write":true}}'
osq "/$OS_INDEX/_clone/lab_clone"
osq "/_cluster/health/lab_clone?wait_for_status=green&timeout=120s&filter_path=status"

# 1) SPLIT 3 -> 6  (el destino debe tener nº primarios multiplo del origen)
osq "/lab_clone/_settings" -X PUT -H 'Content-Type: application/json' -d '{"index":{"blocks.write":true}}'
osq "/lab_clone/_split/lab_split6" -H 'Content-Type: application/json' -d '{"settings":{"index.number_of_shards":6,"index.number_of_replicas":1}}'
osq "/_cluster/health/lab_split6?wait_for_status=green&timeout=300s&filter_path=status"
osq "/_cat/shards/lab_split6?v&h=shard,prirep,docs,store,node&s=shard,prirep"

# 2) SHRINK 6 -> 3  (requiere reunir una copia de todos los shards en 1 nodo)
osq "/lab_split6/_settings" -X PUT -H 'Content-Type: application/json' -d '{"index":{"blocks.write":true,"routing.allocation.require._name":"opensearch-nodes-0"}}'
osq "/_cluster/health/lab_split6?wait_for_status=green&timeout=300s&filter_path=status,relocating_shards"
osq "/lab_split6/_shrink/lab_shrink3" -H 'Content-Type: application/json' -d '{"settings":{"index.number_of_shards":3,"index.number_of_replicas":1,"index.routing.allocation.require._name":null}}'

# limpieza de los indices de prueba
osq "/lab_clone,lab_split6,lab_shrink3" -X DELETE
# devolver lab_content a escritura
osq "/$OS_INDEX/_settings" -X PUT -H 'Content-Type: application/json' -d '{"index":{"blocks.write":false}}'
```

Qué contar:
- `_split`/`_shrink` NO mueven dato fuera de Lucene: reusan segmentos -> rápidos.
- Más primarios = más paralelismo de ESCRITURA e ingesta; pero más consolidación
  en búsqueda. Para este volumen y POCA RAM, dia4 sugiere shards de ~0.5-1 GB.
- "números custom" (p.ej. 3->2) NO tienen operación directa: hay que recrear.

### 4.4 Caso "contenidos": 1 primario + 2 réplicas + wait_for_active_shards  [dia5]

dia5: si los shards juntos son pequeños (~300 MB en su caso real), tiene sentido
**1 primario + 2 réplicas** (HA + escalado de lectura), y en la ingesta pedir
`wait_for_active_shards=2` para no esperar a las 3 copias.

```bash
# crear un indice de demostracion con esa topologia
osq "/demo_contenidos" -X PUT -H 'Content-Type: application/json' -d '{"settings":{"index":{"number_of_shards":1,"number_of_replicas":2}}}'
# indexar pidiendo que confirmen 2 shards activos (no los 3)
osq "/demo_contenidos/_doc?wait_for_active_shards=2" -H 'Content-Type: application/json' -d '{"titulo":"prueba","texto":"contenido de ejemplo"}'
osq "/demo_contenidos" -X DELETE
```

### 4.5 "Bindings" / allocation: evitar reubicaciones que tumben el cluster  [dia4]

Cuando un nodo se cae, OpenSearch espera antes de re-replicar (mover GB por la
red). Subir ese retardo evita un "efecto dominó" si el nodo vuelve pronto.

```bash
# ver el valor actual
osq "/$OS_INDEX/_settings?include_defaults=true&filter_path=**.unassigned.node_left.delayed_timeout"
# subirlo a 10m (dia4): si el nodo vuelve en <10m, no se mueve ningun shard
osq "/$OS_INDEX/_settings" -X PUT -H 'Content-Type: application/json' -d '{"index":{"unassigned.node_left.delayed_timeout":"10m"}}'
```

(Esto es justo lo que vivimos ayer: un nodo fuera; con shards pequeños y delay
adecuado el cluster aguanta sin colapsar la red al reincorporarse.)

### 4.6 Mapping: text vs keyword (alta cardinalidad)  [dia4 punto 4]  — YA APLICADO

`STRATA--LOCATOR.DESCRIPTION` era `text` sin `.keyword` (no se podía agregar -> 400).
En la sesión anterior se añadió `.keyword` + `update_by_query`. Lección dia4:
- `keyword` -> filtros exactos, sorts y AGRUPACIONES.
- `text` -> búsqueda por relevancia.
- DESCRIPTION es de **alta cardinalidad** -> su índice `keyword` es GRANDE (los
  términos no se reutilizan). Regla YAGNI: no poner `.keyword` "por si acaso".

```bash
# comprobar el coste real de agregar sobre un keyword de alta cardinalidad
medir "agg DESCRIPTION.keyword (alta card)" "/$OS_INDEX/_search?filter_path=took" '{"size":0,"aggs":{"d":{"terms":{"field":"STRATA--LOCATOR.DESCRIPTION.keyword","size":10}}}}'
```

### 4.7 Reescritura de QUERIES (gana sin tocar infra)

```bash
# (a) filtro cacheable (bool/filter, sin score) vs query con score
medir "filter (cacheable)" "/$OS_INDEX/_search?filter_path=took" '{"size":0,"query":{"bool":{"filter":[{"term":{"EDITORIAL--CONTAINER.SUBTYPE.keyword":"VIDEO"}}]}}}'
medir "must   (con score) " "/$OS_INDEX/_search?filter_path=took" '{"size":0,"query":{"bool":{"must":[{"term":{"EDITORIAL--CONTAINER.SUBTYPE.keyword":"VIDEO"}}]}}}'

# (b) wildcard con comodin inicial (anti-patron) vs prefijo
medir "wildcard *...*" "/$OS_INDEX/_search?filter_path=took" '{"size":1,"query":{"wildcard":{"EDITORIAL--CONTAINER.MEDIAID.keyword":"*00000100*"}}}'
medir "prefix  ...*  " "/$OS_INDEX/_search?filter_path=took" '{"size":1,"query":{"prefix":{"EDITORIAL--CONTAINER.MEDIAID.keyword":"BIG_0_0000010"}}}'

# (c) paginacion profunda: from grande vs search_after
medir "from=9900" "/$OS_INDEX/_search?filter_path=took" '{"from":9900,"size":10,"query":{"term":{"doc_type.keyword":"LOCATOR"}},"sort":[{"STRATA--LOCATOR.SCORE":"desc"}]}'
```

---

## 5. Guion sugerido para HOY

1. **Foto + líneas base sobre 10M** (sección 1-2). Mensaje: casi todo escala bien
   menos el **join (~9x)**. Mostrar la tabla 1M vs 10M.
1b. **Benchmark concurrente (sección 2b)** con `bench.py -c 5`: enseñar la
   diferencia entre medir en caliente/cacheado (números bonitos y FALSOS) y medir
   bien (concurrente + parametrizado + caché OFF). Demostrar caché ON vs OFF en la
   `agg` (174 ms -> 6 ms) y que en el `join` la caché NO ayuda (~1 s siempre).
2. **Bajo carga** (sección 3): ver subir el `took` y las colas del `write` pool.
   Recordar: 6 workers < 4 workers (saturación) -> más paralelismo ≠ más rendimiento.
3. **Tuning con antes/después** eligiendo 2-3 de la sección 4 según tiempo:
   - réplicas 1->2 con concurrencia (4.1) — el que mejor se ve.
   - split/shrink sobre clon (4.3) — para el bloque de shards.
   - delayed_timeout (4.5) — enlaza con el incidente del nodo caído de ayer.
4. Cerrar con la **tabla de prioridades (dia4)**:

```text
1. RAM            *** barato, alto impacto (concurrencia)
2. CPU            *** barato, alto impacto (concurrencia)
3. SHARDS/REPLICAS*** ingesta y busquedas (seguir la tabla 1/3/multiplos de 3)
4. MAPPINGS       **  quitar lo indexado que no se usa (keyword vs text)
5. DOCS QUE SOBRAN*** "query y fuera" + merge
6. ARQ. INGESTA   *   mensajeria/amortiguacion, logs a memoria
7. DISEÑO/INDICES *   indice de auditoria, materializados para BI
```

> Regla de oro repetida en el curso: **medir en limpio, cambiar UNA cosa,
> volver a medir**. Sin línea base no se puede afirmar que algo "mejora".

---

## 6. RAMPA de concurrencia: ¿dónde satura?

Subir la concurrencia por escalones y ver hasta dónde sube el throughput antes de
estancarse (mientras la latencia se dispara). El punto donde el `req/s` deja de
crecer = **saturación**.

```bash
cd carga && . .venv/bin/activate
python bench.py --query filter --ramp 1,2,5,10,20,40 -d 12
python bench.py --query agg    --ramp 1,2,5,10,20    -d 12
python bench.py --query join   --ramp 1,2,5,10,20    -d 12
```

### Resultado medido hoy (10.1M, caché OFF)

**filter (count por subtype)** — escala bien, aún no satura a 40:

| conc | req/s | took_med | took_p95 | e2e_med | e2e_p95 |
| ---: | ----: | -------: | -------: | ------: | ------: |
|    1 |  79.6 |     5 ms |     8 ms |   12 ms |   16 ms |
|    2 | 153.7 |     5 ms |     9 ms |   12 ms |   18 ms |
|    5 | 222.0 |     7 ms |    39 ms |   16 ms |   52 ms |
|   10 | 274.5 |    12 ms |    66 ms |   28 ms |   80 ms |
|   20 | 330.4 |    30 ms |    89 ms |   51 ms |  127 ms |
|   40 | 412.3 |    48 ms |   132 ms |   84 ms |  230 ms |

**agg (faceta + filtro)** — **satura ~c=10** (throughput se clava en ~41 req/s y
la latencia se duplica a cada escalón):

| conc | req/s | took_med | took_p95 | e2e_med | e2e_p95 |
| ---: | ----: | -------: | -------: | ------: | ------: |
|    1 |   8.9 |    42 ms |    65 ms |   49 ms |   78 ms |
|    2 |  26.1 |    57 ms |   110 ms |   67 ms |  121 ms |
|    5 |  38.0 |   113 ms |   205 ms |  125 ms |  214 ms |
|   10 |  40.3 |   216 ms |   377 ms |  233 ms |  386 ms |
|   20 |  41.2 |   435 ms |   621 ms |  467 ms |  697 ms |  <- satura |

**join (has_child)** — **satura desde c=1** (~4-5 req/s); la concurrencia solo sube
la latencia de forma lineal (la cola):

| conc | req/s | took_med | took_p95 | took_p99 |
| ---: | ----: | -------: | -------: | -------: |
|    1 |   4.2 |   227 ms |   272 ms |   295 ms |
|    2 |   4.2 |   426 ms |   792 ms |  1218 ms |
|    5 |   4.4 |  1003 ms |  1806 ms |  1988 ms |
|   10 |   5.1 |  2011 ms |  3198 ms |  3381 ms |
|   20 |   5.5 |  3611 ms |  6521 ms |  7223 ms |

Con 20 usuarios haciendo joins a la vez, el p95 se va a **6,5 segundos**. El join no
escala: hay que rediseñarlo (ver explain en sección 7).

**CONCLUSIONES (para contar):**
- Hay dos tipos de query: las **baratas que escalan** con la concurrencia (`filter`
  llega a >400 req/s) y las **caras que saturan pronto** (`agg` ~41 req/s, `join`
  ~5 req/s). El cuello no es la query suelta, es **cuántas caben en paralelo**.
- Pasada la saturación, **el throughput NO sube y la latencia se dispara**: meter
  más usuarios concurrentes solo empeora el p95 (cola). Igual que con la ingesta:
  más paralelismo ≠ más rendimiento.
- Esto da el **número de usuarios concurrentes** que aguanta cada tipo de consulta
  antes de degradar -> base para capacity planning y para decidir réplicas/CPU.

---

## 7. EXPLAIN de las queries: qué está bien y qué puede dar problemas

`_validate/query?explain=true` muestra **cómo reescribe OpenSearch la query** sin
ejecutarla: revela si los filtros van como filtro puro (barato) o si hay algo caro.

```bash
osq "/$OS_INDEX/_validate/query?explain=true&filter_path=valid,explanations.explanation" \
  -H 'Content-Type: application/json' -d '{"query":{ ...la query... }}'
```

### Resultado real e interpretación (las 4 familias)

**term1 (CONTAINER por MEDIAID)** — reescritura:
```
#ConstantScore(doc_type.keyword:CONTAINER) #ConstantScore(EDITORIAL--CONTAINER.MEDIAID.keyword:BIG_0_00000001)
```
- `#` = cláusula de **filtro**; `ConstantScore` = **sin cálculo de score**. ✔ ÓPTIMO:
  dos lookups exactos sobre `keyword`, cacheables, O(log n). Nada que mejorar.

**filter (count por SUBTYPE)** — reescritura:
```
#ConstantScore(doc_type.keyword:CONTAINER) #ConstantScore(EDITORIAL--CONTAINER.SUBTYPE.keyword:VIDEO)
```
- ✔ IGUAL DE BUENO: filtros puros sobre `keyword`. Por eso escala a >400 req/s.

**join (has_child)** — reescritura:
```
+LateParsingQuery {joinField=join_field#level_1} #ConstantScore(EDITORIAL--CONTAINER.SUBTYPE.keyword:VIDEO)
```
- `+` = cláusula **obligatoria (must)**; **`LateParsingQuery`** = el join se resuelve
  **en tiempo de ejecución**, no es un término del índice invertido. ✗ AQUÍ ESTÁ EL
  COSTE: tiene que recorrer la relación padre-hijo (global ordinals + bitsets) por
  segmento. Es lo que explica el ~1 s y que no escale ni se cachee. **Candidato #1 a
  rediseño**: ¿necesito de verdad la relación en esta consulta, o puedo desnormalizar?

**agg (parte query)** — reescritura:
```
#ConstantScore(doc_type.keyword:LOCATOR) #ConstantScore(STRATA--LOCATOR.SOURCEENGINE.keyword:BATON)
```
- ✔ El FILTRADO es barato (filtros puros). El coste de la `agg` NO sale en el explain
  (el explain es de la query, no de la agregación): el gasto está en **construir los
  buckets / global ordinals** del `terms`/`cardinality`. Para verlo de verdad: usar
  `"profile": true` (sección 13 del fichero de Dev Tools) y mirar el bloque
  `aggregations` -> `build_aggregation`.

**Resumen visual:** `#ConstantScore(...)` = bien (filtro puro, barato). `LateParsingQuery`
o cláusulas que puntúan (`+algo:texto` con score) = mirar con lupa. En nuestras queries
el único patrón caro es el **join**; el resto reescribe a filtros puros.

> Para el coste de AGREGACIONES (no de la query), usar `profile:true` y leer
> `aggregations[].build_aggregation` / `collect` por shard.

---

## 8. CÓMO REPRODUCIR TODO (clase y en VUESTRA producción)

Todo apunta al cluster por **variables de entorno**: cambiándolas, esto corre contra
cualquier OpenSearch (el del curso o el vuestro de producción). Sin montar nada.

### 8.1 Preparación (una vez)
```bash
cd carga
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
```

### 8.2 Apuntar a VUESTRO cluster
```bash
# para curl (secciones 1-4)
export OS_URL='https://VUESTRO-OPENSEARCH:9200'
export OS_AUTH='usuario:password'
export OS_INDEX='voyager_content_xxx'        # vuestro indice real de contenidos

# para los scripts python (config.py); mismas credenciales
export OS_USER='usuario'; export OS_PASS='password'
# si los MEDIAID de vuestra carga usan otro prefijo, para que term1 acierte:
export OS_BENCH_PREFIXES='LAB0_,LAB1_,LAB2_,LAB3_'
```
Las queries de `bench.py` usan los nombres de campo reales (`EDITORIAL--CONTAINER`,
`STRATA--LOCATOR`, join `level_1/level_2`...), así que **funcionan tal cual contra
vuestros índices `voyager_content_*`**.

### 8.3 Qué es SEGURO lanzar en producción (solo lectura)
- Sección 1 (foto del cluster), 2 (`medir`), 2b/6 (`bench.py`), 7 (`explain`).
  Son **GET/búsquedas**: no modifican datos. Eso sí, generan carga -> hacerlo con
  cabeza (fuera de hora punta si apretáis concurrencia).

### 8.4 Qué crea/modifica datos (usar un índice de LAB aparte, NO el de prod)
```bash
# indice de laboratorio AUTOCONTENIDO (no necesita el mapping propietario):
python crear_indice.py --index lab_content --simple --recreate
# carga de prueba (4 procesos):
PREFIX_BASE=LAB_ ./lanzar_paralelo.sh 4 5000 --index lab_content
# medir / bench / rampa sobre ese indice de lab:
OS_INDEX=lab_content python bench.py --query join --ramp 1,2,5,10,20 -d 12
# experimentos de tuning (seccion 4) SIEMPRE sobre lab_content o un _clone, nunca prod.
```

### 8.5 Re-ejecución exacta de lo de clase (cluster del curso)
```bash
export OS_URL='https://opensearch.iochannel.tech' OS_AUTH='admin:Pa$$w0rd2026'
export OS_USER='admin' OS_PASS='Pa$$w0rd2026' OS_INDEX='lab_content'
# secciones 2, 2b, 6, 7 reproducen las tablas de este documento.
```

> Recordatorio de seguridad: en PRODUCCIÓN, limitarse a lo de 8.3. La carga, el
> borrado, el cambio de réplicas/primarios o el forcemerge solo sobre índices de
> laboratorio o clones; nunca sobre el índice vivo en horario de servicio.
