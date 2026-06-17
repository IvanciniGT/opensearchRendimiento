# Lab: Merges y merge policies (punto 5)

En clase se habló de los **merges** (Lucene consolida segmentos pequeños en otros
más grandes) y del `forcemerge`. Aquí se cierra el tema con la **merge policy** y
sus parámetros de tuning. Recordatorio de fundamentos (dia1): más segmentos y más
fragmentación = más disco, más tiempo de carga de índice y más RAM.

> Mejor en **oslab**. Variables `OS_URL`/`OS_AUTH`/`osq()` como en los otros labs.

---

## 1. Ver la fragmentación actual (segmentos por shard)

```bash
osq "/lab_content/_cat/segments?v&h=shard,prirep,segment,docs.count,docs.deleted,size,size.memory"
# resumen de merges/segmentos del índice
osq "/lab_content/_stats/segments,merges?filter_path=_all.primaries.segments.count,_all.primaries.merges"
```

Mirar: `segments.count` (cuántos segmentos), `docs.deleted` (borrados que aún
ocupan), `merges.current` (merges en curso), `merges.total_throttled_time` (si
Lucene está frenando merges por IO).

---

## 2. Merge policy: qué se puede tunear

OpenSearch usa por defecto la `tiered` merge policy. Parámetros (dinámicos, por índice):

```bash
osq "/lab_content/_settings" -X PUT -H 'Content-Type: application/json' -d '{
  "index.merge.policy.max_merged_segment": "2gb",
  "index.merge.policy.segments_per_tier": 10,
  "index.merge.policy.floor_segment": "2mb",
  "index.merge.policy.max_merge_at_once": 10
}'

# throttling de IO de los merges (clave cuando el disco es el cuello: ver el caso NFS)
osq "/_cluster/settings" -X PUT -H 'Content-Type: application/json' -d '{
  "persistent": { "indices.merge.scheduler.max_thread_count": 1 }
}'
```

- `max_merged_segment` (def 5gb): tope de tamaño de un segmento fruto de merge.
  Bajarlo = segmentos más pequeños (más merges pero más baratos); subirlo = menos
  segmentos grandes (mejor para lectura, merges más caros).
- `segments_per_tier` (def 10): cuántos segmentos por "nivel" antes de fusionar.
  Más alto = menos merges (mejor ingesta), pero más segmentos (peor búsqueda).
- `floor_segment` (def 2mb): por debajo de esto, se tratan como un único tamaño.
- `max_thread_count` del scheduler: en disco rotacional / **NFS** conviene **1**
  (los merges son IO secuencial y muchos hilos compiten por el mismo disco).
  En SSD/NVMe se puede subir.

> Conexión con el caso real: el cuello de la ingesta resultó ser la **concurrencia
> del cliente**, no el cluster (ver `analisis_ingesta_shards.md`). Aun así, cuando
> SÍ se satura el disco en una carga masiva real, bajar el ritmo de merges (menos
> hilos, `segments_per_tier` alto) reduce la presión sobre el disco; luego se
> consolida con `forcemerge`.

---

## 3. forcemerge: consolidar (solo índices que YA no se escriben)

```bash
# ANTES: contar segmentos
osq "/lab_content/_cat/segments?v&h=shard,prirep,segment,docs.count,docs.deleted" | wc -l

# Consolidar a 1 segmento por shard (CARO: relee y reescribe todo el shard).
# Reabsorbe los docs borrados y baja RAM/disco. NUNCA en índices con escritura activa.
osq "/lab_content/_forcemerge?max_num_segments=1"

# DESPUES: comprobar la mejora (menos segmentos, docs.deleted=0)
osq "/lab_content/_stats/segments?filter_path=_all.primaries.segments.count,_all.primaries.docs"
```

`only_expunge_deletes=true` es una variante más barata: solo limpia segmentos con
muchos borrados, sin reescribirlo todo.

```bash
osq "/lab_content/_forcemerge?only_expunge_deletes=true"
```

---

## 4. Comprobación de la efectividad (metodología del curso)

Patrón **antes/después** (igual que en `practica_rendimiento_tuning.md`):
1. Medir `segments.count`, `store.size`, `docs.deleted` y un `took` de búsqueda.
2. Aplicar `forcemerge` (o el cambio de policy + recarga).
3. Volver a medir: menos segmentos → menos RAM de page cache, carga de shard más
   rápida, y normalmente `took` algo menor en búsquedas que tocan muchos segmentos.

> Recordatorio dia4: en este entorno con poca RAM, índices/shards pequeños
> (~0.5-1 GB) + forcemerge cuando el índice se cierra = mejor uso del filesystem cache.
