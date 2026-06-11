# =====================================================================
# ANALISIS AVANZADO DEL CLUSTER  -  OpenSearch 2.19.1
# Indice de trabajo: lab_content  (~1.000.443 docs, 3 shards / 1 replica)
# =====================================================================
# COMO USARLO:
#   - Pegar este fichero entero en OpenSearch Dashboards -> Dev Tools.
#   - Cada bloque "GET/POST ..." se ejecuta con el play (triangulo).
#   - Las lineas que empiezan por # son comentarios (no se ejecutan).
#   - Los numeros [MEDIDO: ...] son valores reales tomados sobre este
#     cluster con 1M de docs, como referencia/linea base.
#
# CONTEXTO DE HARDWARE (importante para interpretar todo):
#   3 nodos, rol "dim" (data+ingest+cluster_manager) -> NO hay nodos dedicados.
#   JVM heap = 4 GB / nodo. RAM contenedor: request 4 GB, limit 6 GB.
#   parent circuit breaker ~3.7 GB (95% del heap).
#   [MEDIDO] RAM del SO al 92-98% usada -> el filesystem cache esta a tope.
#            Con 4 GB de heap sobre 6 GB de limite quedan ~2 GB para
#            page cache de Lucene. Es el "jugar con fuego" de las notas:
#            margen estrecho para cachear segmentos en RAM.
#
# ÍNDICE (resumen):
#   docs=1.000.443 (LOCATOR 933.408 + CONTAINER 67.035, incl. subclips)
#   primarios ~570 MB, total (con replica) ~1.1 GB. Reparto equilibrado.


# =====================================================================
# 1. SALUD Y COMPOSICION GENERAL
# =====================================================================

GET /_cluster/health

# Lectura: status debe ser green; unassigned/initializing/relocating = 0.
# number_of_nodes=3, data_nodes=3.

GET /_cat/health?v

# Tareas pendientes del cluster-manager (creacion de indices, mappings...).
# Si crece de forma sostenida -> cluster-manager saturado.
# [MEDIDO] {"tasks":[]} -> sin tareas pendientes, cluster-manager ocioso.
GET /_cluster/pending_tasks

# Settings efectivos de watermarks de disco.
# [MEDIDO] low=85%  high=90%  flood_stage=95%  (valores por defecto).
#   low   -> deja de asignar shards nuevos al nodo.
#   high  -> intenta reubicar shards fuera del nodo.
#   flood -> pone los indices en read-only (bloqueo de escritura).
GET /_cluster/settings?include_defaults=true&filter_path=defaults.cluster.routing.allocation.disk.watermark,persistent,transient


# =====================================================================
# 2. NODOS: heap / RAM / CPU / disco   (radiografia rapida)
# =====================================================================

GET /_cat/nodes?v&h=name,node.role,master,heap.current,heap.max,heap.percent,ram.percent,cpu,load_1m,disk.used_percent

# [MEDIDO] heap usado 13-47% (sano), ram.percent 92-98% (page cache lleno).
# CONCLUSION: el heap NO es el cuello de botella ahora mismo; la presion
# esta en la RAM del SO (page cache). A mas datos, menos cabe en cache ->
# mas lecturas a disco. Vigilar al crecer el indice.

# Detalle operativo (os, jvm, fs, process, thread_pool) en una llamada:
GET /_nodes/stats/os,jvm,fs,process,thread_pool?filter_path=nodes.*.name,nodes.*.os.cpu.percent,nodes.*.os.mem.used_percent,nodes.*.jvm.mem.heap_used_percent,nodes.*.fs.total,nodes.*.thread_pool.search,nodes.*.thread_pool.write


# =====================================================================
# 3. INDICES, SHARDS Y ALLOCATION
# =====================================================================

GET /_cat/indices?v&s=store.size:desc

GET /_cat/shards/lab_content?v&h=shard,prirep,docs,store,node&s=shard,prirep

# [MEDIDO] ~333k docs/shard, ~190 MB/shard. Equilibrado entre los 3 nodos.
# CONCLUSION: 3 shards primarios sobre 3 nodos = 1 primario por nodo
# (reparto ideal de escritura). El tamano de shard (~190 MB) esta MUY por
# debajo de la recomendacion (10-50 GB). Para este volumen 1 solo shard
# bastaria; 3 ayudan a paralelizar escritura e ingesta.

GET /_cat/allocation?v&h=shards,disk.indices,disk.used,disk.avail,disk.percent,node

# [MEDIDO] disco al 24%, ~2.6 TB libres -> sin riesgo de watermark.

# Por que un shard esta (o no) asignado:
# [MEDIDO] shard 0 primario -> current_state="started", nodo "opensearch-nodes-2".
# (Si estuviera UNASSIGNED, aqui saldria el decider que lo impide.)
GET /_cluster/allocation/explain
{
  "index": "lab_content",
  "shard": 0,
  "primary": true
}


# =====================================================================
# 4. SEGMENTOS Y MERGES  (fragmentacion interna de Lucene)
# =====================================================================

GET /_cat/segments/lab_content?v&h=shard,prirep,segment,generation,docs.count,docs.deleted,size

GET /lab_content/_stats/segments,merges,refresh,flush?filter_path=_all.primaries.segments.count,_all.primaries.merges,_all.primaries.refresh,_all.primaries.flush

# [MEDIDO] recien cargado: ~32 segmentos en primarios, merges ~3,2 s,
#          refresh ~80 s, docs.deleted = 0, store ~1.1 GB.
# [MEDIDO] DESPUES del update_by_query del fix (seccion 12): docs.deleted=53.520,
#          77-83 segmentos/nodo, store 1.3 GB (de 1.1). Es decir: el reindex
#          dejo versiones viejas marcadas como borradas + mas fragmentacion.
# CONCLUSION: un update_by_query/reindex sobre 1M docs FRAGMENTA el indice
# (mas segmentos, mas espacio por docs borrados). Si el indice fuese de solo
# lectura, un forcemerge a 1 segmento reabsorberia esos borrados y bajaria
# RAM/disco. NO hacer forcemerge en indices que se siguen escribiendo.
#
# Solo para indices que ya NO se escriben (cuidado, operacion cara):
# POST /lab_content/_forcemerge?max_num_segments=1


# =====================================================================
# 5. THREAD POOLS Y COLAS  (saturacion de busqueda / escritura)
# =====================================================================

GET /_cat/thread_pool/search,write,get?v&h=node_name,name,active,queue,rejected,completed

# [MEDIDO] queue=0, rejected=0 en todos. write.completed alto (la carga 1M).
# Señal de alarma (no presente ahora): queue creciendo o rejected > 0.

GET /_nodes/stats/thread_pool?filter_path=nodes.*.name,nodes.*.thread_pool.search,nodes.*.thread_pool.write


# =====================================================================
# 6. JVM / GC Y CIRCUIT BREAKERS
# =====================================================================

GET /_nodes/stats/jvm?filter_path=nodes.*.name,nodes.*.jvm.mem.heap_used_percent,nodes.*.jvm.mem.heap_max_in_bytes,nodes.*.jvm.gc

# Vigilar: old GC frecuente, tiempo alto en GC, heap que no baja tras GC.

GET /_nodes/stats/breaker?filter_path=nodes.*.name,nodes.*.breakers.parent,nodes.*.breakers.fielddata.tripped,nodes.*.breakers.request.tripped

# [MEDIDO] parent limit ~3.7 GB, tripped=0 en todos los breakers.
# CONCLUSION: sin disparos de breaker todavia. Las aggs de alta cardinalidad
# (ver seccion 11) son las que mas se acercan al limite.


# =====================================================================
# 7. CACHES  (query_cache / request_cache / fielddata)
# =====================================================================

GET /_nodes/stats/indices/query_cache,request_cache,fielddata?filter_path=nodes.*.name,nodes.*.indices.query_cache,nodes.*.indices.request_cache,nodes.*.indices.fielddata

# [MEDIDO] query_cache: hit_count=0, todo miss (826/806/395) -> 0% aciertos.
#          request_cache: SI hay aciertos (las aggs con size:0 se cachean).
#          fielddata: ~2 MB/nodo (de las aggs sobre campos .keyword).
# CONCLUSION (mejora): el query_cache no se aprovecha porque las pruebas usan
# filtros muy variados y size>0. El node query cache solo cachea filtros en
# segmentos grandes y consultas repetidas. Para dashboards (mismas aggs
# repetidas con size:0) lo que rinde es el REQUEST cache -> y ahi si hay hits.
# Recomendacion: en dashboards usar bool/filter (cacheable) y size:0.


# =====================================================================
# 8. LINEAS BASE DE BUSQUEDA
# (medir el "took" en condiciones ideales: cluster en reposo, repetir 30x,
#  quedarse con minimo/mediana/p95; ya calentado el JIT y las caches)
# =====================================================================
# Resumen de lo medido en este cluster (took en ms, 30 repeticiones):
#   Q1 term -> 1 resultado .......... min 5  / med 9  / p95 15
#   Q2 term -> muchos (size:0) ...... min 5  / med 6  / p95 10
#   Q3 join has_child ............... min 21 / med 35 / p95 44   <- el join cuesta ~4x
#   Q4 agg terms (facetas) .......... min 6  / med 8  / p95 10
#   Q5 agg anidada (2 niveles) ...... min 9  / med 17 / p95 25
#   cardinality alta-card ........... ~8.305 ms (!!)            <- ver seccion 11
#   wildcard *...* (anti-patron) .... ~354 ms                   <- ver seccion 12


# =====================================================================
# 9. QUERIES SIMPLES
# =====================================================================

# 9.1 Devuelve 1: un CONTAINER por su MEDIAID (filtro por keyword exacto).
# [MEDIDO] took ~5-15 ms.
GET /lab_content/_search
{
  "size": 1,
  "query": {
    "bool": {
      "filter": [
        { "term": { "doc_type.keyword": "CONTAINER" } },
        { "term": { "EDITORIAL--CONTAINER.MEDIAID.keyword": "LAB_00000001" } }
      ]
    }
  }
}

# 9.2 Devuelve muchos: solo el conteo (size:0) de LOCATOR.
# [MEDIDO] took ~5-10 ms. El conteo es baratisimo (no trae documentos).
GET /lab_content/_search
{
  "size": 0,
  "query": { "term": { "doc_type.keyword": "LOCATOR" } }
}

# 9.3 Devuelve muchos con _source recortado (buena practica: traer solo lo necesario).
# [MEDIDO] took ~24-279 ms (el primero "en frio" mas alto; se estabiliza ~25 ms).
# El sort por fecha es barato: la fecha es numerica y esta indexada.
GET /lab_content/_search
{
  "size": 20,
  "_source": ["EDITORIAL--CONTAINER.MEDIAID", "EDITORIAL_CORE--EDC_DUBLIN_CORE.DC_DESCRIPTION.DM_TITLE"],
  "query": { "term": { "doc_type.keyword": "CONTAINER" } },
  "sort": [ { "EDITORIAL--CONTAINER.CREATIONDATE": { "order": "desc", "missing": "_last" } } ]
}


# =====================================================================
# 10. QUERIES COMPLEJAS  (relaciones padre-hijo via join)
# =====================================================================

# 10.1 CONTAINER que tienen algun LOCATOR (has_child) con inner_hits.
# [MEDIDO] took ~21-44 ms. El join es la operacion mas cara medida.
GET /lab_content/_search
{
  "size": 2,
  "_source": ["EDITORIAL--CONTAINER.MEDIAID"],
  "query": {
    "bool": {
      "must": [
        { "term": { "doc_type.keyword": "CONTAINER" } },
        {
          "has_child": {
            "type": "level_2",
            "inner_hits": { "size": 2, "_source": ["STRATA--LOCATOR.TYPEID", "STRATA--LOCATOR.DESCRIPTION"] },
            "query": { "term": { "doc_type.keyword": "LOCATOR" } }
          }
        }
      ]
    }
  }
}

# 10.2 LOCATOR cuyo CONTAINER padre cumple condiciones (has_parent).
GET /lab_content/_search
{
  "size": 5,
  "_source": ["STRATA--LOCATOR.TYPEID", "STRATA--LOCATOR.DESCRIPTION"],
  "query": {
    "bool": {
      "filter": [ { "term": { "doc_type.keyword": "LOCATOR" } } ],
      "must": [
        {
          "has_parent": {
            "parent_type": "level_1",
            "query": {
              "bool": { "must": [ { "term": { "EDITORIAL--CONTAINER.SUBTYPE.keyword": "VIDEO" } } ] }
            },
            "inner_hits": { "name": "padre", "size": 1, "_source": ["EDITORIAL--CONTAINER.MEDIAID"] }
          }
        }
      ]
    }
  }
}

# 10.3 Subclips (CONTAINER que cuelgan de otro CONTAINER) con su clip padre.
GET /lab_content/_search
{
  "size": 3,
  "_source": ["EDITORIAL--CONTAINER.MEDIAID", "EDITORIAL--CONTAINER.ISSUBCLIP"],
  "query": {
    "bool": {
      "filter": [
        { "term": { "doc_type.keyword": "CONTAINER" } },
        { "term": { "EDITORIAL--CONTAINER.ISSUBCLIP": true } }
      ],
      "must": [
        {
          "has_parent": {
            "parent_type": "level_1",
            "query": { "match_all": {} },
            "inner_hits": { "name": "clip_padre", "size": 1, "_source": ["EDITORIAL--CONTAINER.MEDIAID"] }
          }
        }
      ]
    }
  }
}


# =====================================================================
# 11. AGREGACIONES  (carga analitica = dashboards)
# =====================================================================

# 11.1 Faceta simple por tipo de locator (terms). size:0 -> cacheable.
# [MEDIDO] took ~6-10 ms.
GET /lab_content/_search
{
  "size": 0,
  "query": { "term": { "doc_type.keyword": "LOCATOR" } },
  "aggs": { "por_tipo": { "terms": { "field": "STRATA--LOCATOR.TYPEID.keyword", "size": 100 } } }
}

# 11.2 Faceta anidada (engine -> keywords). 2 niveles.
# [MEDIDO] took ~9-25 ms.
GET /lab_content/_search
{
  "size": 0,
  "aggs": {
    "por_engine": {
      "terms": { "field": "STRATA--LOCATOR.SOURCEENGINE.keyword", "size": 50 },
      "aggs": { "keywords": { "terms": { "field": "STRATA--LOCATOR.KEYWORDS.keyword", "size": 50 } } }
    }
  }
}

# 11.3 CARDINALITY sobre campos de alta cardinalidad  <-- OPERACION CARA
# [MEDIDO] took ~8.305 ms. PARTICIPANTS distintos = 608.720.
# CONCLUSION (mejora): cardinality (HyperLogLog++) sobre campos muy diversos
# es lo mas caro que hemos visto, ~1000x una busqueda simple. En dashboards,
# evitar cardinality sobre campos de altisima cardinalidad o subir
# precision_threshold con cabeza. Es el principal candidato a optimizar.
GET /lab_content/_search
{
  "size": 0,
  "aggs": {
    "participantes_distintos": { "cardinality": { "field": "STRATA--LOCATOR.PARTICIPANTS.keyword" } },
    "creadores_distintos":     { "cardinality": { "field": "EDITORIAL_CORE--EDC_DUBLIN_CORE.DC_CREATOR.ENTITY_NAME.keyword" } }
  }
}


# =====================================================================
# 12. ANTI-PATRONES  (demostraciones de "que NO hacer")
# =====================================================================

# 12.1 Agregar sobre un campo TEXT sin sub-campo keyword -> ERROR 400.
# [MEDIDO] devuelve illegal_argument_exception (fielddata disabled).
# CONCLUSION: para agregar/ordenar hay que usar el sub-campo .keyword.
# Activar fielddata=true en un text es peligroso (se come el heap).
GET /lab_content/_search
{
  "size": 0,
  "aggs": { "desc": { "terms": { "field": "STRATA--LOCATOR.DESCRIPTION", "size": 10 } } }
}

# ---- FIX del 400 (aplicado en este indice) -------------------------------
# El campo STRATA--LOCATOR.DESCRIPTION es 'text' sin sub-campo keyword, por eso
# no se puede agregar. Solucion canonica (la que sugiere el propio error):
# anadir un multi-campo .keyword y reindexar los docs ya existentes.
#
# Paso 1: anadir el multi-campo (afecta solo a docs NUEVOS de momento).
PUT /lab_content/_mapping
{
  "properties": {
    "STRATA--LOCATOR": {
      "properties": {
        "DESCRIPTION": {
          "type": "text",
          "fields": { "keyword": { "type": "keyword", "ignore_above": 256 } }
        }
      }
    }
  }
}

# Paso 2: poblar el .keyword en los docs ya indexados (reindex in-place).
# OJO: en 1M docs tarda y FRAGMENTA (ver seccion 4). Lanzar en async.
# [MEDIDO] el proxy nginx corta a ~60s con 504; por eso wait_for_completion=false.
POST /lab_content/_update_by_query?wait_for_completion=false&conflicts=proceed
{
  "query": {
    "bool": {
      "filter":   [ { "term": { "doc_type.keyword": "LOCATOR" } } ],
      "must_not": [ { "exists": { "field": "STRATA--LOCATOR.DESCRIPTION.keyword" } } ]
    }
  }
}

# Paso 2b: seguir el progreso de la tarea (sustituir <task_id> por el devuelto).
# GET /_tasks/<task_id>
# O comprobar cobertura: cuantos LOCATOR ya tienen el keyword poblado.
GET /lab_content/_count
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "doc_type.keyword": "LOCATOR" } },
        { "exists": { "field": "STRATA--LOCATOR.DESCRIPTION.keyword" } }
      ]
    }
  }
}

# Paso 3: ahora SI funciona la agregacion (antes 400).
# [MEDIDO] took ~5.564 ms. Cuidado: DESCRIPTION.keyword tiene altisima
# cardinalidad (texto casi unico) -> agregacion cara. Solo tiene sentido
# agregar sobre keyword de BAJA cardinalidad (tipos, estados, codecs...).
GET /lab_content/_search
{
  "size": 0,
  "aggs": { "desc": { "terms": { "field": "STRATA--LOCATOR.DESCRIPTION.keyword", "size": 3 } } }
}
# --------------------------------------------------------------------------

# 12.2 Wildcard con comodin inicial -> escaneo de todos los terminos.
# [MEDIDO] took ~354 ms (vs ~10 ms de un term). ~30-70x mas lento.
# CONCLUSION: evitar "*...*". Si se necesita, usar wildcard field, ngrams o
# search_as_you_type. Un term/prefix sobre keyword es ordenes de magnitud mejor.
GET /lab_content/_search
{
  "size": 1,
  "query": { "wildcard": { "EDITORIAL--CONTAINER.MEDIAID.keyword": "*0000100*" } }
}

# 12.3 Paginacion profunda (from grande) -> coste creciente.
# [MEDIDO] from=0 -> ~65 ms ; from=9900 -> ~544 ms  (~8x mas caro).
# CONCLUSION: from+size carga y ordena from+size en cada shard. Para ir lejos
# usar search_after (o PIT). NO subir from a decenas de miles (limite por
# defecto max_result_window = 10.000).
GET /lab_content/_search
{
  "from": 9900,
  "size": 10,
  "query": { "term": { "doc_type.keyword": "LOCATOR" } },
  "sort": [ { "STRATA--LOCATOR.SCORE": "desc" } ]
}


# =====================================================================
# 13. PROFILING Y EXPLAIN  (entender el plan de ejecucion)
# =====================================================================

# 13.1 profile:true -> desglose por shard/fase (query, fetch) y por sub-query.
# Mirar: tiempos por tipo de query, build_scorer, collector, advance...
GET /lab_content/_search
{
  "profile": true,
  "size": 0,
  "query": {
    "bool": {
      "filter": [ { "term": { "doc_type.keyword": "LOCATOR" } } ],
      "must": [ { "match": { "STRATA--LOCATOR.DESCRIPTION": "test" } } ]
    }
  }
}

# 13.2 explain de scoring de un documento concreto frente a una query.
# [MEDIDO] con "field" (palabra real de las descripciones) -> _explanation.value ~8.06.
# (Con una palabra que no aparece, hits=0 y no hay explanation.)
GET /lab_content/_search
{
  "explain": true,
  "size": 1,
  "query": { "match": { "STRATA--LOCATOR.DESCRIPTION": "field" } }
}

# 13.3 _validate/query?explain -> ver como se reescribe la query sin ejecutarla.
GET /lab_content/_validate/query?explain=true
{
  "query": { "wildcard": { "EDITORIAL--CONTAINER.MEDIAID.keyword": "*0000100*" } }
}


# =====================================================================
# 14. CONCLUSIONES GLOBALES Y MEJORAS PROPUESTAS
# =====================================================================
# ESTADO GENERAL: cluster sano. green, 0 rejected, 0 breakers tripped,
# disco 24%, heap 13-47%. Las busquedas simples y las facetas van finas
# (5-25 ms). No hay cuello de botella agudo con 1M de docs.
#
# PUNTOS A MEJORAR (ordenados por impacto):
#
# 1) RAM del SO al 92-98% (page cache saturado).
#    Es el limite real al crecer. 4 GB heap + ~2 GB page cache sobre 6 GB.
#    -> Si el indice crece mucho, subir el limit de RAM del pod, o mover
#       datos frios a otro indice/tier. El heap (4 GB) esta bien dimensionado;
#       no subirlo por encima de ~50% de la RAM ni de 31 GB (compressed oops).
#
# 2) cardinality sobre alta cardinalidad = ~8,3 s (1000x una busqueda).
#    -> En dashboards, limitar/evitar; ajustar precision_threshold; o
#       precalcular metricas. Es el principal riesgo de breaker bajo carga.
#
# 3) Mapping sobredimensionado / desajustado.
#    dynamic:false (bien), pero el ajuste de campos no estaba afinado:
#    - DESCRIPTION era text SIN .keyword -> no se podia agregar (400). FIX
#      aplicado en seccion 12: anadido .keyword + update_by_query (1M docs).
#      Leccion: decidir por campo si necesita full-text, keyword, o ambos.
#    - Casi todos los demas text SI llevan .keyword aunque no se agregue por
#      ellos. Cada sub-campo extra = mas terminos, mas disco y mas RAM.
#    -> Lo ideal: keyword solo donde se filtra/agrega/ordena exacto; text solo
#       donde se busca por relevancia. Cambiar el mapping de un campo existente
#       obliga a reindexar (como acabamos de ver), asi que se decide al disenar.
#
# 4) join (has_child/has_parent) cuesta ~4x.
#    eager_global_ordinals:true ya esta puesto (bien para el join). Asumido el
#    coste si el modelo lo necesita; si una consulta no requiere la relacion,
#    no usar join.
#
# 5) query_cache con 0 aciertos.
#    Para carga de dashboards, apoyarse en request_cache (size:0 + filtros
#    estables en bool/filter) que SI cachea. Evitar size>0 y filtros volatiles
#    cuando se quiera cache.
#
# 6) Shards muy pequenos (~190 MB) para la recomendacion (10-50 GB).
#    Correcto para este volumen de lab (3 shards = paralelismo de escritura).
#    Si fuese un indice de solo-lectura estable -> menos shards + forcemerge.
#
# SIGUIENTE PASO sugerido: repetir estas lineas base BAJO CARGA (lanzando
# el cargador en paralelo) y comparar el "took" y los thread_pool/breakers
# antes/despues. Ahi es donde apareceran los sintomas reales de degradacion.
