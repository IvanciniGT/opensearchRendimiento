# Lab: ISM y rollover — ciclo de vida de índices (punto 6)

`opensearch-index-management` (ISM) ya está instalado. Permite **automatizar** lo
que en clase se ha hecho a mano (rotar índices por tamaño/edad, mover a tiers,
forzar merge, borrar viejos). Es el "mantenimiento reproducible" del punto 6.

> Mejor en **oslab** (efímero). Variables: `OS_URL`, `OS_AUTH`, `osq()` como en
> `lab_slowlogs_alerting.md`.

Conceptos:
- **Política ISM**: lista de **estados** (hot, warm, delete...) con **acciones**
  (rollover, force_merge, replica_count, delete...) y **transiciones** (cuándo
  pasar de un estado a otro: por edad, tamaño, nº de docs).
- **Rollover**: cuando el índice "vivo" (apuntado por un alias de escritura)
  supera un límite (tamaño/edad/docs), se crea uno nuevo y el alias salta a él.
  Es la forma correcta de rotar logs (en vez de un índice por mes a mano).

---

## 1. Política ISM con rollover + ciclo hot → delete

```bash
osq "/_plugins/_ism/policies/logs-policy" -X PUT -H 'Content-Type: application/json' -d '{
  "policy": {
    "description": "Rollover por tamano/edad y borrado a los 7 dias",
    "default_state": "hot",
    "states": [
      {
        "name": "hot",
        "actions": [
          { "rollover": { "min_size": "5gb", "min_index_age": "1d", "min_doc_count": 5000000 } }
        ],
        "transitions": [ { "state_name": "delete", "conditions": { "min_index_age": "7d" } } ]
      },
      {
        "name": "delete",
        "actions": [ { "delete": {} } ],
        "transitions": []
      }
    ],
    "ism_template": [ { "index_patterns": ["logs-*"], "priority": 100 } ]
  }
}'
```

`ism_template` hace que la política se aplique **automáticamente** a todo índice
nuevo que case `logs-*`. (Antes se hacía con un `index_template`.)

---

## 2. Índice "vivo" con alias de escritura (lo que exige el rollover)

```bash
# 1) plantilla con el alias de escritura is_write_index
osq "/_index_template/logs-template" -X PUT -H 'Content-Type: application/json' -d '{
  "index_patterns": ["logs-*"],
  "template": {
    "settings": { "number_of_shards": 3, "number_of_replicas": 1 },
    "aliases": { "logs": {} }
  }
}'

# 2) primer índice con sufijo numerico y marcado como write index del alias
osq "/logs-000001" -X PUT -H 'Content-Type: application/json' -d '{
  "aliases": { "logs": { "is_write_index": true } }
}'

# 3) escribir SIEMPRE por el alias (nunca por el nombre del indice)
osq "/logs/_doc" -H 'Content-Type: application/json' -d '{"@timestamp":"2026-06-17T10:00:00Z","msg":"hola"}'
```

Cuando `logs-000001` cumpla las condiciones (`min_size`/`min_age`/`min_doc_count`),
ISM crea `logs-000002`, le pasa el `is_write_index` y sigue. El alias `logs`
siempre apunta al vivo para escritura y a todos para lectura.

> Para una demo rápida en clase, baja los umbrales (`"min_doc_count": 5`,
> `"min_index_age": "5m"`) y mete unos pocos docs; verás aparecer `logs-000002`.

---

## 3. Ver el estado ISM de los índices

```bash
# estado/acción ISM actual por índice
osq "/_plugins/_ism/explain/logs-*?pretty"

# forzar la ejecución del job ISM sin esperar (acelerar la demo)
# osq "/_plugins/_ism/retry/logs-000001" -X POST   # si quedó en failed
```

En **Dashboards → Index Management → Policies / Indices** se ve todo esto visual:
políticas, a qué índice aplican, en qué estado están y la próxima transición.

---

## 4. Relación con lo visto en clase

- Sustituye al "un índice por mes creado a mano" (dia2/dia3): el rollover rota por
  tamaño real (5 GB, como recomienda dia4) en vez de por calendario.
- La acción `force_merge` dentro de un estado "warm" enlaza con
  `lab_merge_policies.md` (consolidar segmentos en índices que ya no se escriben).
- La acción `replica_count` permite el patrón dia4: índice caliente con 1 réplica,
  al enfriarse subir/bajar réplicas según consulta.

## 5. Limpieza

```bash
osq "/logs-*" -X DELETE
osq "/_index_template/logs-template" -X DELETE
osq "/_plugins/_ism/policies/logs-policy" -X DELETE
```
