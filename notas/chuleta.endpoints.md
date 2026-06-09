# Catálogo de endpoints para fundamentos de monitorización

## Objetivo del documento

Este documento recopila los endpoints para:

* comprobar el estado general del cluster;
* revisar nodos;
* analizar índices;
* revisar shards;
* detectar problemas de asignación;
* observar consumo de CPU, heap, disco y memoria;
* revisar thread pools, colas y rechazos;
* analizar búsqueda e indexación;
* observar segmentos, merges y cachés;
* detectar circuit breakers;
* preparar una línea base de rendimiento.

---

# 1. Salud general del cluster

---

## 1.1 `GET /_cluster/health`

### Uso

Permite obtener una visión global del estado del cluster.

Es uno de los primeros endpoints que se deben consultar ante cualquier problema.

Sirve para responder:

* ¿El cluster está disponible?
* ¿Está en estado `green`, `yellow` o `red`?
* ¿Hay shards no asignados?
* ¿Hay shards inicializando?
* ¿Hay shards relocalizándose?
* ¿Hay tareas pendientes?
* ¿Cuántos nodos forman parte del cluster?

### Endpoint

```http
GET /_cluster/health
```

### Ejemplo de envío

```http
GET /_cluster/health?pretty
```

### Ejemplo de salida

```json
{
  "cluster_name": "opensearch-cluster",
  "status": "green",
  "timed_out": false,
  "number_of_nodes": 3,
  "number_of_data_nodes": 3,
  "discovered_master": true,
  "active_primary_shards": 12,
  "active_shards": 24,
  "relocating_shards": 0,
  "initializing_shards": 0,
  "unassigned_shards": 0,
  "delayed_unassigned_shards": 0,
  "number_of_pending_tasks": 0,
  "task_max_waiting_in_queue_millis": 0,
  "active_shards_percent_as_number": 100.0
}
```

### Interpretación

| Campo                     | Significado                                  |
| ------------------------- | -------------------------------------------- |
| `status`                  | Estado general del cluster                   |
| `number_of_nodes`         | Número total de nodos                        |
| `number_of_data_nodes`    | Número de nodos con datos                    |
| `active_primary_shards`   | Shards primarios activos                     |
| `active_shards`           | Total de shards activos, incluyendo réplicas |
| `relocating_shards`       | Shards moviéndose entre nodos                |
| `initializing_shards`     | Shards inicializándose                       |
| `unassigned_shards`       | Shards sin asignar                           |
| `number_of_pending_tasks` | Tareas pendientes en el cluster              |

### Lectura rápida

| Estado   | Significado                                                 |
| -------- | ----------------------------------------------------------- |
| `green`  | Todos los primarios y réplicas están asignados              |
| `yellow` | Todos los primarios están asignados, pero alguna réplica no |
| `red`    | Algún shard primario no está asignado                       |

---

## 1.2 `GET /_cat/health`

### Uso

Muestra la salud del cluster en formato tabular.

Es útil para una revisión rápida desde consola.

### Endpoint

```http
GET /_cat/health
```

### Ejemplo de envío

```http
GET /_cat/health?v
```

### Ejemplo de salida

```text
epoch      timestamp cluster            status node.total node.data shards pri relo init unassign pending_tasks max_task_wait_time active_shards_percent
1760000000 10:30:25  opensearch-cluster green  3          3         24     12  0    0    0        0             -                  100.0%
```

### Interpretación

| Campo           | Significado              |
| --------------- | ------------------------ |
| `status`        | Estado general           |
| `node.total`    | Número total de nodos    |
| `node.data`     | Número de nodos de datos |
| `shards`        | Total de shards activos  |
| `pri`           | Shards primarios         |
| `relo`          | Shards relocalizándose   |
| `init`          | Shards inicializándose   |
| `unassign`      | Shards no asignados      |
| `pending_tasks` | Tareas pendientes        |

---

## 1.3 `GET /_cluster/pending_tasks`

### Uso

Permite ver tareas pendientes gestionadas por el nodo cluster-manager.

Es útil cuando el cluster parece lento a nivel administrativo:

* creación de índices lenta;
* cambios de mappings lentos;
* asignación de shards lenta;
* muchas operaciones administrativas pendientes;
* cluster state pesado.

### Endpoint

```http
GET /_cluster/pending_tasks
```

### Ejemplo de envío

```http
GET /_cluster/pending_tasks?pretty
```

### Ejemplo de salida

```json
{
  "tasks": [
    {
      "insert_order": 101,
      "priority": "HIGH",
      "source": "create-index [logs-2026.06.08]",
      "executing": false,
      "time_in_queue_millis": 2450,
      "time_in_queue": "2.4s"
    }
  ]
}
```

### Interpretación

| Campo           | Significado                  |
| --------------- | ---------------------------- |
| `priority`      | Prioridad de la tarea        |
| `source`        | Origen de la tarea           |
| `executing`     | Indica si se está ejecutando |
| `time_in_queue` | Tiempo esperando en cola     |

### Señales de alarma

* muchas tareas pendientes;
* tareas esperando muchos segundos o minutos;
* tareas relacionadas con asignación de shards;
* cambios frecuentes de mappings;
* creación masiva de índices;
* cluster-manager saturado.

---

# 2. Información de nodos

---

## 2.1 `GET /_cat/nodes`

### Uso

Muestra una vista rápida de los nodos del cluster.

Sirve para detectar:

* nodos con CPU alta;
* nodos con heap alto;
* nodos con uso de RAM elevado;
* nodos con disco alto;
* roles de cada nodo;
* nodo cluster-manager activo;
* posibles nodos calientes.

### Endpoint

```http
GET /_cat/nodes
```

### Ejemplo de envío

```http
GET /_cat/nodes?v
```

### Ejemplo de salida

```text
ip         heap.percent ram.percent cpu load_1m load_5m load_15m node.role master name
10.0.0.10 42           71          18  1.20    1.10    0.90     dimr      -      os-data-1
10.0.0.11 78           84          87  5.30    4.80    4.20     dimr      *      os-data-2
10.0.0.12 39           68          22  1.40    1.20    1.00     dimr      -      os-data-3
```

### Interpretación

| Campo          | Significado                         |
| -------------- | ----------------------------------- |
| `heap.percent` | Porcentaje de heap JVM usado        |
| `ram.percent`  | Porcentaje de RAM del sistema usada |
| `cpu`          | Uso de CPU                          |
| `load_1m`      | Carga media del último minuto       |
| `node.role`    | Roles del nodo                      |
| `master`       | Nodo cluster-manager activo         |
| `name`         | Nombre del nodo                     |

### Lectura del ejemplo

El nodo `os-data-2` destaca porque tiene:

* heap más alto;
* CPU mucho más alta;
* load average superior;
* además es el cluster-manager activo.

Podría ser un nodo caliente o estar asumiendo demasiadas responsabilidades.

---

## 2.2 `GET /_cat/nodes` con columnas concretas

### Uso

Permite personalizar las columnas que queremos ver.

Es recomendable para crear salidas más limpias en clase o para línea base.

### Endpoint

```http
GET /_cat/nodes?v&h=name,ip,node.role,master,heap.percent,ram.percent,cpu,load_1m,disk.used_percent
```

### Ejemplo de envío

```http
GET /_cat/nodes?v&h=name,ip,node.role,master,heap.percent,ram.percent,cpu,load_1m,disk.used_percent
```

### Ejemplo de salida

```text
name      ip         node.role master heap.percent ram.percent cpu load_1m disk.used_percent
os-data-1 10.0.0.10 dimr      -      42           71          18  1.20    35
os-data-2 10.0.0.11 dimr      *      78           84          87  5.30    72
os-data-3 10.0.0.12 dimr      -      39           68          22  1.40    38
```

### Uso recomendado

Este formato es muy útil para una primera radiografía del cluster.

---

## 2.3 `GET /_nodes/stats`

### Uso

Devuelve estadísticas detalladas de todos los nodos.

Es uno de los endpoints más importantes para diagnóstico técnico.

Permite revisar:

* sistema operativo;
* JVM;
* proceso;
* filesystem;
* thread pools;
* índices;
* búsqueda;
* indexación;
* merges;
* segmentos;
* cachés;
* breakers;
* presión interna.

### Endpoint

```http
GET /_nodes/stats
```

### Ejemplo de envío

```http
GET /_nodes/stats?pretty
```

### Ejemplo de salida abreviada

```json
{
  "cluster_name": "opensearch-cluster",
  "nodes": {
    "nodeId1": {
      "name": "os-data-1",
      "roles": ["data", "ingest", "master"],
      "indices": {
        "docs": {
          "count": 12000000,
          "deleted": 50000
        },
        "store": {
          "size_in_bytes": 19327352832
        }
      },
      "os": {
        "cpu": {
          "percent": 18
        },
        "mem": {
          "used_percent": 71
        }
      },
      "jvm": {
        "mem": {
          "heap_used_percent": 42
        }
      }
    }
  }
}
```

### Interpretación

Este endpoint es muy grande. En la práctica se suele filtrar por secciones.

---

## 2.4 `GET /_nodes/stats/os,jvm,fs,process,thread_pool`

### Uso

Devuelve solo las partes más importantes para una línea base inicial de nodos.

### Endpoint

```http
GET /_nodes/stats/os,jvm,fs,process,thread_pool
```

### Ejemplo de envío

```http
GET /_nodes/stats/os,jvm,fs,process,thread_pool?pretty
```

### Ejemplo de salida abreviada

```json
{
  "nodes": {
    "nodeId1": {
      "name": "os-data-1",
      "os": {
        "cpu": {
          "percent": 18
        },
        "mem": {
          "total_in_bytes": 34359738368,
          "used_percent": 71
        }
      },
      "jvm": {
        "mem": {
          "heap_used_percent": 42,
          "heap_used_in_bytes": 7214202880,
          "heap_max_in_bytes": 17179869184
        },
        "gc": {
          "collectors": {
            "young": {
              "collection_count": 1200,
              "collection_time_in_millis": 8500
            },
            "old": {
              "collection_count": 3,
              "collection_time_in_millis": 900
            }
          }
        }
      },
      "fs": {
        "total": {
          "total_in_bytes": 536870912000,
          "free_in_bytes": 348966092800,
          "available_in_bytes": 348966092800
        }
      },
      "thread_pool": {
        "search": {
          "threads": 13,
          "queue": 0,
          "active": 2,
          "rejected": 0,
          "completed": 450000
        }
      }
    }
  }
}
```

### Interpretación

| Sección       | Uso                       |
| ------------- | ------------------------- |
| `os`          | CPU y memoria del sistema |
| `jvm`         | Heap y garbage collection |
| `fs`          | Disco                     |
| `process`     | Proceso OpenSearch        |
| `thread_pool` | Colas, activos y rechazos |

---

# 3. Índices

---

## 3.1 `GET /_cat/indices`

### Uso

Muestra información tabular sobre los índices.

Sirve para detectar:

* índices más grandes;
* número de shards;
* número de réplicas;
* cantidad de documentos;
* índices en estado yellow o red;
* índices pequeños con demasiados shards;
* índices grandes con pocos shards.

### Endpoint

```http
GET /_cat/indices
```

### Ejemplo de envío

```http
GET /_cat/indices?v
```

### Ejemplo de salida

```text
health status index              uuid   pri rep docs.count docs.deleted store.size pri.store.size
green  open   logs-2026.06.08    abc1   3   1   12000000   50000        18gb       9gb
green  open   products           abc2   1   1   500000     1200         2gb        1gb
yellow open   metrics-2026.06    abc3   6   1   90000000   800000       120gb      60gb
```

### Interpretación

| Campo            | Significado                      |
| ---------------- | -------------------------------- |
| `health`         | Estado del índice                |
| `status`         | Abierto o cerrado                |
| `index`          | Nombre del índice                |
| `pri`            | Número de shards primarios       |
| `rep`            | Número de réplicas               |
| `docs.count`     | Documentos vivos                 |
| `docs.deleted`   | Documentos borrados internamente |
| `store.size`     | Tamaño total incluyendo réplicas |
| `pri.store.size` | Tamaño de primarios              |

---

## 3.2 `GET /_cat/indices` ordenado por tamaño

### Uso

Permite identificar rápidamente los índices que más ocupan.

### Endpoint

```http
GET /_cat/indices?v&s=store.size:desc
```

### Ejemplo de envío

```http
GET /_cat/indices?v&s=store.size:desc
```

### Ejemplo de salida

```text
health status index              pri rep docs.count store.size pri.store.size
yellow open   metrics-2026.06    6   1   90000000   120gb      60gb
green  open   logs-2026.06.08    3   1   12000000   18gb       9gb
green  open   products           1   1   500000     2gb        1gb
```

### Uso recomendado

Primer paso para localizar índices candidatos a revisión.

---

## 3.3 `GET /_stats`

### Uso

Devuelve estadísticas detalladas de índices.

Sirve para revisar de forma amplia:

* documentos;
* almacenamiento;
* búsqueda;
* indexación;
* segmentos;
* merges;
* refresh;
* flush;
* cachés;
* translog.

### Endpoint

```http
GET /_stats
```

### Ejemplo de envío

```http
GET /_stats?pretty
```

### Ejemplo de salida abreviada

```json
{
  "_all": {
    "primaries": {
      "docs": {
        "count": 102500000,
        "deleted": 851200
      },
      "store": {
        "size_in_bytes": 75161927680
      },
      "indexing": {
        "index_total": 5000000,
        "index_time_in_millis": 240000
      },
      "search": {
        "query_total": 800000,
        "query_time_in_millis": 960000
      }
    },
    "total": {
      "docs": {
        "count": 102500000,
        "deleted": 851200
      }
    }
  }
}
```

### Interpretación

| Sección    | Uso                     |
| ---------- | ----------------------- |
| `docs`     | Número de documentos    |
| `store`    | Tamaño                  |
| `indexing` | Actividad de indexación |
| `search`   | Actividad de búsqueda   |
| `segments` | Segmentos Lucene        |
| `merges`   | Actividad de merges     |
| `refresh`  | Refreshes               |
| `flush`    | Flushes                 |
| `translog` | Translog                |

---

# 4. Shards y asignación

---

## 4.1 `GET /_cat/shards`

### Uso

Muestra la distribución de shards por índice y nodo.

Es esencial para detectar:

* shards no asignados;
* shards demasiado grandes;
* distribución desigual;
* hot shards;
* primarios y réplicas;
* shards en relocating o initializing.

### Endpoint

```http
GET /_cat/shards
```

### Ejemplo de envío

```http
GET /_cat/shards?v
```

### Ejemplo de salida

```text
index            shard prirep state   docs     store ip         node
logs-2026.06.08  0     p      STARTED 4000000  6gb   10.0.0.10 os-data-1
logs-2026.06.08  0     r      STARTED 4000000  6gb   10.0.0.11 os-data-2
logs-2026.06.08  1     p      STARTED 4100000  6.2gb 10.0.0.11 os-data-2
logs-2026.06.08  1     r      STARTED 4100000  6.2gb 10.0.0.12 os-data-3
logs-2026.06.08  2     p      STARTED 3900000  5.8gb 10.0.0.12 os-data-3
logs-2026.06.08  2     r      STARTED 3900000  5.8gb 10.0.0.10 os-data-1
```

### Interpretación

| Campo    | Significado               |
| -------- | ------------------------- |
| `index`  | Índice                    |
| `shard`  | Número de shard           |
| `prirep` | `p` primario, `r` réplica |
| `state`  | Estado del shard          |
| `docs`   | Documentos                |
| `store`  | Tamaño                    |
| `node`   | Nodo donde está asignado  |

---

## 4.2 `GET /_cat/shards` ordenado por tamaño

### Uso

Permite localizar los shards más grandes.

### Endpoint

```http
GET /_cat/shards?v&s=store:desc
```

### Ejemplo de envío

```http
GET /_cat/shards?v&s=store:desc
```

### Ejemplo de salida

```text
index          shard prirep state   docs      store node
metrics-2026   2     p      STARTED 35000000  45gb  os-data-2
metrics-2026   2     r      STARTED 35000000  45gb  os-data-1
logs-2026      1     p      STARTED 4100000   6.2gb os-data-2
logs-2026      1     r      STARTED 4100000   6.2gb os-data-3
```

### Lectura

Si un shard es muchísimo más grande que los demás del mismo índice, puede haber:

* routing desequilibrado;
* distribución irregular de datos;
* tenant muy grande;
* índice mal particionado;
* estrategia temporal inadecuada.

---

## 4.3 `GET /_cat/allocation`

### Uso

Muestra la distribución de shards y disco por nodo.

Sirve para detectar:

* nodos con más shards;
* nodos con más uso de disco;
* desequilibrio de almacenamiento;
* riesgos de watermarks;
* nodos candidatos a saturación.

### Endpoint

```http
GET /_cat/allocation
```

### Ejemplo de envío

```http
GET /_cat/allocation?v
```

### Ejemplo de salida

```text
shards disk.indices disk.used disk.avail disk.total disk.percent host      node
8      120gb        150gb     350gb      500gb      30           10.0.0.10 os-data-1
8      300gb        330gb     170gb      500gb      66           10.0.0.11 os-data-2
8      125gb        155gb     345gb      500gb      31           10.0.0.12 os-data-3
```

### Interpretación

Aunque los tres nodos tienen 8 shards, `os-data-2` tiene mucho más disco usado.

Esto puede indicar:

* shards más grandes;
* datos desbalanceados;
* routing desequilibrado;
* índices calientes;
* mala distribución histórica.

---

## 4.4 `GET /_cluster/allocation/explain`

### Uso

Explica por qué un shard se ha asignado, no se ha asignado o no puede moverse.

Es muy útil cuando hay shards en estado `UNASSIGNED`.

### Endpoint

```http
GET /_cluster/allocation/explain
```

### Ejemplo de envío

```http
GET /_cluster/allocation/explain
{
  "index": "logs-2026.06.08",
  "shard": 0,
  "primary": false
}
```

### Ejemplo de salida abreviada

```json
{
  "index": "logs-2026.06.08",
  "shard": 0,
  "primary": false,
  "current_state": "unassigned",
  "unassigned_info": {
    "reason": "NODE_LEFT",
    "at": "2026-06-08T10:10:00Z",
    "details": "node_left"
  },
  "can_allocate": "no",
  "allocate_explanation": "cannot allocate because allocation is not permitted to any of the nodes",
  "node_allocation_decisions": [
    {
      "node_name": "os-data-1",
      "node_decision": "no",
      "deciders": [
        {
          "decider": "disk_threshold",
          "decision": "NO",
          "explanation": "the node is above the high watermark"
        }
      ]
    }
  ]
}
```

### Interpretación

En este ejemplo, el shard no se puede asignar porque el nodo está por encima del umbral de disco.

---

# 5. JVM, heap y garbage collection

---

## 5.1 `GET /_nodes/stats/jvm`

### Uso

Devuelve estadísticas de JVM.

Sirve para analizar:

* heap usado;
* heap máximo;
* pools de memoria;
* garbage collection;
* pausas de GC;
* presión sostenida de memoria.

### Endpoint

```http
GET /_nodes/stats/jvm
```

### Ejemplo de envío

```http
GET /_nodes/stats/jvm?pretty
```

### Ejemplo de salida abreviada

```json
{
  "nodes": {
    "nodeId1": {
      "name": "os-data-1",
      "jvm": {
        "mem": {
          "heap_used_percent": 68,
          "heap_used_in_bytes": 11682311045,
          "heap_max_in_bytes": 17179869184,
          "non_heap_used_in_bytes": 245366784
        },
        "gc": {
          "collectors": {
            "young": {
              "collection_count": 3400,
              "collection_time_in_millis": 22000
            },
            "old": {
              "collection_count": 7,
              "collection_time_in_millis": 1800
            }
          }
        }
      }
    }
  }
}
```

### Interpretación

| Campo                             | Significado                |
| --------------------------------- | -------------------------- |
| `heap_used_percent`               | Porcentaje de heap usado   |
| `heap_used_in_bytes`              | Heap usado en bytes        |
| `heap_max_in_bytes`               | Heap máximo                |
| `young.collection_count`          | Número de GC young         |
| `young.collection_time_in_millis` | Tiempo dedicado a GC young |
| `old.collection_count`            | Número de GC old           |
| `old.collection_time_in_millis`   | Tiempo dedicado a GC old   |

### Señales de alarma

* heap alto sostenido;
* old GC frecuente;
* tiempo elevado en GC;
* heap que no baja tras GC;
* circuit breakers asociados;
* latencias coincidiendo con GC.

---

## 5.2 `GET /_cat/nodes` para heap

### Uso

Vista rápida del heap por nodo.

### Endpoint

```http
GET /_cat/nodes?v&h=name,heap.percent,ram.percent,cpu,load_1m,node.role
```

### Ejemplo de envío

```http
GET /_cat/nodes?v&h=name,heap.percent,ram.percent,cpu,load_1m,node.role
```

### Ejemplo de salida

```text
name      heap.percent ram.percent cpu load_1m node.role
os-data-1 42           71          18  1.20    dimr
os-data-2 83           86          77  4.80    dimr
os-data-3 39           68          22  1.40    dimr
```

### Lectura

`os-data-2` puede estar bajo presión de heap y CPU.

Conviene revisar:

* shards en ese nodo;
* búsquedas;
* indexación;
* agregaciones;
* cachés;
* breakers;
* routing.

---

# 6. Disco y filesystem

---

## 6.1 `GET /_nodes/stats/fs`

### Uso

Devuelve estadísticas del filesystem de los nodos.

Sirve para revisar:

* disco total;
* disco libre;
* disco disponible;
* uso de disco;
* posibles riesgos de watermarks.

### Endpoint

```http
GET /_nodes/stats/fs
```

### Ejemplo de envío

```http
GET /_nodes/stats/fs?pretty
```

### Ejemplo de salida abreviada

```json
{
  "nodes": {
    "nodeId1": {
      "name": "os-data-1",
      "fs": {
        "total": {
          "total_in_bytes": 536870912000,
          "free_in_bytes": 348966092800,
          "available_in_bytes": 348966092800
        }
      }
    }
  }
}
```

### Interpretación

| Campo                | Significado                        |
| -------------------- | ---------------------------------- |
| `total_in_bytes`     | Tamaño total del filesystem        |
| `free_in_bytes`      | Espacio libre                      |
| `available_in_bytes` | Espacio disponible para OpenSearch |

---

## 6.2 `GET /_cat/nodes` para disco

### Uso

Vista rápida del uso de disco por nodo.

### Endpoint

```http
GET /_cat/nodes?v&h=name,disk.used_percent,disk.avail,disk.total
```

### Ejemplo de envío

```http
GET /_cat/nodes?v&h=name,disk.used_percent,disk.avail,disk.total
```

### Ejemplo de salida

```text
name      disk.used_percent disk.avail disk.total
os-data-1 35                325gb      500gb
os-data-2 78                110gb      500gb
os-data-3 38                310gb      500gb
```

### Lectura

`os-data-2` tiene mucho más disco usado.

Conviene cruzar con:

```http
GET /_cat/allocation?v
GET /_cat/shards?v&s=store:desc
```

---

# 7. Thread pools, colas y rechazos

---

## 7.1 `GET /_cat/thread_pool`

### Uso

Muestra el estado de los thread pools.

Sirve para detectar:

* operaciones activas;
* colas;
* rechazos;
* saturación de búsqueda;
* saturación de escritura;
* problemas por nodo.

### Endpoint

```http
GET /_cat/thread_pool
```

### Ejemplo de envío

```http
GET /_cat/thread_pool?v
```

### Ejemplo de salida

```text
node_name name    active queue rejected completed
os-data-1 search  2      0     0        450000
os-data-2 search  13     48    35       470000
os-data-3 search  1      0     0        430000
os-data-1 write   1      0     0        250000
os-data-2 write   8      80    22       260000
os-data-3 write   2      0     0        245000
```

### Interpretación

| Campo       | Significado              |
| ----------- | ------------------------ |
| `active`    | Operaciones ejecutándose |
| `queue`     | Operaciones esperando    |
| `rejected`  | Operaciones rechazadas   |
| `completed` | Operaciones completadas  |

### Lectura

El nodo `os-data-2` tiene colas y rechazos tanto en `search` como en `write`.

Puede haber:

* nodo caliente;
* shard caliente;
* routing desequilibrado;
* disco lento;
* heap alto;
* demasiada concurrencia;
* consultas o bulk demasiado agresivos.

---

## 7.2 `GET /_cat/thread_pool/search`

### Uso

Muestra solo el pool de búsqueda.

### Endpoint

```http
GET /_cat/thread_pool/search
```

### Ejemplo de envío

```http
GET /_cat/thread_pool/search?v
```

### Ejemplo de salida

```text
node_name name   active queue rejected completed
os-data-1 search 2      0     0        450000
os-data-2 search 13     48    35       470000
os-data-3 search 1      0     0        430000
```

### Señales de alarma

* `queue` creciendo;
* `rejected` mayor que cero;
* un nodo con mucha más actividad que otros.

---

## 7.3 `GET /_cat/thread_pool/write`

### Uso

Muestra solo el pool de escritura.

### Endpoint

```http
GET /_cat/thread_pool/write
```

### Ejemplo de envío

```http
GET /_cat/thread_pool/write?v
```

### Ejemplo de salida

```text
node_name name  active queue rejected completed
os-data-1 write 1      0     0        250000
os-data-2 write 8      80    22       260000
os-data-3 write 2      0     0        245000
```

### Señales de alarma

* indexación saturada;
* bulk demasiado grande;
* demasiada concurrencia;
* disco lento;
* merges intensos;
* réplicas excesivas;
* ingest pipelines pesados.

---

## 7.4 `GET /_nodes/stats/thread_pool`

### Uso

Devuelve estadísticas detalladas de thread pools por nodo.

### Endpoint

```http
GET /_nodes/stats/thread_pool
```

### Ejemplo de envío

```http
GET /_nodes/stats/thread_pool?pretty
```

### Ejemplo de salida abreviada

```json
{
  "nodes": {
    "nodeId2": {
      "name": "os-data-2",
      "thread_pool": {
        "search": {
          "threads": 13,
          "queue": 48,
          "active": 13,
          "rejected": 35,
          "largest": 13,
          "completed": 470000
        },
        "write": {
          "threads": 8,
          "queue": 80,
          "active": 8,
          "rejected": 22,
          "largest": 8,
          "completed": 260000
        }
      }
    }
  }
}
```

---

# 8. Búsqueda

---

## 8.1 `GET /_nodes/stats/indices/search`

### Uso

Devuelve estadísticas de búsqueda por nodo.

Sirve para analizar:

* volumen de búsquedas;
* tiempo acumulado de búsqueda;
* búsquedas actualmente en ejecución;
* fase query;
* fase fetch;
* scrolls;
* presión de búsquedas.

### Endpoint

```http
GET /_nodes/stats/indices/search
```

### Ejemplo de envío

```http
GET /_nodes/stats/indices/search?pretty
```

### Ejemplo de salida abreviada

```json
{
  "nodes": {
    "nodeId1": {
      "name": "os-data-1",
      "indices": {
        "search": {
          "query_total": 800000,
          "query_time_in_millis": 960000,
          "query_current": 2,
          "fetch_total": 790000,
          "fetch_time_in_millis": 240000,
          "fetch_current": 1,
          "scroll_total": 1200,
          "scroll_time_in_millis": 45000,
          "scroll_current": 0
        }
      }
    }
  }
}
```

### Interpretación

| Campo                  | Significado                     |
| ---------------------- | ------------------------------- |
| `query_total`          | Total de fases query ejecutadas |
| `query_time_in_millis` | Tiempo acumulado en query       |
| `query_current`        | Queries en ejecución            |
| `fetch_total`          | Total de fases fetch            |
| `fetch_time_in_millis` | Tiempo acumulado en fetch       |
| `fetch_current`        | Fetches en ejecución            |
| `scroll_total`         | Scrolls ejecutados              |
| `scroll_current`       | Scrolls abiertos actualmente    |

### Cálculos orientativos

```text
latencia_media_query = query_time_in_millis / query_total
latencia_media_fetch = fetch_time_in_millis / fetch_total
```

### Advertencia

Estas medias son acumuladas. No sustituyen a percentiles, slow logs o profiling, pero sirven para una línea base inicial.

---

# 9. Indexación

---

## 9.1 `GET /_nodes/stats/indices/indexing`

### Uso

Devuelve estadísticas de indexación por nodo.

Sirve para analizar:

* volumen de documentos indexados;
* tiempo acumulado de indexación;
* operaciones actuales;
* fallos de indexación;
* presión de escritura.

### Endpoint

```http
GET /_nodes/stats/indices/indexing
```

### Ejemplo de envío

```http
GET /_nodes/stats/indices/indexing?pretty
```

### Ejemplo de salida abreviada

```json
{
  "nodes": {
    "nodeId1": {
      "name": "os-data-1",
      "indices": {
        "indexing": {
          "index_total": 5000000,
          "index_time_in_millis": 240000,
          "index_current": 3,
          "index_failed": 12,
          "delete_total": 150000,
          "delete_time_in_millis": 18000,
          "delete_current": 0,
          "noop_update_total": 500
        }
      }
    }
  }
}
```

### Interpretación

| Campo                   | Significado                |
| ----------------------- | -------------------------- |
| `index_total`           | Documentos indexados       |
| `index_time_in_millis`  | Tiempo acumulado indexando |
| `index_current`         | Indexaciones en curso      |
| `index_failed`          | Indexaciones fallidas      |
| `delete_total`          | Borrados                   |
| `delete_time_in_millis` | Tiempo acumulado borrando  |

### Señales de alarma

* `index_current` alto constantemente;
* `index_failed` creciendo;
* colas en `write`;
* rechazos en `write`;
* merges intensos;
* heap alto;
* disco saturado.

---

## 9.2 `GET /_nodes/stats` con indexing pressure

### Uso

Permite revisar presión relacionada con indexación.

### Endpoint

```http
GET /_nodes/stats?filter_path=nodes.*.indexing_pressure
```

### Ejemplo de envío

```http
GET /_nodes/stats?filter_path=nodes.*.indexing_pressure
```

### Ejemplo de salida orientativa

```json
{
  "nodes": {
    "nodeId1": {
      "indexing_pressure": {
        "memory": {
          "current": {
            "combined_coordinating_and_primary_in_bytes": 10485760,
            "coordinating_in_bytes": 2097152,
            "primary_in_bytes": 8388608,
            "replica_in_bytes": 0
          },
          "total": {
            "combined_coordinating_and_primary_in_bytes": 987654321,
            "coordinating_in_bytes": 123456789,
            "primary_in_bytes": 864197532,
            "replica_in_bytes": 456789123
          },
          "limit_in_bytes": 1717986918
        }
      }
    }
  }
}
```

### Interpretación

Ayuda a detectar si las operaciones de indexación están generando presión de memoria.

---

# 10. Segmentos y merges

---

## 10.1 `GET /_cat/segments`

### Uso

Muestra los segmentos Lucene por índice y shard.

Sirve para detectar:

* muchos segmentos;
* segmentos pequeños;
* índices con posible necesidad de revisión;
* actividad interna de Lucene.

### Endpoint

```http
GET /_cat/segments
```

### Ejemplo de envío

```http
GET /_cat/segments?v
```

### Ejemplo de salida

```text
index            shard prirep ip         segment generation docs.count docs.deleted size
logs-2026.06.08 0     p      10.0.0.10 _0      0          1000000    1000         1.5gb
logs-2026.06.08 0     p      10.0.0.10 _1      1          900000     500          1.2gb
logs-2026.06.08 1     p      10.0.0.11 _0      0          1200000    1500         1.8gb
```

### Interpretación

| Campo          | Significado               |
| -------------- | ------------------------- |
| `index`        | Índice                    |
| `shard`        | Shard                     |
| `prirep`       | Primario o réplica        |
| `segment`      | Nombre del segmento       |
| `docs.count`   | Documentos en el segmento |
| `docs.deleted` | Documentos borrados       |
| `size`         | Tamaño del segmento       |

---

## 10.2 `GET /<indice>/_segments`

### Uso

Muestra información detallada de segmentos de un índice concreto.

### Endpoint

```http
GET /<indice>/_segments
```

### Ejemplo de envío

```http
GET /logs-2026.06.08/_segments?pretty
```

### Ejemplo de salida abreviada

```json
{
  "indices": {
    "logs-2026.06.08": {
      "shards": {
        "0": [
          {
            "routing": {
              "state": "STARTED",
              "primary": true,
              "node": "nodeId1"
            },
            "segments": {
              "_0": {
                "generation": 0,
                "num_docs": 1000000,
                "deleted_docs": 1000,
                "size_in_bytes": 1610612736,
                "committed": true,
                "search": true
              }
            }
          }
        ]
      }
    }
  }
}
```

### Uso recomendado

Cuando un índice concreto parece problemático y se quiere observar su estructura interna de segmentos.

---

## 10.3 `GET /_nodes/stats/indices/segments,merges`

### Uso

Devuelve estadísticas de segmentos y merges por nodo.

Sirve para detectar:

* merges activos;
* tiempo acumulado en merges;
* bytes procesados;
* memoria asociada a segmentos;
* presión de disco o CPU por merges.

### Endpoint

```http
GET /_nodes/stats/indices/segments,merges
```

### Ejemplo de envío

```http
GET /_nodes/stats/indices/segments,merges?pretty
```

### Ejemplo de salida abreviada

```json
{
  "nodes": {
    "nodeId1": {
      "name": "os-data-1",
      "indices": {
        "segments": {
          "count": 245,
          "memory_in_bytes": 52428800,
          "terms_memory_in_bytes": 20971520,
          "stored_fields_memory_in_bytes": 10485760
        },
        "merges": {
          "current": 2,
          "current_docs": 300000,
          "current_size_in_bytes": 2147483648,
          "total": 1500,
          "total_time_in_millis": 980000,
          "total_docs": 90000000,
          "total_size_in_bytes": 536870912000
        }
      }
    }
  }
}
```

### Interpretación

| Campo                         | Significado                        |
| ----------------------------- | ---------------------------------- |
| `segments.count`              | Número de segmentos                |
| `segments.memory_in_bytes`    | Memoria usada por segmentos        |
| `merges.current`              | Merges activos                     |
| `merges.total`                | Total de merges ejecutados         |
| `merges.total_time_in_millis` | Tiempo acumulado de merges         |
| `merges.total_size_in_bytes`  | Volumen total procesado por merges |

---

# 11. Cachés

---

## 11.1 `GET /_nodes/stats/indices/query_cache`

### Uso

Devuelve estadísticas de query cache.

Sirve para analizar si los filtros reutilizables están aprovechando caché.

### Endpoint

```http
GET /_nodes/stats/indices/query_cache
```

### Ejemplo de envío

```http
GET /_nodes/stats/indices/query_cache?pretty
```

### Ejemplo de salida abreviada

```json
{
  "nodes": {
    "nodeId1": {
      "name": "os-data-1",
      "indices": {
        "query_cache": {
          "memory_size_in_bytes": 104857600,
          "total_count": 150000,
          "hit_count": 90000,
          "miss_count": 60000,
          "cache_size": 5000,
          "cache_count": 8000,
          "evictions": 3000
        }
      }
    }
  }
}
```

### Interpretación

| Campo                  | Significado          |
| ---------------------- | -------------------- |
| `memory_size_in_bytes` | Memoria usada        |
| `hit_count`            | Aciertos de caché    |
| `miss_count`           | Fallos de caché      |
| `evictions`            | Expulsiones de caché |
| `cache_size`           | Entradas actuales    |

### Señales de alarma

* muchas expulsiones;
* pocos aciertos;
* muchas consultas variables;
* filtros poco reutilizables.

---

## 11.2 `GET /_nodes/stats/indices/request_cache`

### Uso

Devuelve estadísticas de request cache.

Es especialmente útil para búsquedas analíticas y agregaciones repetidas.

### Endpoint

```http
GET /_nodes/stats/indices/request_cache
```

### Ejemplo de envío

```http
GET /_nodes/stats/indices/request_cache?pretty
```

### Ejemplo de salida abreviada

```json
{
  "nodes": {
    "nodeId1": {
      "name": "os-data-1",
      "indices": {
        "request_cache": {
          "memory_size_in_bytes": 52428800,
          "evictions": 120,
          "hit_count": 45000,
          "miss_count": 15000
        }
      }
    }
  }
}
```

### Interpretación

| Campo                  | Significado   |
| ---------------------- | ------------- |
| `memory_size_in_bytes` | Memoria usada |
| `hit_count`            | Aciertos      |
| `miss_count`           | Fallos        |
| `evictions`            | Expulsiones   |

---

## 11.3 `GET /_nodes/stats/indices/fielddata`

### Uso

Devuelve estadísticas de fielddata.

Es importante porque fielddata puede consumir heap.

### Endpoint

```http
GET /_nodes/stats/indices/fielddata
```

### Ejemplo de envío

```http
GET /_nodes/stats/indices/fielddata?pretty
```

### Ejemplo de salida abreviada

```json
{
  "nodes": {
    "nodeId2": {
      "name": "os-data-2",
      "indices": {
        "fielddata": {
          "memory_size_in_bytes": 314572800,
          "evictions": 25
        }
      }
    }
  }
}
```

### Interpretación

| Campo                  | Significado                      |
| ---------------------- | -------------------------------- |
| `memory_size_in_bytes` | Memoria heap usada por fielddata |
| `evictions`            | Expulsiones de fielddata         |

### Señales de alarma

* fielddata consumiendo mucha memoria;
* evictions;
* uso de campos `text` para agregaciones u ordenaciones;
* heap alto coincidiendo con fielddata.

---

## 11.4 Endpoint combinado de cachés

### Uso

Permite revisar las principales cachés en una sola llamada.

### Endpoint

```http
GET /_nodes/stats/indices/query_cache,request_cache,fielddata
```

### Ejemplo de envío

```http
GET /_nodes/stats/indices/query_cache,request_cache,fielddata?pretty
```

### Ejemplo de salida abreviada

```json
{
  "nodes": {
    "nodeId1": {
      "name": "os-data-1",
      "indices": {
        "query_cache": {
          "memory_size_in_bytes": 104857600,
          "hit_count": 90000,
          "miss_count": 60000,
          "evictions": 3000
        },
        "request_cache": {
          "memory_size_in_bytes": 52428800,
          "hit_count": 45000,
          "miss_count": 15000,
          "evictions": 120
        },
        "fielddata": {
          "memory_size_in_bytes": 314572800,
          "evictions": 25
        }
      }
    }
  }
}
```

---

# 12. Circuit breakers

---

## 12.1 `GET /_nodes/stats/breaker`

### Uso

Devuelve estadísticas de circuit breakers.

Los circuit breakers protegen al cluster de operaciones que podrían consumir demasiada memoria.

Sirve para detectar:

* consultas demasiado pesadas;
* agregaciones peligrosas;
* uso excesivo de fielddata;
* operaciones rechazadas por protección de memoria.

### Endpoint

```http
GET /_nodes/stats/breaker
```

### Ejemplo de envío

```http
GET /_nodes/stats/breaker?pretty
```

### Ejemplo de salida abreviada

```json
{
  "nodes": {
    "nodeId2": {
      "name": "os-data-2",
      "breakers": {
        "request": {
          "limit_size_in_bytes": 10307921510,
          "estimated_size_in_bytes": 2147483648,
          "overhead": 1.0,
          "tripped": 4
        },
        "fielddata": {
          "limit_size_in_bytes": 6871947673,
          "estimated_size_in_bytes": 314572800,
          "overhead": 1.03,
          "tripped": 2
        },
        "parent": {
          "limit_size_in_bytes": 12025908428,
          "estimated_size_in_bytes": 8589934592,
          "overhead": 1.0,
          "tripped": 1
        }
      }
    }
  }
}
```

### Interpretación

| Campo                     | Significado                     |
| ------------------------- | ------------------------------- |
| `limit_size_in_bytes`     | Límite del breaker              |
| `estimated_size_in_bytes` | Memoria estimada                |
| `overhead`                | Factor aplicado                 |
| `tripped`                 | Veces que el breaker ha saltado |

### Señales de alarma

* `tripped` creciendo;
* breaker de request saltando;
* breaker de fielddata saltando;
* parent breaker saltando;
* coincidencia con agregaciones o dashboards.

---

# 13. Routing

---

## 13.1 Indexar documento con routing explícito

### Uso

Permite indicar manualmente qué valor se usará para decidir el shard de destino.

Es útil en escenarios donde queremos que documentos de una misma entidad lógica caigan juntos.

Ejemplos:

* tenant;
* cliente;
* organización;
* cuenta;
* proyecto.

### Endpoint

```http
POST /<indice>/_doc/<id>?routing=<valor>
```

### Ejemplo de envío

```http
POST /orders/_doc/1?routing=C001
{
  "customer_id": "C001",
  "amount": 120,
  "status": "PAID"
}
```

### Ejemplo de salida

```json
{
  "_index": "orders",
  "_id": "1",
  "_version": 1,
  "result": "created",
  "_shards": {
    "total": 2,
    "successful": 2,
    "failed": 0
  },
  "_seq_no": 0,
  "_primary_term": 1
}
```

### Interpretación

El documento se ha indexado usando `C001` como valor de routing.

---

## 13.2 Buscar usando routing explícito

### Uso

Permite dirigir la búsqueda solo al shard asociado al valor de routing.

Puede reducir el fan-out de la búsqueda.

### Endpoint

```http
GET /<indice>/_search?routing=<valor>
```

### Ejemplo de envío

```http
GET /orders/_search?routing=C001
{
  "query": {
    "term": {
      "customer_id": "C001"
    }
  }
}
```

### Ejemplo de salida abreviada

```json
{
  "took": 12,
  "timed_out": false,
  "_shards": {
    "total": 1,
    "successful": 1,
    "skipped": 0,
    "failed": 0
  },
  "hits": {
    "total": {
      "value": 2,
      "relation": "eq"
    },
    "hits": [
      {
        "_index": "orders",
        "_id": "1",
        "_routing": "C001",
        "_source": {
          "customer_id": "C001",
          "amount": 120,
          "status": "PAID"
        }
      }
    ]
  }
}
```

### Lectura importante

Fíjate en:

```json
"_shards": {
  "total": 1
}
```

Eso indica que la búsqueda ha ido solo a un shard.

---

## 13.3 Buscar sin routing

### Uso

Consulta normal sin routing explícito.

OpenSearch debe consultar todos los shards relevantes del índice.

### Endpoint

```http
GET /<indice>/_search
```

### Ejemplo de envío

```http
GET /orders/_search
{
  "query": {
    "term": {
      "customer_id": "C001"
    }
  }
}
```

### Ejemplo de salida abreviada

```json
{
  "took": 35,
  "timed_out": false,
  "_shards": {
    "total": 3,
    "successful": 3,
    "skipped": 0,
    "failed": 0
  },
  "hits": {
    "total": {
      "value": 2,
      "relation": "eq"
    },
    "hits": []
  }
}
```

### Lectura importante

Fíjate en:

```json
"_shards": {
  "total": 3
}
```

La búsqueda se ha ejecutado sobre tres shards.

---

## 13.4 Recuperar documento con routing

### Uso

Si un documento fue indexado con routing explícito, normalmente hay que usar el mismo routing para recuperarlo por ID.

### Endpoint

```http
GET /<indice>/_doc/<id>?routing=<valor>
```

### Ejemplo de envío

```http
GET /orders/_doc/1?routing=C001
```

### Ejemplo de salida

```json
{
  "_index": "orders",
  "_id": "1",
  "_routing": "C001",
  "_version": 1,
  "found": true,
  "_source": {
    "customer_id": "C001",
    "amount": 120,
    "status": "PAID"
  }
}
```

---

## 13.5 Crear índice con routing obligatorio

### Uso

Obliga a que las operaciones de indexación indiquen un valor de routing.

Es útil cuando el diseño del índice depende del routing.

### Endpoint

```http
PUT /<indice>
```

### Ejemplo de envío

```http
PUT /orders-routing-required
{
  "settings": {
    "number_of_shards": 3,
    "number_of_replicas": 1
  },
  "mappings": {
    "_routing": {
      "required": true
    },
    "properties": {
      "customer_id": {
        "type": "keyword"
      },
      "amount": {
        "type": "double"
      },
      "status": {
        "type": "keyword"
      }
    }
  }
}
```

### Ejemplo de salida

```json
{
  "acknowledged": true,
  "shards_acknowledged": true,
  "index": "orders-routing-required"
}
```

### Ejemplo de error al indexar sin routing

```http
POST /orders-routing-required/_doc/1
{
  "customer_id": "C001",
  "amount": 120,
  "status": "PAID"
}
```

Salida orientativa:

```json
{
  "error": {
    "type": "routing_missing_exception",
    "reason": "routing is required for [orders-routing-required]/[_doc]/[1]"
  },
  "status": 400
}
```

---

# 14. Ejemplos de búsqueda e indexación utilizados en clase

---

## 14.1 Búsqueda simple

### Uso

Ejemplo básico para explicar el flujo interno de búsqueda.

### Endpoint

```http
GET /<indice>/_search
```

### Ejemplo de envío

```http
GET /logs/_search
{
  "query": {
    "match": {
      "message": "timeout"
    }
  }
}
```

### Ejemplo de salida abreviada

```json
{
  "took": 18,
  "timed_out": false,
  "_shards": {
    "total": 3,
    "successful": 3,
    "skipped": 0,
    "failed": 0
  },
  "hits": {
    "total": {
      "value": 152,
      "relation": "eq"
    },
    "hits": [
      {
        "_index": "logs",
        "_id": "abc123",
        "_score": 1.42,
        "_source": {
          "message": "timeout connecting to database",
          "service": "billing",
          "level": "ERROR"
        }
      }
    ]
  }
}
```

---

## 14.2 Búsqueda con filtro

### Uso

Ejemplo para explicar filtros, cachés y queries más operativas.

### Endpoint

```http
GET /<indice>/_search
```

### Ejemplo de envío

```http
GET /logs/_search
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "service": "billing"
          }
        },
        {
          "range": {
            "@timestamp": {
              "gte": "now-1h"
            }
          }
        }
      ]
    }
  }
}
```

### Ejemplo de salida abreviada

```json
{
  "took": 25,
  "_shards": {
    "total": 3,
    "successful": 3,
    "failed": 0
  },
  "hits": {
    "total": {
      "value": 2350,
      "relation": "eq"
    },
    "hits": []
  }
}
```

---

## 14.3 Agregación simple

### Uso

Ejemplo para explicar carga analítica, request cache y consumo potencial de memoria.

### Endpoint

```http
GET /<indice>/_search
```

### Ejemplo de envío

```http
GET /logs/_search
{
  "size": 0,
  "aggs": {
    "por_servicio": {
      "terms": {
        "field": "service.keyword"
      }
    }
  }
}
```

### Ejemplo de salida abreviada

```json
{
  "took": 42,
  "timed_out": false,
  "_shards": {
    "total": 3,
    "successful": 3,
    "failed": 0
  },
  "hits": {
    "total": {
      "value": 1200000,
      "relation": "eq"
    }
  },
  "aggregations": {
    "por_servicio": {
      "buckets": [
        {
          "key": "billing",
          "doc_count": 350000
        },
        {
          "key": "checkout",
          "doc_count": 220000
        }
      ]
    }
  }
}
```

---

## 14.4 Agregación potencialmente costosa

### Uso

Ejemplo para explicar riesgo de agregaciones de alta cardinalidad.

### Endpoint

```http
GET /<indice>/_search
```

### Ejemplo de envío

```http
GET /logs/_search
{
  "size": 0,
  "aggs": {
    "por_usuario": {
      "terms": {
        "field": "user_id",
        "size": 100000
      }
    }
  }
}
```

### Posible salida de error orientativa

```json
{
  "error": {
    "type": "circuit_breaking_exception",
    "reason": "Data too large, data for [<request>] would be larger than limit",
    "bytes_wanted": 12500000000,
    "bytes_limit": 10300000000
  },
  "status": 429
}
```

### Lectura

La query intenta construir demasiados buckets y puede superar límites de memoria.

---

## 14.5 Indexación simple

### Uso

Ejemplo para explicar el flujo interno de indexación.

### Endpoint

```http
POST /<indice>/_doc
```

### Ejemplo de envío

```http
POST /logs/_doc
{
  "@timestamp": "2026-06-08T10:00:00Z",
  "service": "billing",
  "level": "ERROR",
  "message": "timeout connecting to database"
}
```

### Ejemplo de salida

```json
{
  "_index": "logs",
  "_id": "lW0fT5cB8XK9",
  "_version": 1,
  "result": "created",
  "_shards": {
    "total": 2,
    "successful": 2,
    "failed": 0
  },
  "_seq_no": 100,
  "_primary_term": 1
}
```

---

## 14.6 Bulk indexing

### Uso

Ejemplo para explicar indexación masiva.

### Endpoint

```http
POST /_bulk
```

### Ejemplo de envío

```http
POST /_bulk
{ "index": { "_index": "logs", "_id": "1" } }
{ "@timestamp": "2026-06-08T10:00:00Z", "message": "error 1", "service": "billing" }
{ "index": { "_index": "logs", "_id": "2" } }
{ "@timestamp": "2026-06-08T10:00:01Z", "message": "error 2", "service": "checkout" }
```

### Ejemplo de salida abreviada

```json
{
  "took": 35,
  "errors": false,
  "items": [
    {
      "index": {
        "_index": "logs",
        "_id": "1",
        "status": 201,
        "result": "created"
      }
    },
    {
      "index": {
        "_index": "logs",
        "_id": "2",
        "status": 201,
        "result": "created"
      }
    }
  ]
}
```

### Señales a vigilar

Después de lanzar carga bulk, revisar:

```http
GET /_cat/thread_pool/write?v
GET /_nodes/stats/indices/indexing?pretty
GET /_nodes/stats/indices/segments,merges?pretty
GET /_nodes/stats/jvm?pretty
```

---

# 15. Settings del cluster

---

## 15.1 `GET /_cluster/settings`

### Uso

Permite revisar settings dinámicos del cluster.

Es útil para línea base y troubleshooting.

### Endpoint

```http
GET /_cluster/settings
```

### Ejemplo de envío

```http
GET /_cluster/settings?include_defaults=true&pretty
```

### Ejemplo de salida abreviada

```json
{
  "persistent": {
    "cluster": {
      "routing": {
        "allocation": {
          "disk": {
            "watermark": {
              "low": "85%",
              "high": "90%",
              "flood_stage": "95%"
            }
          }
        }
      }
    }
  },
  "transient": {},
  "defaults": {
    "cluster": {
      "routing": {
        "allocation": {
          "enable": "all"
        }
      }
    }
  }
}
```

### Interpretación

Sirve para revisar:

* watermarks;
* reglas de asignación;
* settings persistentes;
* settings transitorios;
* defaults efectivos.

---

# 16. Resumen rápido por categoría

---

## 16.1 Cluster

| Endpoint                                              | Uso                             |
| ----------------------------------------------------- | ------------------------------- |
| `GET /_cluster/health?pretty`                         | Estado general del cluster      |
| `GET /_cat/health?v`                                  | Estado general en formato tabla |
| `GET /_cluster/pending_tasks?pretty`                  | Tareas pendientes               |
| `GET /_cluster/settings?include_defaults=true&pretty` | Settings efectivos del cluster  |

---

## 16.2 Nodos

| Endpoint                                                                                              | Uso                                 |
| ----------------------------------------------------------------------------------------------------- | ----------------------------------- |
| `GET /_cat/nodes?v`                                                                                   | Vista rápida de nodos               |
| `GET /_cat/nodes?v&h=name,ip,node.role,master,heap.percent,ram.percent,cpu,load_1m,disk.used_percent` | Vista personalizada                 |
| `GET /_nodes/stats?pretty`                                                                            | Estadísticas completas              |
| `GET /_nodes/stats/os,jvm,fs,process,thread_pool?pretty`                                              | Estadísticas operativas principales |

---

## 16.3 Índices

| Endpoint                                | Uso                               |
| --------------------------------------- | --------------------------------- |
| `GET /_cat/indices?v`                   | Vista general de índices          |
| `GET /_cat/indices?v&s=store.size:desc` | Índices ordenados por tamaño      |
| `GET /_stats?pretty`                    | Estadísticas completas de índices |

---

## 16.4 Shards

| Endpoint                           | Uso                         |
| ---------------------------------- | --------------------------- |
| `GET /_cat/shards?v`               | Vista general de shards     |
| `GET /_cat/shards?v&s=store:desc`  | Shards ordenados por tamaño |
| `GET /_cat/allocation?v`           | Distribución por nodo       |
| `GET /_cluster/allocation/explain` | Diagnóstico de asignación   |

---

## 16.5 JVM y disco

| Endpoint                                                           | Uso                       |
| ------------------------------------------------------------------ | ------------------------- |
| `GET /_nodes/stats/jvm?pretty`                                     | Heap y garbage collection |
| `GET /_nodes/stats/fs?pretty`                                      | Filesystem y disco        |
| `GET /_cat/nodes?v&h=name,disk.used_percent,disk.avail,disk.total` | Disco por nodo            |

---

## 16.6 Thread pools

| Endpoint                               | Uso                              |
| -------------------------------------- | -------------------------------- |
| `GET /_cat/thread_pool?v`              | Thread pools en formato tabla    |
| `GET /_cat/thread_pool/search?v`       | Pool de búsqueda                 |
| `GET /_cat/thread_pool/write?v`        | Pool de escritura                |
| `GET /_nodes/stats/thread_pool?pretty` | Estadísticas detalladas de pools |

---

## 16.7 Búsqueda e indexación

| Endpoint                                    | Uso                        |
| ------------------------------------------- | -------------------------- |
| `GET /_nodes/stats/indices/search?pretty`   | Estadísticas de búsqueda   |
| `GET /_nodes/stats/indices/indexing?pretty` | Estadísticas de indexación |
| `POST /<indice>/_doc`                       | Indexación simple          |
| `POST /_bulk`                               | Indexación masiva          |
| `GET /<indice>/_search`                     | Búsqueda                   |
| `GET /<indice>/_search?routing=<valor>`     | Búsqueda con routing       |

---

## 16.8 Segmentos, merges y cachés

| Endpoint                                                               | Uso                        |
| ---------------------------------------------------------------------- | -------------------------- |
| `GET /_cat/segments?v`                                                 | Segmentos en formato tabla |
| `GET /<indice>/_segments?pretty`                                       | Segmentos de un índice     |
| `GET /_nodes/stats/indices/segments,merges?pretty`                     | Segmentos y merges         |
| `GET /_nodes/stats/indices/query_cache?pretty`                         | Query cache                |
| `GET /_nodes/stats/indices/request_cache?pretty`                       | Request cache              |
| `GET /_nodes/stats/indices/fielddata?pretty`                           | Fielddata                  |
| `GET /_nodes/stats/indices/query_cache,request_cache,fielddata?pretty` | Cachés principales         |

---

## 16.9 Breakers e indexing pressure

| Endpoint                                                  | Uso                   |
| --------------------------------------------------------- | --------------------- |
| `GET /_nodes/stats/breaker?pretty`                        | Circuit breakers      |
| `GET /_nodes/stats?filter_path=nodes.*.indexing_pressure` | Presión de indexación |

---

## 16.10 Routing

| Endpoint                                   | Uso                                       |
| ------------------------------------------ | ----------------------------------------- |
| `POST /<indice>/_doc/<id>?routing=<valor>` | Indexar con routing explícito             |
| `GET /<indice>/_doc/<id>?routing=<valor>`  | Recuperar documento con routing           |
| `GET /<indice>/_search?routing=<valor>`    | Buscar usando routing                     |
| `PUT /<indice>` con `_routing.required`    | Crear índice que obliga a indicar routing |

---

# 17. Orden recomendado para una primera radiografía

---

## Paso 1: salud general

```http
GET /_cluster/health?pretty
GET /_cat/health?v
```

## Paso 2: nodos

```http
GET /_cat/nodes?v
GET /_cat/nodes?v&h=name,ip,node.role,master,heap.percent,ram.percent,cpu,load_1m,disk.used_percent
```

## Paso 3: índices

```http
GET /_cat/indices?v&s=store.size:desc
```

## Paso 4: shards

```http
GET /_cat/shards?v&s=store:desc
GET /_cat/allocation?v
```

## Paso 5: JVM y disco

```http
GET /_nodes/stats/jvm?pretty
GET /_nodes/stats/fs?pretty
```

## Paso 6: thread pools

```http
GET /_cat/thread_pool/search?v
GET /_cat/thread_pool/write?v
```

## Paso 7: búsqueda e indexación

```http
GET /_nodes/stats/indices/search?pretty
GET /_nodes/stats/indices/indexing?pretty
```

## Paso 8: segmentos y merges

```http
GET /_nodes/stats/indices/segments,merges?pretty
```

## Paso 9: cachés y breakers

```http
GET /_nodes/stats/indices/query_cache,request_cache,fielddata?pretty
GET /_nodes/stats/breaker?pretty
```

## Paso 10: hipótesis

Con los datos anteriores, formular una hipótesis:

```text
Síntoma observado:
Nodo afectado:
Índice afectado:
Shard afectado:
Métrica anómala:
Posible causa:
Siguiente endpoint a revisar:
```

---

# 18. Plantilla mínima de línea base usando endpoints

---

````markdown
# Línea base OpenSearch

## Cluster

Endpoint usado:

```http
GET /_cluster/health?pretty
````

Resultado resumido:

* Estado:
* Nodos:
* Data nodes:
* Shards activos:
* Shards no asignados:
* Pending tasks:

---

## Nodos

Endpoint usado:

```http
GET /_cat/nodes?v&h=name,ip,node.role,master,heap.percent,ram.percent,cpu,load_1m,disk.used_percent
```

Resultado:

| Nodo | Roles | Master | Heap % | RAM % | CPU | Load 1m | Disco % |
| ---- | ----- | ------ | -----: | ----: | --: | ------: | ------: |
|      |       |        |        |       |     |         |         |

---

## Índices

Endpoint usado:

```http
GET /_cat/indices?v&s=store.size:desc
```

Resultado:

| Índice | Health | Primarios | Réplicas | Docs | Tamaño |
| ------ | ------ | --------: | -------: | ---: | -----: |
|        |        |           |          |      |        |

---

## Shards

Endpoint usado:

```http
GET /_cat/shards?v&s=store:desc
```

Resultado:

| Índice | Shard | P/R | Estado | Docs | Tamaño | Nodo |
| ------ | ----: | --- | ------ | ---: | -----: | ---- |
|        |       |     |        |      |        |      |

---

## Thread pools

Endpoints usados:

```http
GET /_cat/thread_pool/search?v
GET /_cat/thread_pool/write?v
```

Resultado:

| Nodo | Pool | Active | Queue | Rejected |
| ---- | ---- | -----: | ----: | -------: |
|      |      |        |       |          |

---

## JVM

Endpoint usado:

```http
GET /_nodes/stats/jvm?pretty
```

Resultado:

* Nodo con mayor heap:
* Heap máximo:
* Young GC:
* Old GC:
* Observaciones:

---

## Disco

Endpoint usado:

```http
GET /_cat/allocation?v
```

Resultado:

* Nodo con mayor disco:
* Nodo con menor espacio libre:
* ¿Hay desequilibrio?:
* Observaciones:

---

## Búsqueda

Endpoint usado:

```http
GET /_nodes/stats/indices/search?pretty
```

Resultado:

* query_total:
* query_time_in_millis:
* query_current:
* fetch_total:
* fetch_time_in_millis:
* fetch_current:

---

## Indexación

Endpoint usado:

```http
GET /_nodes/stats/indices/indexing?pretty
```

Resultado:

* index_total:
* index_time_in_millis:
* index_current:
* index_failed:

---

## Segmentos y merges

Endpoint usado:

```http
GET /_nodes/stats/indices/segments,merges?pretty
```

Resultado:

* Número de segmentos:
* Merges activos:
* Tiempo de merges:
* Observaciones:

---

## Cachés

Endpoint usado:

```http
GET /_nodes/stats/indices/query_cache,request_cache,fielddata?pretty
```

Resultado:

* Query cache hits:
* Query cache misses:
* Query cache evictions:
* Request cache hits:
* Request cache misses:
* Fielddata memory:
* Fielddata evictions:

---

## Breakers

Endpoint usado:

```http
GET /_nodes/stats/breaker?pretty
```

Resultado:

* Breakers con trips:
* Nodo afectado:
* Observaciones:

---

## Hipótesis inicial

* Síntoma:
* Métrica anómala:
* Posible causa:
* Siguiente comprobación:

