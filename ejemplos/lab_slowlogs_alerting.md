# Lab: Slow logs, Alerting y Anomaly Detection (punto 8 del temario)

Cuaderno reproducible (terminal + Dev Tools) para **logging de consultas lentas,
alertas y detección de anomalías**. Todos los plugins necesarios YA están
instalados en el cluster (ver `temario_pendiente_y_plugins.md`): `opensearch-alerting`,
`opensearch-notifications`, `opensearch-anomaly-detection`, `query-insights`.

> Recomendado ejecutarlo contra el cluster de laboratorio efímero **oslab**
> (`k8s/oslab-cluster.yaml`) para no ensuciar el real. Ajusta las variables:
>
> ```bash
> export OS_URL='https://oslab.opensearch-lab:9200'   # o el del curso
> export OS_AUTH='admin:Pa$$w0rd2026'
> osq() { curl -s -k -u "$OS_AUTH" "$OS_URL$1" "${@:2}"; }
> ```

---

## 1. Slow logs de BÚSQUEDA e INDEXACIÓN

OpenSearch puede registrar en el log del nodo cualquier query/indexación que
supere un umbral. Se configura **por índice** y es dinámico (no reinicia nada).
Hay 4 niveles (warn/info/debug/trace) con su propio umbral; el log sale por la
fase `query` y la fase `fetch`.

```bash
# Activar slow log de BÚSQUEDA en un índice (umbrales de ejemplo, bajos para verlo)
osq "/lab_content/_settings" -X PUT -H 'Content-Type: application/json' -d '{
  "index.search.slowlog.threshold.query.warn":  "1s",
  "index.search.slowlog.threshold.query.info":  "500ms",
  "index.search.slowlog.threshold.query.debug": "200ms",
  "index.search.slowlog.threshold.fetch.warn":  "1s",
  "index.search.slowlog.threshold.fetch.info":  "500ms"
}'

# Activar slow log de INDEXACIÓN (además puede registrar el _source con source:N)
osq "/lab_content/_settings" -X PUT -H 'Content-Type: application/json' -d '{
  "index.indexing.slowlog.threshold.index.warn": "1s",
  "index.indexing.slowlog.threshold.index.info": "500ms",
  "index.indexing.slowlog.source": "200"
}'

# Ver la config efectiva
osq "/lab_content/_settings?filter_path=**.slowlog&flat_settings=true"
```

Dónde sale el log: en `*_index_search_slowlog.log` / `*_index_indexing_slowlog.log`
del nodo. En Kubernetes, por stdout del contenedor:

```bash
kubectl logs -n opensearch-lab oslab-nodes-0 | grep -i slowlog
# o todos los nodos:
for p in oslab-nodes-0 oslab-nodes-1 oslab-nodes-2; do kubectl logs -n opensearch-lab $p | grep slowlog; done
```

Provocar una query lenta para verla aparecer (wildcard con comodín inicial, el
anti-patrón de `analisis_avanzado_cluster.md §12.2`):

```bash
osq "/lab_content/_search" -H 'Content-Type: application/json' -d '{
  "size": 1, "query": { "wildcard": { "EDITORIAL--CONTAINER.MEDIAID.keyword": "*0000100*" } } }'
```

**Para contar:** el slow log es la herramienta clásica para "pillar" qué query
real está siendo lenta en producción. Umbral por índice → en el índice de
contenidos pones 1-2 s; en el de logs (ingesta) vigilas `indexing.slowlog`.
Desactivar: poner los umbrales a `-1`.

---

## 2. query-insights: Top N queries lentas SIN leer logs

El plugin `query-insights` (ya instalado) mantiene un Top N de las consultas más
costosas por latencia / CPU / memoria, consultable por API. Más cómodo que el
slow log para una foto rápida.

```bash
# Activar el monitor de "top queries by latency"
osq "/_cluster/settings" -X PUT -H 'Content-Type: application/json' -d '{
  "persistent": {
    "search.insights.top_queries.latency.enabled": true,
    "search.insights.top_queries.latency.top_n_size": 10,
    "search.insights.top_queries.latency.window_size": "5m"
  }
}'

# Lanzar algunas queries (incluida una cara) y consultar el Top N
osq "/_insights/top_queries?type=latency"
```

**Para contar:** en Dashboards esto se ve en **Query Insights** (menú lateral).
Es lo que enseñas para "¿cuáles son mis 10 queries más lentas ahora mismo?".

---

## 3. Alerting: monitor + trigger + notificación (webhook / email)

Flujo del plugin Alerting: **Monitor** (qué y cada cuánto se evalúa) →
**Trigger** (condición) → **Action** (a qué **canal** de Notifications se manda).

### 3.1 Crear el canal de notificación (Notifications)

**Webhook** (lo más fácil para demo; vale un endpoint de prueba tipo webhook.site):

```bash
osq "/_plugins/_notifications/configs" -X POST -H 'Content-Type: application/json' -d '{
  "config_id": "chan-webhook",
  "name": "canal-webhook-demo",
  "config": {
    "name": "canal-webhook-demo",
    "description": "Webhook de pruebas",
    "config_type": "webhook",
    "is_enabled": true,
    "webhook": { "url": "https://webhook.site/REEMPLAZA-POR-TU-UUID" }
  }
}'
```

**Email** (requiere un canal SMTP "sender" + lista de destinatarios):

```bash
# 1) sender SMTP
osq "/_plugins/_notifications/configs" -X POST -H 'Content-Type: application/json' -d '{
  "config_id": "smtp-sender",
  "config": {
    "name": "smtp-curso", "description": "SMTP del curso", "config_type": "smtp_account",
    "is_enabled": true,
    "smtp_account": { "host": "smtp.tu-dominio.com", "port": 587,
                      "method": "start_tls", "from_address": "opensearch@tu-dominio.com" }
  }
}'
# 2) canal email que usa ese sender
osq "/_plugins/_notifications/configs" -X POST -H 'Content-Type: application/json' -d '{
  "config_id": "chan-email",
  "config": {
    "name": "alertas-ops", "description": "Email a operaciones", "config_type": "email",
    "is_enabled": true,
    "email": { "email_account_id": "smtp-sender",
               "recipient_list": [ { "recipient": "ops@tu-dominio.com" } ] }
  }
}'

# probar un canal
osq "/_plugins/_notifications/feature/test/chan-webhook" -X GET
```

### 3.2 Monitor "per query" que cuenta errores/eventos y dispara

Ejemplo realista: vigilar que el ratio de **rechazos del write pool** o el nº de
documentos de cierto tipo no se dispara. Versión simple: monitor que cuenta docs
de un índice y avisa si supera un umbral.

```bash
osq "/_plugins/_alerting/monitors" -X POST -H 'Content-Type: application/json' -d '{
  "type": "monitor",
  "name": "monitor-conteo-locators",
  "monitor_type": "query_level_monitor",
  "enabled": true,
  "schedule": { "period": { "interval": 1, "unit": "MINUTES" } },
  "inputs": [{
    "search": {
      "indices": ["lab_content"],
      "query": { "size": 0,
        "query": { "bool": { "filter": [ { "term": { "doc_type.keyword": "LOCATOR" } } ] } } }
    }
  }],
  "triggers": [{
    "name": "demasiados-locators",
    "severity": "1",
    "condition": { "script": { "lang": "painless",
      "source": "ctx.results[0].hits.total.value > 1000000" } },
    "actions": [{
      "name": "avisar-webhook",
      "destination_id": "",
      "message_template": { "source": "Alerta: hay {{ctx.results.0.hits.total.value}} LOCATOR (> umbral)." },
      "notification_id": "chan-webhook"
    }]
  }]
}'

# listar / ejecutar a mano para probar el trigger
osq "/_plugins/_alerting/monitors/_search" -X POST -H 'Content-Type: application/json' -d '{"query":{"match_all":{}}}'
# (sustituir <id>) ejecutar sin esperar al schedule:
# osq "/_plugins/_alerting/monitors/<id>/_execute" -X POST
```

**Para contar:** lo normal es crear estos monitores desde la **UI de Dashboards →
Alerting** (más visual: monitor por query, por buckets, por clúster-metrics como
JVM/CPU, o per-document). El monitor tipo **cluster_metrics** es ideal para
operación: vigila `_cluster/health` (status != green), heap, o `_cat/thread_pool`
(rejected > 0) y avisa. La API de arriba es para reproducir/versionar.

> Plantilla útil: monitor **cluster_metrics** sobre `GET /_cluster/health` con
> trigger `ctx.results[0].status != "green"` → notificación. Es la alerta básica
> de "mi cluster se ha puesto amarillo/rojo".

---

## 4. Anomaly Detection (plugin ML)

Detecta anomalías en series temporales (p.ej. caídas/picos de throughput de
ingesta o de latencia) usando Random Cut Forest, sin definir umbrales fijos.

```bash
# Crear un detector sobre una métrica temporal (requiere un índice con @timestamp
# y un campo numérico; sirve un índice de métricas o de eventos con fecha).
osq "/_plugins/_anomaly_detection/detectors" -X POST -H 'Content-Type: application/json' -d '{
  "name": "ad-ingesta",
  "description": "Anomalias en el ritmo de indexacion",
  "time_field": "@timestamp",
  "indices": ["lab_content"],
  "feature_attributes": [{
    "feature_name": "docs_por_intervalo",
    "feature_enabled": true,
    "aggregation_query": { "cuenta": { "value_count": { "field": "doc_type.keyword" } } }
  }],
  "detection_interval": { "period": { "interval": 5, "unit": "Minutes" } },
  "window_delay": { "period": { "interval": 1, "unit": "Minutes" } }
}'

# arrancar el detector (sustituir <detector_id> por el id devuelto)
# osq "/_plugins/_anomaly_detection/detectors/<detector_id>/_start" -X POST
# resultados:
# osq "/_plugins/_anomaly_detection/detectors/<detector_id>/results" 
```

**Para contar:** AD necesita datos con **continuidad temporal** para entrenar; en
clase se ve mejor en la **UI → Anomaly Detection**, donde se elige el índice, la
feature y se ven las anomalías en una gráfica con su `anomaly_grade`. Se puede
encadenar con un **monitor de Alerting tipo "Per cluster metrics / AD"** para que
una anomalía dispare una notificación.

---

## 5. Limpieza

```bash
# slow logs a -1 (desactivar)
osq "/lab_content/_settings" -X PUT -H 'Content-Type: application/json' -d '{
  "index.search.slowlog.threshold.query.warn":"-1","index.search.slowlog.threshold.query.info":"-1",
  "index.search.slowlog.threshold.query.debug":"-1","index.indexing.slowlog.threshold.index.warn":"-1",
  "index.indexing.slowlog.threshold.index.info":"-1" }'
# borrar monitores / detectores / canales por su id desde la UI o por API.
```

> Si se prueba en **oslab** (cluster desechable), no hace falta limpiar nada:
> se borra el cluster entero al acabar.
