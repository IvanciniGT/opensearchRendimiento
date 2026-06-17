# Temario: qué queda por cubrir y estado de los plugins

Revisión de los 10 puntos del temario contra lo impartido (notas dia1-6 +
cuadernos `analisis_avanzado_cluster.md` y `practica_rendimiento_tuning.md` +
prácticas en vivo). Y, sobre todo: **qué plugins hacen falta y cuáles ya están**.

> Cluster del curso: **OpenSearch 3.6.0** (distribución estándar), 3 nodos
> `dim` (data+ingest+master), gestionado por el **OpenSearch Operator**
> (`opensearch.org/v1`). Dashboards 3.6.0 estándar.

---

## 1. TL;DR — no hay que instalar casi nada

La distribución estándar de OpenSearch 3.6.0 **ya incluye TODOS los plugins**
que parecían faltar. Comprobado con `GET /_cat/plugins`:

| Necesidad (temario)        | Plugin                          | ¿Instalado? |
| -------------------------- | ------------------------------- | :---------: |
| Alerting (punto 8)         | `opensearch-alerting`           | ✅ SÍ |
| Notificaciones email/web   | `opensearch-notifications(-core)`| ✅ SÍ |
| Anomaly Detection (8)      | `opensearch-anomaly-detection`  | ✅ SÍ |
| ML (base de AD)            | `opensearch-ml`                 | ✅ SÍ |
| Observability (7)          | `opensearch-observability`      | ✅ SÍ |
| ISM / rollover (6)         | `opensearch-index-management`   | ✅ SÍ |
| Métricas Prometheus (7)    | `prometheus-exporter`           | ✅ SÍ |
| Slow / top queries (8)     | `query-insights`                | ✅ SÍ |
| Reporting                  | `opensearch-reports-scheduler`  | ✅ SÍ |
| Security analytics, SQL, kNN, neural, geo, LTR, flow-framework, skills... | varios | ✅ SÍ |

**La UI de Dashboards** usa la imagen estándar `opensearch-dashboards:3.6.0`,
que trae los plugins de front (Observability, Alerting, Anomaly Detection,
Index Management). Si "no aparecía Observability" es cuestión de **menú**, no de
instalación: está en el menú lateral izquierdo, sección **OpenSearch Plugins /
Observability** (Notebooks, Logs, Traces, Metrics, Applications). Alerting y
Anomaly Detection cuelgan de **OpenSearch Plugins → Alerting / Anomaly Detection**.

> Conclusión: **no se instala nada nuevo en el motor**. El trabajo pendiente es
> CONFIGURAR y USAR estas funciones (slow logs, monitores, detectores, snapshots,
> ISM, merge policies) — para eso están los cuadernos de `ejemplos/`.

### Verificación funcional en el cluster bueno (17 jun 2026)

Probado por API que cada plugin responde en el cluster real:

| Plugin | Endpoint probado | Resultado |
| ------ | ---------------- | --------- |
| prometheus-exporter | `GET /_prometheus/metrics` | ✅ 5.064 líneas de métricas |
| alerting | `GET /_plugins/_alerting/monitors/_search` | ✅ responde (0 monitores) |
| anomaly-detection | `GET /_plugins/_anomaly_detection/detectors/_count` | ✅ responde (404 del índice `.opendistro-anomaly-detectors` = aún sin detectores; se crea al definir el primero) |
| notifications | `GET /_plugins/_notifications/features` | ✅ responde |
| index-management (ISM) | `GET /_plugins/_ism/policies` | ✅ responde (0 policies) |
| observability | `GET /_plugins/_observability/object` | ✅ responde (0 objetos) |
| query-insights | `GET /_insights/top_queries?type=latency` | ✅ responde |

**Activado en el cluster real**: `query-insights` (top queries por latency + cpu +
memory, `top_n=10`, ventana 5m). Reversible:
```bash
PUT /_cluster/settings { "persistent": {
  "search.insights.top_queries.latency.enabled": false,
  "search.insights.top_queries.cpu.enabled": false,
  "search.insights.top_queries.memory.enabled": false } }
```
El resto (monitores, detectores, ISM policies, snapshots) se crean en clase o en
`oslab` con los cuadernos; no se han dejado artefactos en producción.

---

## 2. Cobertura punto por punto

| # | Tema | Estado | Dónde / qué falta |
| - | ---- | ------ | ----------------- |
| 1 | Fundamentos de monitorización | ✅ Completo | dia1/2/5, `analisis_avanzado` §1-2 |
| 2 | Entorno de carga elevada | ✅ Completo | `carga/` (generador/cargador/bench/rampa), 10M docs |
| 3 | Diagnóstico de cuellos de botella | ✅ Completo | `analisis_avanzado` §5-6, `practica` §3/§6; CPU 1→4 y NFS en vivo |
| 4 | Optimización de consultas | ✅ Completo | `analisis_avanzado` §12-13 (explain/profile/validate/anti-patrones) |
| 5 | Indexación y tuning general | 🟡 Casi | `practica` §4; **faltaba: merge policies** → `lab_merge_policies.md` |
| 6 | Mantenimiento de índices | 🟡 Parcial | segmentos/forcemerge ✓, ISM ya explicado de palabra; **falta práctica ISM/rollover** → `lab_ism_rollover.md` |
| 7 | Monitorización visual y dashboards | 🟡 | Grafana/Prometheus ya mostrado (no documentado); **falta Observability + dashboards operativos** → `lab_observability_prometheus.md` |
| 8 | Logging, alertas, troubleshooting | ❌→🟡 | **Slow logs + Alerting + Anomaly Detection** → `lab_slowlogs_alerting.md` |
| 9 | Snapshots y operación avanzada | 🟡 Parcial | validación antes/después ✓; **falta snapshots/recovery** → `lab_snapshots.md` |
| 10| Taller práctico final | 🟡 En curso | lo de hoy (CPU, ingesta, NFS) es de este estilo; se cierra integrando 7/8/9 |

---

## 3. Lo que queda por impartir (con su cuaderno)

1. **Slow logs + Alerting + Anomaly Detection** (punto 8) → `ejemplos/lab_slowlogs_alerting.md`
   - Activar `search.slowlog` / `indexing.slowlog` y leerlos.
   - `query-insights` (Top N queries lentas) sin tocar logs.
   - Monitor de Alerting (per-query) + canal de notificación (webhook/email).
   - Detector de Anomaly Detection sobre una métrica.

2. **Observability + Prometheus/Grafana** (punto 7) → `ejemplos/lab_observability_prometheus.md`
   - Endpoint `_prometheus/metrics`, métricas clave y dashboards operativos.
   - Observability en Dashboards (dónde está y para qué).

3. **Snapshots y recuperación** (punto 9) → `ejemplos/lab_snapshots.md`
   - Registrar repositorio, crear/restaurar snapshot, política automática (SM).

4. **ISM / rollover** (parte del 6) → `ejemplos/lab_ism_rollover.md`
   - Política ISM con rollover por tamaño/edad + transiciones hot→delete.

5. **Merge policies** (parte del 5) → `ejemplos/lab_merge_policies.md`
   - `forcemerge`, parámetros de la merge policy, throttling.

> Para probar 8/9/6 con tranquilidad (crear índices, snapshots, ISM, reinicios)
> sin tocar el cluster real, se ha montado un **cluster de laboratorio efímero**
> (`oslab`, almacenamiento `emptyDir`): ver `k8s/oslab-cluster.yaml` y
> `k8s/README-oslab.md`.

---

## 4. Cómo verificar el estado de plugins (para enseñar en clase)

```bash
# Motor: lista de plugins por nodo
GET /_cat/plugins?v

# ¿Está el endpoint de Prometheus?
GET /_prometheus/metrics            # (texto plano estilo exporter)

# Categorías de plugins instalados (alerting, anomaly, observability, ism...)
GET /_cat/plugins?h=component&s=component | sort -u
```
