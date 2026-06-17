# Lab: Observability, Prometheus/Grafana y dashboards operativos (punto 7)

Cubre la **monitorización visual**. La integración Prometheus/Grafana ya está
montada y mostrada en clase; aquí se documenta para que quede reproducible, más
el plugin **Observability** de Dashboards y los **dashboards operativos** que
conviene tener.

> Plugins implicados (ya instalados): `prometheus-exporter`, `opensearch-observability`.
> El cluster del operador tiene `monitoring.enable: true` → genera un
> **ServiceMonitor** que tu Prometheus (namespace `monitoring`) recoge.

---

## 1. Métricas Prometheus desde OpenSearch

El plugin `prometheus-exporter` expone un endpoint en formato Prometheus:

```bash
# texto plano estilo exporter (cientos de métricas: jvm, indices, thread_pool, fs, breakers...)
osq "/_prometheus/metrics" | head -40
```

Métricas clave para los paneles (nombres `opensearch_*`):
- `opensearch_jvm_mem_heap_used_percent` — heap por nodo (vigilar GC).
- `opensearch_os_mem_used_percent` — RAM del SO (page cache; alto = bueno).
- `opensearch_indices_search_query_time_seconds` / `_query_total` — latencia/throughput búsqueda.
- `opensearch_indices_indexing_index_total` / `_index_time_seconds` — ritmo de indexación.
- `opensearch_threadpool_threads_count{name="write"|"search"}`, `_queue`, `_rejected` — saturación de colas.
- `opensearch_circuitbreaker_tripped_count` — breakers disparados.
- `opensearch_fs_total_available_bytes` — disco libre (watermarks).
- `opensearch_cluster_status` — 0/1/2 = green/yellow/red.

### Cómo lo recoge Prometheus (operador)

El CR tiene:
```yaml
spec:
  general:
    monitoring:
      enable: true
      scrapeInterval: "30s"
      monitoringUserSecret: opensearch-admin-credentials
      labels: { release: monitoring }   # para que tu Prometheus lo seleccione
```
Esto crea un `ServiceMonitor` (CRD del Prometheus Operator). Comprobar:
```bash
kubectl get servicemonitor -A | grep -i opensearch
```

---

## 2. Dashboards operativos recomendados (Grafana)

Paneles mínimos para operación (los que enseñas):
1. **Salud del cluster**: `opensearch_cluster_status`, nodos activos, shards
   unassigned/initializing/relocating.
2. **Heap & GC** por nodo: `heap_used_percent`, tiempo/recuento de GC (old gen).
   Leer como en dia5: el mínimo en reposo = lo cacheado; picos entre GC = normal.
3. **RAM del SO / page cache**: `os_mem_used_percent` ~100% = sano.
4. **Búsqueda**: req/s y latencia media (rate de `query_total` y `query_time`).
5. **Indexación**: docs/s (rate de `index_total`) y latencia.
6. **Thread pools**: `write`/`search` queue y **rejected** (la señal de saturación
   del caso de la práctica: rejected > 0 = estás metiendo más de lo que absorbe).
7. **Disco**: `fs_available_bytes` y % usado (watermarks 85/90/95).
8. **Circuit breakers**: tripped (parent/fielddata/request).

> Hay dashboards de Grafana ya hechos para OpenSearch (Grafana.com dashboard
> "OpenSearch" / por el exporter). Sirven de base; ajustar a estas métricas.

---

## 3. Observability en OpenSearch Dashboards

El plugin `opensearch-observability` (UI incluida en la imagen estándar) está en
el **menú lateral izquierdo → Observability**. Secciones:
- **Notebooks**: cuadernos mezclando texto + visualizaciones + PPL/consultas
  (ideal para post-mortems de incidentes y para esta misma formación).
- **Logs / Discover**: explorar índices de logs con **PPL** (Piped Processing
  Language), p.ej. `source=logs-* | stats count() by level`.
- **Traces / Services**: APM (trazas distribuidas) si se ingieren con Data
  Prepper/OTel — fuera del alcance del lab, pero es donde vive.
- **Metrics**: visualización de métricas (incluidas las de Prometheus si se
  configura la fuente).

> Para clase, lo más rentable es: (a) enseñar que existe el menú, (b) crear un
> **Notebook** de Observability con 2-3 visualizaciones del índice de lab, y (c)
> una consulta **PPL** en Discover. Es "monitorización visual" sin salir de OS.

---

## 4. Dónde encaja cada herramienta (resumen para contar)

| Necesidad | Herramienta |
| --- | --- |
| Operación 24/7, alarmas, histórico de métricas | **Prometheus + Grafana** (fuera de OS) |
| Explorar datos/logs ad-hoc, PPL, post-mortems | **Observability (Dashboards)** |
| Avisos automáticos (umbral/anomalía) | **Alerting + Anomaly Detection** (`lab_slowlogs_alerting.md`) |
| Top queries lentas | **Query Insights** |

La regla del curso (dia4): los dashboards de **operación** necesitan casi tiempo
real (Grafana/Prometheus); los de **BI** no (mejor Postgres/herramienta BI, más
barata que tirar de OpenSearch para agregados históricos).
