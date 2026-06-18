Vale. **Primero: Snapshots y recuperación**.

Yo lo plantearía como una sección de **operación y continuidad**, no como “un comando para hacer backup”.

# 1. Idea principal

Un snapshot es una **copia recuperable de índices OpenSearch en un repositorio externo**.

No es una réplica. No es un backup del pod. No es copiar el directorio de datos.

```text
OpenSearch cluster
   índices / shards / segmentos
          ↓
      snapshot
          ↓
repositorio externo
S3 / MinIO / filesystem compartido / repositorio compatible
```

Frase para clase:

> La réplica me protege de que caiga un nodo. El snapshot me protege de tener que recuperar datos.

# 2. Snapshot vs réplica

Esta comparación es clave:

| Concepto                                        | Réplica             | Snapshot                       |
| ----------------------------------------------- | ------------------- | ------------------------------ |
| Objetivo                                        | Alta disponibilidad | Recuperación                   |
| Vive dentro del cluster                         | Sí                  | No debería                     |
| Protege si cae un nodo                          | Sí                  | Indirectamente                 |
| Protege si borro un índice                      | No                  | Sí                             |
| Protege si hago un `update_by_query` desastroso | No                  | Sí, si tengo snapshot anterior |
| Protege ante pérdida total del cluster          | No                  | Sí, si está fuera              |

Ejemplo claro:

```text
Se cae un nodo
→ me ayudan las réplicas.

Alguien borra un índice
→ las réplicas replican el borrado.
→ necesito snapshot.

Una carga masiva corrompe datos
→ las réplicas replican la corrupción.
→ necesito snapshot anterior.

Pierdo el cluster completo
→ necesito repositorio externo.
```

Frase buena:

> La réplica no es backup. La réplica replica también los errores.

# 3. Qué guarda un snapshot

Puede guardar:

```text
índices
mappings
settings de índices
aliases
shards
segmentos
data streams, si aplica
estado global del cluster, si se incluye
```

Hay una decisión importante:

```json
{
  "include_global_state": false
}
```

Para restauraciones controladas, normalmente prefiero explicar esto:

> Si quiero restaurar un índice concreto, suelo evitar `include_global_state: true` salvo que sepa exactamente lo que estoy haciendo. No quiero pisar templates, políticas, seguridad o configuración global del cluster destino sin querer.

# 4. Snapshot incremental

OpenSearch no copia necesariamente todo cada vez. Los snapshots son **incrementales a nivel de segmentos**.

Lucene usa segmentos inmutables. Si un segmento ya fue copiado en un snapshot anterior, no tiene que copiarse otra vez.

```text
Snapshot 1:
  segmento A
  segmento B
  segmento C

Snapshot 2:
  segmento A ya estaba
  segmento B ya estaba
  segmento C ya estaba
  segmento D nuevo
```

Frase para clase:

> Los snapshots son incrementales porque Lucene trabaja con segmentos inmutables. Se reutilizan los segmentos ya guardados.

Pero matiz:

> Incremental no significa gratis. Sigue consumiendo I/O, ancho de banda, tiempo y espacio para los segmentos nuevos.

# 5. Repositorio externo

Un snapshot necesita un **repositorio**.

Puede ser:

```text
S3
MinIO / compatible S3
filesystem compartido
repositorio gestionado por la plataforma
```

Malas ideas:

```text
emptyDir
disco local del pod
directorio dentro del data path de OpenSearch
PVC que cae con el mismo cluster
almacenamiento sin política de protección
```

Frase:

> Si el repositorio de snapshots cae con el mismo fallo que el cluster, no tienes recuperación real.

# 6. RPO y RTO

Aquí merece la pena meter gestión seria.

```text
RPO = cuánto dato puedo perder.
RTO = cuánto tiempo puedo tardar en recuperar el servicio.
```

Ejemplo:

```text
Snapshot cada 24 horas
→ RPO aproximado: hasta 24 horas de pérdida.

Snapshot cada 1 hora
→ RPO aproximado: hasta 1 hora de pérdida.

Restore tarda 2 horas
→ RTO real mínimo: 2 horas + validaciones.
```

Frase:

> “Tenemos backup” no significa nada si no sabemos cuánto dato podemos perder y cuánto tardamos en volver.

# 7. Frecuencia y retención

La frecuencia depende de:

```text
criticidad del dato
volumen de cambios
coste de reconstrucción
RPO requerido
coste de almacenamiento
```

Ejemplos:

```text
Índice crítico con datos no reconstruibles
→ snapshots frecuentes.

Índice de logs reconstruible desde otra fuente
→ snapshots menos frecuentes o retención más corta.

Índice histórico read-only
→ snapshot al cerrar/rotar y luego retención.
```

Retención típica:

```text
horarios durante 24/48h
diarios durante 7/30 días
semanales durante varios meses
```

Cuidado con la corrupción lógica:

```text
Si corrompo datos el lunes
y me doy cuenta el viernes
pero solo retengo snapshots de 24h,
ya no tengo una copia sana.
```

# 8. Restauración segura

No siempre quieres restaurar encima del índice existente.

Patrón seguro:

```text
restauro con otro nombre
valido datos
comparo
decido si cambio alias o reindexo
```

Ejemplo conceptual:

```json
{
  "indices": "lab_content",
  "include_global_state": false,
  "rename_pattern": "lab_content",
  "rename_replacement": "lab_content_restored"
}
```

Frase:

> La restauración más segura no suele ser pisar producción. Suele ser restaurar con otro nombre, comprobar y luego decidir.

# 9. Aliases y aplicaciones

Si la aplicación usa aliases, restaurar un índice no basta.

Ejemplo:

```text
Aplicación consulta:
  content_current

Índice real:
  content_000123

Restauro:
  content_000120_restored

La aplicación no lo usará hasta que mueva el alias.
```

Buenas prácticas:

```text
usar aliases para desacoplar app e índice físico
documentar cómo cambiar alias
probar rollback
no improvisar en producción
```

# 10. Seguridad

Un snapshot puede contener todos los datos del índice. Hay que protegerlo como producción.

Preguntas:

```text
¿Quién puede crear snapshots?
¿Quién puede restaurarlos?
¿Dónde se guardan?
¿Está cifrado el repositorio?
¿Quién tiene acceso al bucket/directorio?
¿Incluye índices de sistema?
¿Incluye estado global?
```

Frase:

> Un snapshot puede ser una fuga masiva de datos si el repositorio no está protegido.

# 11. No tocar el repositorio a mano

Importantísimo:

```text
No borrar ficheros manualmente.
No mover carpetas.
No limpiar el bucket “a ojo”.
No copiar parcialmente el repositorio.
```

Los snapshots se borran mediante API:

```http
DELETE /_snapshot/mi_repo/snapshot_antiguo
```

Frase:

> El repositorio de snapshots tiene metadatos internos. Si borras ficheros a mano, puedes romper snapshots que parecían sanos.

# 12. Backup no probado = no backup

Esta es la idea de cierre.

Buenas prácticas:

```text
probar restores periódicos
restaurar en entorno de laboratorio
medir tiempos reales
validar número de documentos
validar mappings
validar aliases
validar búsquedas críticas
documentar el procedimiento
```

Frase fuerte:

> Un snapshot que nunca se ha restaurado no es un backup. Es una esperanza.

# 13. Demo mínima por API

Cuando pases a práctica, haría esta secuencia:

```http
GET /_snapshot
```

Ver repositorios existentes.

Si ya hay repositorio:

```http
PUT /_snapshot/mi_repo/snap_001?wait_for_completion=true
{
  "indices": "lab_content",
  "include_global_state": false
}
```

Ver snapshots:

```http
GET /_snapshot/mi_repo/_all
```

Restaurar con otro nombre:

```http
POST /_snapshot/mi_repo/snap_001/_restore
{
  "indices": "lab_content",
  "include_global_state": false,
  "rename_pattern": "lab_content",
  "rename_replacement": "lab_content_restored"
}
```

Comprobar:

```http
GET /_cat/indices/lab_content*
```

```http
GET /lab_content_restored/_count
```

# 14. Mini guion para decirlo en clase

```text
Vamos a empezar por snapshots porque operar OpenSearch no es solo hacerlo rápido.

Hasta ahora hemos hablado de rendimiento: shards, segmentos, merges, cachés, memoria, CPU, queries lentas. Pero en producción también hay que responder a otra pregunta: ¿qué pasa si perdemos datos?

Las réplicas nos ayudan si cae un nodo, pero no nos protegen de un borrado accidental, de una corrupción lógica, de una actualización masiva mal hecha o de perder el cluster entero. Para eso necesitamos snapshots.

Y un snapshot solo es útil si está fuera del cluster, si tiene una política de retención razonable y, sobre todo, si hemos probado a restaurarlo.
```

# 15. Cierre de la sección

La frase final:

> Snapshot no es “hacer copia”. Snapshot es diseñar recuperación: repositorio externo, RPO, RTO, retención, seguridad y pruebas reales de restore.



































Siguiente bloque: **Slow logs + Query Insights**.

Aquí el objetivo es pasar de:

```text
“OpenSearch va lento”
```

a:

```text
“estas queries concretas están tardando, consumiendo CPU/memoria, o generando fetch caro”
```

# 1. Idea principal

Hay dos herramientas complementarias:

```text
Slow logs
  → dejan rastro en logs cuando una búsqueda o indexación supera un umbral.

Query Insights
  → mantiene ranking de las queries más caras por latencia, CPU o memoria.
```

Frase para clase:

> `profile` sirve para estudiar una query que ya conozco. Slow logs y Query Insights sirven para descubrir qué queries reales tengo que estudiar.

---

# 2. Slow logs: qué son

Los **slow logs** son logs especiales por índice que registran operaciones lentas.

Hay dos familias principales:

```text
search slow log
  → búsquedas lentas

indexing slow log
  → escrituras/indexaciones lentas
```

No están pensados para dejarlos hiperverbosos siempre. Son una herramienta de diagnóstico.

---

# 3. Search slow log

Una búsqueda tiene fases. Las dos más importantes para explicar son:

```text
query phase
  → buscar, filtrar, calcular score, agregaciones, joins, etc.

fetch phase
  → recuperar documentos, _source, stored fields, highlights, inner_hits, etc.
```

Esto es muy útil porque una búsqueda puede ser lenta por motivos distintos.

Ejemplo:

```text
Query phase lenta
  → query compleja, has_child, wildcard, agregaciones caras, alta cardinalidad.

Fetch phase lenta
  → se devuelven muchos documentos, _source pesado, highlight, inner_hits, campos grandes.
```

Frase:

> No es lo mismo tardar buscando que tardar recuperando documentos. El slow log separa query phase y fetch phase.

---

# 4. Activar slow logs por índice

Ejemplo razonable para laboratorio:

```http
PUT /lab_content/_settings
{
  "index.search.slowlog.threshold.query.warn": "500ms",
  "index.search.slowlog.threshold.query.info": "200ms",
  "index.search.slowlog.threshold.fetch.warn": "300ms",
  "index.indexing.slowlog.threshold.index.warn": "500ms"
}
```

Explicación:

```text
query.warn = registra búsquedas cuya query phase supere 500 ms
query.info = registra búsquedas cuya query phase supere 200 ms
fetch.warn = registra búsquedas cuya fetch phase supere 300 ms
index.warn = registra indexaciones que superen 500 ms
```

Para producción, cuidado:

```text
umbrales demasiado bajos
  → demasiado ruido
  → muchos logs
  → más coste
  → difícil separar señal de basura
```

Frase:

> El slow log no debe convertirse en un log de todo. Debe capturar lo que realmente merece investigación.

---

# 5. Niveles de slow log

Puedes configurar varios niveles:

```text
trace
debug
info
warn
```

Ejemplo:

```http
PUT /lab_content/_settings
{
  "index.search.slowlog.threshold.query.warn": "1s",
  "index.search.slowlog.threshold.query.info": "500ms",
  "index.search.slowlog.threshold.query.debug": "200ms",
  "index.search.slowlog.threshold.query.trace": "50ms"
}
```

Para clase, yo no bajaría demasiado salvo demo controlada.

Frase:

> Cuanto más bajo pongo el umbral, más operaciones entran en el slow log. Eso puede ser útil en laboratorio, pero peligroso en producción.

---

# 6. Qué información aporta el slow log

Un slow log puede ayudarte a ver:

```text
índice afectado
shard afectado
tiempo consumido
fase query/fetch
query ejecutada
usuario, si está disponible
nodo
tamaño solicitado
parámetros relevantes
```

Lo importante no es solo que “una query tarda”, sino poder responder:

```text
¿qué índice?
¿qué shard?
¿qué tipo de query?
¿qué filtros?
¿qué agregaciones?
¿qué usuario/app?
¿qué patrón se repite?
```

---

# 7. Dónde se leen en Kubernetes/OpenShift

En cluster con operador/pods, normalmente lo miras como logs de los pods.

Ejemplo genérico:

```bash
kubectl logs -n proyecto-ivan <pod-opensearch> | grep slowlog
```

O por todos los pods con selector, si lo tenéis etiquetado:

```bash
kubectl logs -n proyecto-ivan -l opster.io/opensearch-cluster=<cluster-name> --tail=500
```

En OpenShift:

```bash
oc logs -n proyecto-ivan <pod-opensearch> | grep slowlog
```

También puede haber configuración de logging que los mande a un sistema centralizado.

Frase:

> Configurar slow logs en OpenSearch no basta; hay que saber dónde acaban esos logs en tu plataforma.

---

# 8. Indexing slow log

No todo es búsqueda. También interesa detectar escrituras lentas.

Activación:

```http
PUT /lab_content/_settings
{
  "index.indexing.slowlog.threshold.index.warn": "500ms",
  "index.indexing.slowlog.threshold.index.info": "200ms"
}
```

Casos donde puede saltar:

```text
bulk demasiado grande
scripts de update caros
scripted_upsert complejo
shard saturado
disco lento
CPU limitada
réplicas lentas
refresh/merge compitiendo
pipeline de ingest pesado
```

En vuestro caso, esto conecta muy bien con GELASTIC/scripted upsert:

```text
si cada evento dispara update con script,
y el script compara secciones, fechas, permisos, join_field...
la escritura ya no es solo “meter un documento”.
```

Frase:

> Una indexación lenta no siempre es problema de OpenSearch puro. Puede venir de scripts, pipelines, réplicas, I/O, CPU o diseño de actualización.

---

# 9. Query Insights: qué aporta

**Query Insights** es más cómodo para ver rankings.

No espera a que tú sepas qué query mirar. Te da listas de las queries más caras.

Ejemplos:

```http
GET /_insights/top_queries?type=latency
```

```http
GET /_insights/top_queries?type=cpu
```

```http
GET /_insights/top_queries?type=memory
```

Diferencia:

```text
latency
  → las que más tardan

cpu
  → las que más CPU consumen

memory
  → las que más memoria estimada consumen
```

Frase:

> No todas las queries peligrosas son las más lentas. Algunas no tardan muchísimo, pero consumen mucha CPU o memoria y castigan al cluster.

---

# 10. Slow logs vs Query Insights

Comparación buena para clase:

| Herramienta    | Para qué sirve mejor                                           |
| -------------- | -------------------------------------------------------------- |
| Slow logs      | Tener trazabilidad en logs de operaciones que superan umbrales |
| Query Insights | Ver ranking de queries caras recientes                         |
| Profile API    | Analizar en detalle una query concreta                         |
| Explain API    | Entender scoring/documento concreto                            |
| Validate query | Comprobar cómo se interpreta una query                         |

Frase:

> Query Insights me ayuda a encontrar sospechosos. Slow logs me dan evidencias en logs. Profile me permite hacer la autopsia.

---

# 11. Flujo práctico de diagnóstico

Este flujo queda muy bien:

```text
1. Usuario dice: “el buscador va lento”.
2. Miro Query Insights por latency.
3. Identifico queries repetidas o muy caras.
4. Miro si consumen CPU o memoria.
5. Activo slow logs con umbrales razonables si necesito trazabilidad.
6. Reproduzco una query candidata con profile.
7. Reviso mapping, cardinalidad, joins, wildcard, sort, highlight, inner_hits.
8. Decido optimización.
```

Ejemplo:

```text
Query Insights muestra:
  has_child + inner_hits + highlight + sort

Hipótesis:
  join caro
  fetch caro por inner_hits/highlight
  sort sobre campo no ideal
  demasiados documentos candidatos

Siguiente paso:
  profile
  revisar cardinalidad
  revisar mapping
  revisar si desnormalizar o precalcular
```

---

# 12. Qué queries suelen aparecer como problemáticas

En este curso, los sospechosos típicos son:

```text
has_child / has_parent
inner_hits
wildcard con comodín inicial
simple_query_string muy amplio
agregaciones de alta cardinalidad
cardinality sobre campos enormes
sort profundo
from/size profundo
highlight
consultas que devuelven mucho _source
scripts
KNN/vectoriales
```

Frase:

> Las queries lentas rara vez son misteriosas: suelen mezclar fan-out, cardinalidad, joins, fetch pesado o patrones que no aprovechan bien el índice.

---

# 13. Buenas prácticas con slow logs

```text
No dejar umbrales ridículamente bajos en producción.
Activarlos por índice, no necesariamente para todo.
Distinguir query phase y fetch phase.
Activarlos temporalmente durante investigación.
Centralizar logs si el cluster tiene varios nodos.
Correlacionar con hora, usuario, endpoint de aplicación y carga.
Revisar slow logs junto con thread pools, CPU, heap, breakers y merges.
```

Frase:

> Un slow log aislado no explica todo. Hay que cruzarlo con métricas del cluster y de la plataforma.

---

# 14. Buenas prácticas con Query Insights

```text
Activar solo lo que se necesita.
Revisar latency, CPU y memory, no solo latency.
Mirar patrones repetidos, no solo una query puntual.
Usarlo como puerta de entrada a profile.
No confundir top query con causa única del problema.
```

Frase:

> Query Insights no sustituye al análisis. Prioriza dónde mirar.

---

# 15. Cuidado con el efecto observador

Tanto slow logs como trazas detalladas pueden añadir coste.

Mensaje práctico:

```text
Más observabilidad
  → más información
  → más coste

Menos observabilidad
  → menos coste
  → menos visibilidad
```

Frase:

> La observabilidad también consume recursos. Hay que configurarla con criterio.

---

# 16. Mini guion para decirlo en clase

```text
Ahora vamos a ver cómo detectar queries problemáticas en un cluster real.

Hasta ahora hemos usado profile y explain, pero eso parte de que yo ya sé qué query quiero estudiar. En producción normalmente ocurre al revés: alguien dice que va lento y yo tengo que descubrir qué está pasando.

Para eso tengo dos herramientas muy útiles: slow logs y Query Insights.

Slow logs me dejan rastro en logs cuando una búsqueda o indexación supera un umbral. Query Insights me da rankings de las queries más caras por latencia, CPU o memoria.

La idea no es activar todo al máximo y llenar discos de logs. La idea es capturar señal suficiente para poder investigar.
```

# 17. Cierre de la sección

Frase final:

> Slow logs y Query Insights son el puente entre “hay quejas de rendimiento” y “estas son las queries que debemos analizar”. A partir de ahí ya entran profile, mapping, cardinalidad, joins, cachés, shards y recursos del cluster.































Siguiente bloque: **Alerting + Notifications**.

Aquí el objetivo es pasar de:

```text
“puedo ver métricas si entro a mirar”
```

a:

```text
“el sistema me avisa cuando ocurre algo que merece atención”
```

Pero con una idea importante: **alertar no es llenar de correos a la gente**. Alertar bien es convertir síntomas técnicos en señales accionables.

# 1. Idea principal

En OpenSearch, la parte de alertas se apoya en dos piezas:

```text
Alerting
  → define monitores, condiciones y acciones.

Notifications
  → define los canales por los que se envían los avisos.
```

Modelo mental:

```text
Monitor
   ↓
ejecuta una consulta periódicamente
   ↓
Trigger
   ↓
evalúa una condición
   ↓
Action
   ↓
envía mensaje por un Channel
```

Frase para clase:

> Alerting responde a la pregunta “¿cuándo debo avisar?”. Notifications responde a la pregunta “¿por dónde aviso?”.

---

# 2. Componentes básicos

## Monitor

El **monitor** es lo que se ejecuta cada cierto tiempo.

Puede basarse en:

```text
una query
una métrica
un índice de logs
un índice de eventos
una consulta agregada
```

Ejemplo conceptual:

```text
Cada 1 minuto:
  busca en logs de OpenSearch
  cuenta errores
  si hay más de X
  dispara alerta
```

## Trigger

El **trigger** es la condición.

Ejemplos:

```text
cluster_status != green
heap_used_percent > 85
rejected > 0
latencia_p95 > 1000 ms
errores_5xx > 10 en 5 minutos
```

## Action

La **action** es lo que pasa cuando se cumple la condición:

```text
enviar email
llamar webhook
avisar a Slack/Teams vía webhook
crear evento
mandar notificación interna
```

## Channel

El **channel** viene de Notifications:

```text
email
webhook
Slack/Teams vía webhook
Amazon SNS, si aplica
otros destinos configurados
```

Frase:

> Monitor y trigger deciden si hay alerta. Notification channel decide cómo sale del sistema.

---

# 3. Qué tipo de alertas tienen sentido

Yo las agruparía en cuatro familias.

## 1. Alertas de salud del cluster

Estas son básicas:

```text
cluster red
cluster yellow sostenido
nodos caídos
shards unassigned
disco por encima de watermark
```

Ojo con `yellow`:

```text
yellow puntual durante mantenimiento
  → quizá no quiero despertar a nadie

yellow sostenido con shards sin asignar
  → sí merece atención
```

Frase:

> No todo `yellow` es una emergencia, pero un `yellow` sostenido sin explicación sí es un síntoma operativo.

---

## 2. Alertas de saturación

Aquí entra lo que habéis visto de diagnóstico:

```text
heap alto sostenido
GC excesivo
circuit breakers tripped
thread_pool rejected
search queue creciendo
write queue creciendo
CPU throttling
disco alto
I/O lento
```

La idea importante:

> No alertar solo por un valor instantáneo. Mejor alertar por valor sostenido o por tendencia.

Ejemplo:

```text
heap > 85% durante 10 minutos
```

mejor que:

```text
heap > 85% una vez
```

---

## 3. Alertas de rendimiento

Relacionadas con la experiencia de usuario:

```text
latencia media alta
p95/p99 alto
queries lentas repetidas
indexing latency alta
bulk failures
errores parciales en bulk
```

Frase:

> Para rendimiento, las medias engañan. Mejor mirar percentiles o contar operaciones que superan un umbral.

Ejemplo:

```text
p95 de búsqueda > 1s durante 5 minutos
```

es más útil que:

```text
media de búsqueda > 1s
```

---

## 4. Alertas funcionales o de negocio

También puedes alertar sobre datos:

```text
no entran documentos en 10 minutos
suben errores de ingesta
cae volumen de eventos
aparecen demasiados documentos en estado ERROR
sube el número de procesos fallidos
```

Esto suele ser más útil para la aplicación que para la infraestructura.

Frase:

> Las mejores alertas no siempre son técnicas. A veces lo importante es detectar que ha dejado de entrar negocio.

---

# 4. Alertas buenas vs alertas malas

## Mala alerta

```text
heap > 70%
```

Problema:

```text
puede ser normal
puede ser puntual
puede generar ruido
no dice qué hacer
```

## Mejor alerta

```text
heap > 85% durante 10 minutos
y GC aumentando
o breakers cerca del límite
```

## Mala alerta

```text
cluster yellow
```

## Mejor alerta

```text
cluster yellow durante más de 10 minutos
y shards unassigned > 0
```

## Mala alerta

```text
latencia alta
```

## Mejor alerta

```text
p95 de búsqueda > 1s durante 5 minutos
para el índice crítico
```

Frase para clase:

> Una alerta buena tiene contexto, duración y acción posible. Una alerta mala solo genera ruido.

---

# 5. Severidad

Conviene distinguir niveles:

```text
info
warning
critical
```

Ejemplo:

```text
warning:
  heap > 80% durante 10 minutos

critical:
  breakers tripped > 0
  o cluster red
  o disk flood_stage
```

Otra forma:

```text
warning:
  problema potencial

critical:
  impacto real o riesgo inmediato
```

Frase:

> No todo merece el mismo canal ni la misma urgencia. Si todo es crítico, nada es crítico.

---

# 6. Frecuencia y ventanas

Una alerta necesita dos cosas:

```text
cada cuánto evalúo
sobre qué ventana temporal miro
```

Ejemplo:

```text
evaluar cada 1 minuto
mirar los últimos 5 minutos
```

Esto evita alertas por picos sueltos.

Ejemplo conceptual:

```text
Si rejected > 0 en los últimos 5 minutos
  → warning

Si rejected sigue aumentando durante 15 minutos
  → critical
```

Frase:

> Las alertas operativas deben tolerar picos normales, pero detectar problemas sostenidos.

---

# 7. Dedupe y recuperación

Una buena alerta debe pensar también en cuándo se cierra.

No basta con disparar:

```text
ALERTA: heap alto
ALERTA: heap alto
ALERTA: heap alto
ALERTA: heap alto
```

Hay que evitar tormentas.

Buenas prácticas:

```text
deduplicar alertas iguales
poner periodo de enfriamiento
avisar cuando se recupera
no repetir cada minuto si no cambia nada
```

Frase:

> Una alerta que se repite cada minuto sin aportar información nueva se convierte en ruido operativo.

---

# 8. Qué alertas pondría para este curso

Yo propondría un set pequeño, no veinte.

## Mínimas de cluster

```text
cluster_status == red
cluster_status == yellow sostenido
unassigned_shards > 0
disk watermark high/flood
```

## Mínimas de presión

```text
thread_pool_search_rejected > 0
thread_pool_write_rejected > 0
breaker_tripped > 0
heap_used_percent > 85 sostenido
```

## Mínimas de rendimiento

```text
search p95 > umbral
indexing latency > umbral
top queries lentas repetidas
```

## Mínimas de ingesta

```text
documentos indexados por minuto cae a 0
bulk errors > 0
logs de error de GELASTIC/Data Prepper/app > umbral
```

Frase:

> Mejor cinco alertas bien pensadas que cincuenta alertas que nadie lee.

---

# 9. Relación con slow logs y Query Insights

Conecta con el bloque anterior:

```text
Query Insights
  → me dice qué queries son caras.

Slow logs
  → dejan evidencia cuando superan umbrales.

Alerting
  → me avisa cuando el patrón se convierte en problema.
```

Ejemplo:

```text
Query Insights muestra queries lentas
   ↓
activo slow logs para capturar detalle
   ↓
creo alerta si hay más de N queries lentas en 5 minutos
```

Frase:

> No todo slow log debe ser una alerta. Pero si los slow logs se acumulan, sí puede ser una señal.

---

# 10. Relación con Kubernetes/OpenShift

Muy importante en vuestro entorno.

OpenSearch puede alertar de:

```text
heap
breakers
thread pools
shards
latencia
índices
```

Pero OpenShift/Prometheus debe alertar de:

```text
CPU throttling
OOMKilled
restarts
PVC lleno
latencia de disco
pod not ready
nodo con presión de memoria
```

Frase:

> OpenSearch no siempre ve la causa raíz. Puede ver el síntoma. La causa puede estar en Kubernetes: CPU limit, throttling, memoria del contenedor o almacenamiento.

Ejemplo:

```text
OpenSearch alerta:
  search latency alta

OpenShift muestra:
  CPU throttling alto

Conclusión:
  la query no cambió; lo que cambió fue la capacidad efectiva de CPU.
```

---

# 11. Notifications: buenas prácticas

Los canales deben diseñarse con criterio.

```text
warning
  → canal menos intrusivo

critical
  → canal urgente

informativo
  → dashboard/log, quizá no email
```

Buenas prácticas:

```text
no mandar todo a todos
separar canales por severidad
incluir contexto en el mensaje
incluir índice, cluster, nodo, métrica, valor y ventana
incluir enlace a dashboard/runbook si existe
```

Mensaje malo:

```text
Alert: heap high
```

Mensaje bueno:

```text
Cluster os-prod: heap_used_percent > 85% durante 10 minutos.
Nodos afectados: os-data-1, os-data-2.
Revisar GC, breakers, search/indexing load y CPU throttling.
```

Frase:

> Una notificación debe ayudar a empezar el diagnóstico, no solo asustar.

---

# 12. Runbooks

Aquí puedes meter un concepto profesional.

Cada alerta importante debería tener un runbook:

```text
qué significa
cómo comprobarlo
qué comandos ejecutar
qué riesgos tiene
qué acciones son seguras
cuándo escalar
```

Ejemplo:

```text
Alerta: thread_pool_write_rejected > 0

Comprobar:
  _cat/thread_pool/write
  _nodes/stats/thread_pool
  indexing rate
  bulk size/concurrency
  CPU throttling
  disk I/O
  merge activity

Acciones posibles:
  reducir concurrencia de bulk
  revisar ingesta
  revisar CPU/I/O
  revisar replicas/refresh
```

Frase:

> Una alerta sin runbook depende de la memoria del operador. Una alerta con runbook convierte experiencia en procedimiento.

---

# 13. Qué no hacer

Lista para clase:

```text
No alertar por cada métrica aislada.
No poner umbrales sin conocer línea base.
No usar la misma severidad para todo.
No mandar todas las alertas por email a todo el mundo.
No alertar por picos normales.
No ignorar recuperación/deduplicación.
No crear alertas que nadie sabe resolver.
No olvidar métricas de Kubernetes/OpenShift.
```

Frase:

> La mala monitorización no falla por falta de datos. Falla por exceso de ruido y falta de criterio.

---

# 14. Mini guion para decirlo en clase

```text
Ya sabemos detectar queries lentas con Query Insights y slow logs. El siguiente paso es no tener que estar mirando manualmente todo el tiempo.

Para eso usamos Alerting y Notifications.

Un monitor ejecuta una comprobación periódica. Un trigger decide si el resultado es problemático. Una action envía una notificación por un canal.

Pero lo importante no es crear muchas alertas. Lo importante es crear alertas útiles: con umbral razonable, ventana temporal, severidad, contexto y una acción posible.

Una alerta buena no dice solo “algo va mal”. Dice qué va mal, desde cuándo, con qué valor, en qué cluster o índice, y qué debería mirar el operador después.
```

# 15. Cierre de la sección

Frase final:

> Alerting convierte observabilidad en operación. Pero solo funciona si las alertas son accionables, tienen contexto y están basadas en una línea base real. Si no, solo hemos construido una máquina de ruido.




































Siguiente bloque: **Anomaly Detection**.

Aquí lo importante es no venderlo como magia ni como sustituto de las alertas normales. Es otra herramienta para un tipo concreto de problema: **cuando no sabes poner un umbral fijo porque el comportamiento normal cambia con el tiempo**.

# 1. Idea principal

Una alerta clásica funciona así:

```text
si métrica > umbral
  dispara alerta
```

Ejemplo:

```text
si heap_used_percent > 85%
  alerta
```

Anomaly Detection funciona de otra forma:

```text
aprende el patrón normal de una métrica
y avisa cuando el valor observado se sale de ese patrón
```

Ejemplo:

```text
los lunes a las 9:00 siempre hay más búsquedas
los viernes por la tarde siempre hay menos ingesta
por la noche baja la actividad
a final de mes sube el volumen
```

Frase para clase:

> Alerting clásico detecta valores altos o bajos respecto a un umbral. Anomaly Detection detecta comportamientos raros respecto al patrón habitual.

---

# 2. Por qué no basta con umbrales

Hay métricas donde un umbral fijo funciona bien:

```text
cluster red
breaker tripped > 0
disk > 90%
thread_pool rejected > 0
```

Ahí no necesitas inteligencia especial. Son síntomas claros.

Pero hay otras métricas donde el valor “normal” depende del contexto:

```text
número de búsquedas por minuto
documentos indexados por minuto
latencia media según hora del día
errores por aplicación
volumen de logs
número de procesos BPM en un estado
```

Ejemplo:

```text
1000 búsquedas/minuto a las 10:00 puede ser normal.
1000 búsquedas/minuto a las 03:00 puede ser raro.

10 búsquedas/minuto a las 03:00 puede ser normal.
10 búsquedas/minuto a las 10:00 puede indicar caída de tráfico.
```

Frase:

> Una anomalía no siempre es un valor alto. A veces lo raro es que el valor sea demasiado bajo para ese momento.

---

# 3. Qué es un detector

En OpenSearch, un detector de anomalías define básicamente:

```text
qué datos voy a analizar
qué métrica o feature voy a observar
cada cuánto la evalúo
sobre qué ventana temporal
cómo agrupo, si hay categorías
```

Modelo mental:

```text
índice de métricas / logs / eventos
        ↓
consulta temporal
        ↓
feature numérica
        ↓
modelo aprende patrón
        ↓
anomaly grade / confidence
        ↓
posible alerta
```

Frase:

> Un detector no analiza “todo el cluster”. Analiza una o varias señales concretas que tú eliges.

---

# 4. Qué es una feature

Una **feature** es la señal numérica que el detector observa.

Ejemplos:

```text
count de documentos por intervalo
media de latencia
p95 de latencia
suma de errores
media de CPU
número de rejected
número de respuestas 500
```

Ejemplo de logs:

```text
cada 5 minutos:
  contar documentos con level = ERROR
```

Ejemplo de rendimiento:

```text
cada 1 minuto:
  calcular media/p95 de search_latency
```

Frase:

> Si eliges una mala feature, tendrás un mal detector. La calidad de Anomaly Detection depende mucho de qué señal le das.

---

# 5. Anomaly grade y confidence

Dos conceptos útiles:

```text
anomaly grade
  → cuánto se parece esto a una anomalía

confidence
  → cuánta confianza tiene el modelo en esa conclusión
```

Al principio, la confianza puede ser baja porque el modelo todavía no ha visto suficiente histórico.

Frase para clase:

> Al principio, Anomaly Detection necesita aprender. No hay que esperar resultados perfectos desde el minuto uno.

---

# 6. Ejemplos buenos para OpenSearch

## Volumen de ingesta

```text
documentos indexados por minuto
```

Anomalías posibles:

```text
cae a cero cuando debería haber tráfico
sube de golpe por una tormenta de eventos
sube por reintentos masivos
```

## Errores de aplicación

```text
count de logs ERROR cada 5 minutos
```

Anomalías:

```text
pico raro de errores
errores en horario donde no suele haber carga
errores tras despliegue
```

## Latencia de búsqueda

```text
p95 search latency por intervalo
```

Anomalías:

```text
latencia más alta de lo normal para esa hora
latencia rara en un índice concreto
latencia rara tras cambio de mapping/query
```

## Queries lentas

```text
número de slow logs por intervalo
```

Anomalías:

```text
de repente aparecen muchas queries lentas
sube el coste de búsqueda aunque el tráfico sea igual
```

## Negocio/BPM

```text
número de procesos en estado ERROR
número de procesos completados por hora
número de eventos por estado
```

Anomalías:

```text
caída de procesos completados
pico de fallos
atasco en un estado intermedio
```

---

# 7. Cuándo usar alerting normal y cuándo anomalías

## Usar alerting normal

Para condiciones objetivas:

```text
cluster red
shards unassigned
disk flood_stage
breaker tripped
write rejected > 0
pod restart
OOMKilled
```

Aquí quieres una regla clara.

## Usar Anomaly Detection

Para patrones variables:

```text
tráfico normal por hora/día
ingesta variable
errores con estacionalidad
latencia que depende del uso
volumen de negocio cambiante
```

Frase:

> No uses Anomaly Detection para sustituir una alerta obvia. Si el cluster está red, no necesito un modelo estadístico para saber que tengo un problema.

---

# 8. Relación con Alerting

Anomaly Detection por sí sola detecta anomalías. Para avisar a alguien, normalmente lo conectas con Alerting.

Modelo:

```text
Detector de anomalías
        ↓
resultado con anomaly grade
        ↓
monitor / trigger
        ↓
notification channel
```

Ejemplo:

```text
si anomaly_grade > 0.7
y confidence > 0.8
durante varios intervalos
  enviar alerta
```

Frase:

> Anomaly Detection encuentra rarezas. Alerting decide cuándo esas rarezas merecen avisar a alguien.

---

# 9. Cuidado con falsos positivos

Anomaly Detection puede generar falsos positivos si:

```text
hay poco histórico
la señal es muy ruidosa
cambia el patrón por una razón conocida
hay despliegues, cargas masivas o mantenimientos
la métrica elegida no representa bien el problema
hay demasiadas categorías
```

Ejemplo:

```text
haces una carga masiva planificada
el detector ve un pico enorme
lo marca como anomalía
pero no es incidente: es operación prevista
```

Frase:

> Una anomalía no siempre es un incidente. Es una señal que hay que interpretar.

---

# 10. No empezar por demasiadas señales

Mala práctica:

```text
crear detectores para 200 métricas
sin línea base
sin saber quién las atiende
sin canales claros
```

Mejor:

```text
empezar con pocas señales importantes
validar si detectan algo útil
ajustar ventanas y severidades
conectar solo algunas a alertas
```

Señales iniciales razonables:

```text
volumen de errores
volumen de ingesta
latencia de búsqueda
queries lentas
eventos de negocio críticos
```

Frase:

> En anomalías, más detectores no significa mejor observabilidad. Puede significar más ruido.

---

# 11. Ventanas temporales

La ventana importa mucho.

Si la ventana es muy pequeña:

```text
más sensibilidad
más ruido
más falsos positivos
```

Si la ventana es muy grande:

```text
menos ruido
detección más lenta
puede suavizar problemas reales
```

Ejemplo:

```text
1 minuto
  útil para picos rápidos, pero ruidoso

5 minutos
  buen equilibrio para muchas métricas operativas

1 hora
  más estable, pero menos reactivo
```

Frase:

> La ventana temporal decide si estás mirando micro-picos o comportamiento sostenido.

---

# 12. Cardinalidad y categorías

Puedes tener anomalías por categoría:

```text
por índice
por aplicación
por cliente
por endpoint
por nodo
```

Pero cuidado:

```text
más categorías
  → más modelos/señales
  → más coste
  → más ruido
  → más complejidad
```

Ejemplo bueno:

```text
errores por aplicación
latencia por índice crítico
ingesta por pipeline
```

Ejemplo peligroso:

```text
detectar anomalías por usuario individual
por id de documento
por media_id
por campo de altísima cardinalidad
```

Frase:

> En Anomaly Detection, igual que en agregaciones, la cardinalidad importa. No todo campo categórico es buen campo para partir el análisis.

---

# 13. Cómo lo explicaría en el curso

Yo lo diría así:

```text
Una alerta clásica necesita que yo sepa dónde poner el umbral.
Pero en muchos sistemas el umbral no es estable.

La carga normal de las diez de la mañana no se parece a la carga normal de las tres de la mañana. Un lunes puede no parecerse a un sábado. Y una caída de tráfico puede ser tan preocupante como un pico.

Anomaly Detection intenta aprender ese patrón normal y señalar valores raros. No sustituye a las alertas básicas: cluster red, disco lleno, breakers, rejected. Eso sigue siendo alerting clásico.

Donde aporta valor es en señales variables: ingesta, errores, latencia, volumen de negocio o comportamiento por aplicación.
```

---

# 14. Buenas prácticas

```text
Empezar con pocas métricas importantes.
Usar señales numéricas claras.
Tener suficiente histórico.
No alertar directamente cualquier anomalía leve.
Combinar anomaly_grade con confidence.
Evitar categorías de altísima cardinalidad.
Documentar qué significa cada detector.
Tener en cuenta despliegues y mantenimientos.
Revisar falsos positivos.
Conectar a Alerting solo lo que sea accionable.
```

---

# 15. Qué no hacer

```text
No usarlo para sustituir alertas obvias.
No crear detectores sin saber quién los atenderá.
No elegir features ruidosas sin agregación.
No partir por campos de alta cardinalidad sin necesidad.
No esperar precisión perfecta desde el primer día.
No confundir anomalía con incidente confirmado.
No venderlo como magia.
```

---

# 16. Frase de cierre

> Anomaly Detection sirve cuando el problema no es “superar un número fijo”, sino comportarse de forma rara respecto al patrón normal. Es útil para ingesta, errores, latencia y señales de negocio, pero necesita buena elección de features, histórico, ajuste y criterio operativo.




























Entonces, quitando también **Prometheus/Grafana**, lo pendiente queda bastante reducido.

Ya cubierto:

```text
Snapshots / recovery
Slow logs + Query Insights
Alerting + Notifications
Anomaly Detection
Merge policies
ISM / rollover
Prometheus / Grafana
```

Lo que puede quedar sería:

```text
1. Observability en OpenSearch Dashboards
2. Reporting
3. Cierre integrador / checklist operativo
```

# 1. Observability en Dashboards

Aunque Prometheus/Grafana ya lo hayáis visto, puedes dedicarle un bloque corto a **Observability dentro de OpenSearch Dashboards**.

No como sustituto de Grafana, sino como complemento.

La idea:

```text
Prometheus/Grafana/OpenShift
  → monitorización de plataforma y métricas técnicas

OpenSearch Observability
  → exploración dentro del ecosistema OpenSearch:
     logs, trazas, métricas, notebooks, consultas, objetos guardados
```

Frase para clase:

> Grafana es muy bueno para cuadros de mando operativos de plataforma. Observability en Dashboards es más útil cuando quiero explorar datos que ya están en OpenSearch: logs, trazas, eventos, consultas y notebooks.

Qué contar:

```text
Notebooks
  → análisis guiado / documentación viva

Logs
  → exploración de logs indexados

Traces
  → si hay trazas instrumentadas

Metrics
  → métricas almacenadas en OpenSearch

Applications
  → visión agrupada de servicios/aplicaciones, si está alimentado
```

Comprobación:

```http
GET /_plugins/_observability/object
```

Mensaje importante:

> Que el plugin esté instalado no significa que mágicamente tenga observabilidad completa. Necesita datos: logs, métricas, trazas o eventos bien ingestados.

# 2. Reporting

Este lo haría rápido.

Qué es:

```text
Reporting = generación y envío programado de informes desde Dashboards.
```

Casos de uso:

```text
informe semanal de estado
informe mensual de capacidad
informe de incidencias
captura periódica de dashboards
reportes para responsables no técnicos
```

Diferencia con alerting:

```text
Alerting
  → avisa cuando pasa algo

Reporting
  → informa periódicamente aunque no haya incidente
```

Frase buena:

> Reporting no es monitorización en tiempo real. Es comunicación operativa programada.

Buenas prácticas:

```text
no enviar informes enormes que nadie lee
resumir pocas métricas importantes
separar informes técnicos de informes ejecutivos
incluir tendencia, no solo foto fija
no confundir reporting con backup ni auditoría
```

# 3. Cierre integrador

Esto sí lo haría, aunque sea corto, porque te permite cerrar el curso con criterio.

Caso:

```text
“Los usuarios dicen que las búsquedas van lentas.”
```

Recorrido:

```text
1. Compruebo health, nodos y shards.
2. Miro CPU, memoria, throttling y disco desde plataforma.
3. Miro heap, GC, breakers y thread pools desde OpenSearch.
4. Miro Query Insights para encontrar queries caras.
5. Reviso slow logs si necesito trazabilidad.
6. Analizo una query concreta con profile.
7. Reviso mapping, joins, cardinalidad, wildcard, sort, highlight, inner_hits.
8. Miro segmentos, merges y docs.deleted.
9. Si el patrón se repite, creo una alerta.
10. Antes de operación destructiva, verifico snapshots.
```

Frase de cierre:

> Operar OpenSearch no es tocar settings al azar. Es seguir un razonamiento: observar, acotar, medir, formular hipótesis, validar, cambiar lo mínimo necesario y dejar protección para la próxima vez.

# Conclusión práctica

Lo que queda de verdad:

```text
Observability en Dashboards  → 20-30 min
Reporting                    → 10-15 min
Cierre integrador             → 20-30 min
```

Y si vas justo de tiempo, yo priorizaría:

```text
1. Observability en Dashboards
2. Cierre integrador
3. Reporting solo mencionado
```
