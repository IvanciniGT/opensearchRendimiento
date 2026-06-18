
# Slow logs + Query Insights + Query profiling

## Slow logs. 

Es una funcionalidad que podemos habilitar en nuestro cluster para poder ver las queries que están tardando más de lo esperado. Esto nos permite identificar queries que podrían estar afectando el rendimiento de nuestra base de datos y optimizarlas.

    Lo que podemos configurar es que ciertas queries se guarden en los logs.
    Lo hacemos a nivel de INDICE.

En vuestro caso, el cluster corre en Kubernetes (Openshift) , los logs donde mirar eso, serían los logs de los pods de elasticsearch.

Cómo se configura? Se configura por niveles de log:

```http
PUT /MI_INDICE/settings
{
  "index.search.slowlog.threshold.query.warn": "5s",
  "index.search.slowlog.threshold.query.info": "2s",
  "index.search.slowlog.threshold.query.debug": "1s",
  "index.search.slowlog.threshold.query.trace": "500ms",
}
```

ESTO IMPACTA EN RENDIMIENTO... poco... pero algo. NO MUCHO.

Eso se puede hacer no solo para queries que busquen información, sino también para queries que generen indexación.

```http
PUT /MI_INDICE/settings
{
  "index.indexing.slowlog.threshold.index.warn": "5s",
  "index.indexing.slowlog.threshold.index.info": "2s",
  "index.indexing.slowlog.threshold.index.debug": "1s",
  "index.indexing.slowlog.threshold.index.trace": "500ms"
}
```

En muchos casos, si no tengo claro, por donde van los tiros.

Empezamos por valores altos en templates de indices... y uso warning
PUT /MI_INDICE/settings
{
  "index.indexing.slowlog.threshold.index.warn": "10s",
  "index.indexing.slowlog.threshold.index.info": "-1",
  "index.indexing.slowlog.threshold.index.debug": "-1",
  "index.indexing.slowlog.threshold.index.trace": "-1"
}

Qué me ofrecen estos logs:
- Índice afectado
- Shard afectado
- Tiempo consumido
- Query/Petición que se ejecutó
- Usuario
- Nodo
- Tamaño de la petición/respuesta

## Query Insights

Esto también pudo montarlo.. y me da más información que los slow logs. Impacta más en rendimiento, pero me da más información.

Lo puedo manejar además mediante API o mediante OpenSearch Dashboards.

```http
GET /_insights/top_queries?type=latency
GET /_insights/top_queries?type=memory
GET /_insights/top_queries?type=cpu
```

Las que más tardan.
Las que más memoria consumen.
Las que más CPU consumen.

---

Me dicen que el buscador de la app va lento.
Miro a ver que queries se están lanzado que tarden tiempo (latency) -> A investigar

Entro yo y miro las que más tardan o las que más CPU consumen... más ram consumen... -> A investigar

## Buenas prácticas:
- No usar umbrales muy bajos en slow logs, porque impacta en rendimiento.
- Cruzar información con métricas del cluster. (RAM, CPU...)
- Query insights... pesa mucho más que slow logs, así que lo activo solo cuando realmente tendo identificado problema.
- No me fijo tanto en 1 query, sino en un patrón de queries que se repiten y que están afectando el rendimiento.

- Esto identifica queries... pero no significa automaticamente que esas queries sean las que están afectando el rendimiento. Puede haber otras causas: Recursos hardware, shards, replicas, etc.

Lo único que saco es un primer sitio por donde ir tirando del hilo!

---

# Una vez que tenemos una query / Patron de queries identificadas.

2 opciones:
- Analizar la query y ver si se puede optimizar: Explain de la query, ver si hay filtros que no se están usando, si hay campos que no están indexados, etc.
- Mucho más potente... pero más complejo... es el query profiling. Esto nos permite ver cómo se ejecuta la query, qué partes de la query están tardando más, y cómo se puede optimizar.
   Esto ya no es ver el plan de ejecución potencial de la query... 
   Esto es ejecutar la query e ir anotando todo lo que hace la query realmente, en cada shar y los tiempo de cada fase de la query. Esto nos permite ver si hay partes de la query que están tardando más de lo esperado, y cómo se puede optimizar.
   Esto genera un chorizo del 15.
   El interpretarlo es más complejo => Herramientas como chatgpt o similares os ayudan mucho con la interpretación de los resultados.

---

En las queries complejas de ejemplo, lo que más impacta son el has_clild y el has_parent.
En ambos casos, intermnamete, el Opensearch las procesa de la misma forma... 
Normalmente lo primero que hará será aplicar el filtro de la query principal, y luego el filtro de la query secundaria...
Claro... eso va en bucle... la secundaria digo.
Dame todos los elementos padre con estos filtros que tengan un hijo tal que tenga estos otros filtros.
Dame todos los elementos hijo con estos filtros que tengan un padre tal que tenga estos otros filtros.

En cualquier de los casos, lo primero que se hace es la primera parte de la query:
Dame todos los elementos padre con estos filtros ... \
Dame todos los elementos hijo con estos filtros ...  / Esto genera una listas de documentos que cumplen las condiciones (filtros)

Y ahora entra en bucle (iteración) y va a ir comprobando cada uno de los elementos de la lista generada en la primera parte de la query, para ver si cumplen las condiciones de la segunda parte de la query.

Qué lista será más grande? 
En vuestro caso, padres = Container
                 hijos = Locators ******

Esto hace que el bucle de la segunda query (has_parent) tenga que iterar sobre una lista más grande que la primera query (has_child). Esto hace que la query con has_parent sea más lenta que la query con has_child.

## Profiling de queries

Para activarlo, al lanzar una query, le añadimos el parámetro `profile=true` y nos devuelve un objeto con toda la información de la ejecución de la query.

```http
GET /MI_INDICE/_search?profile=true
{
 "profile": true,
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "field1": "value1"
          }
        },
        {
          "has_child": {
            "type": "child_type",
            "query": {
              "match": {
                "field2": "value2"
              }
            }
          }
        }
      ]
    }
  }
}
```

En el json de vuelta, se incluirá un objeto `profile` que contiene información detallada sobre la ejecución de la query, incluyendo el tiempo de ejecución de cada fase, el número de documentos procesados, y más.

La query puede involucrar varios shards... y se hace el trabajo para cada uno de ellos.

Puede haber diferencias muy grandes entre shards: Mal routing

---

1. slow logs
   Configurar solo warning y a valores altos.
2. Query insights

```http
PUT /_cluster/settings
{
  "persistent": {
    "search.insights.top_queries.latency.enabled": true,
    "search.insights.top_queries.cpu.enabled": true,
    "search.insights.top_queries.memory.enabled": true,
    "search.insights.top_queries.latency.top_n_size": 10,
    "search.insights.top_queries.latency.window_size": "5m"
  }
}

// Desactivar:
PUT /_cluster/settings
{
  "persistent": {
    "search.insights.top_queries.latency.enabled": false,
    "search.insights.top_queries.cpu.enabled": false,
    "search.insights.top_queries.memory.enabled": false
  }
}

```

Esto entra en más detalle.

3. Explain
4. Profile (al sacar un profile le intuye el explain)



---


# SNAPSHOTS DE INDICES

SNAPSHOT = BACKUP de un indice o conjunto de indices. Completo o incremental.

En vuestro caso, teneís:
- Cabina de almacenamiento
- VMWare
- Kubernetes

Hay que elegir dónde hacer los backups.

Puedo hacer el backup en distintos sitios... con distintos procedimientos, implicaciones y velocidades.

De qué quiero hacer backup?
 - VMs NO : redesplegamos cluster               
 - Despliegue: NO : redesplegamos cluster       Velero! KUBERNETES
 - INDICES
   - replicas? son backups o no? NO SON BACKUPS
     Replicas me dan HA: Tener acceso a la infromación cuando hay un fallo HW o SF
     Backups: Recuperación ante desastres.  Si ocurre un desastre, el desastre se replica a las réplicas.

Lo normal es que los backups (snapshots) los haga en un almacenamiento independiente.
En ocasiones, si los datos (índices ) los guardo en un volumen de una cabina, me puede ser mucho más eficiente hacer el backup del volumen completo a nivel de la cabina.

NFS puede ser una buena forma. S3 es una forma estupenda.
Almacenamiento Ficheros         Almacenamiento de Objetos

El snapshot guarda:
- Segmentos (datos)
- Mappings
- Settings
- Alias
- Shards
- Información global del cluster
  {
    "include_global_state": true
  }

    OJO al include global state: 
        - Guarda templates de indices, usuarios, roles, etc.
  
Los snapshots no solo sirven para copias de seguridad... también para migrar información entre clusters.

Clave: PROBAR LOS SNAPSHOTS

Backup / Snapshot NO PROBADO = NO BACKUP

RPO = Cuánto dato puedo perder   -> La cantidad de snapshots (24 horas... 1 hora)
RTO = Cuánto tiempo puedo tardar en recuperar el dato

Definir una política de retención.

Hay que tener en cuenta la naturaleza del índice:
- Logs -> Vamos rotando. Una vez congelado ya no hay que hacer backup. Lo que hay que hacer es un snapshot de los últimos 7 días, y luego ir borrando los snapshots antiguos.
- Contenidos -> Snapshots continuos.

Cuánto tardo en reindexar? Si tardo poco... quizás aplico la misma politica de las VMs o el cluster.

---

# Auditoría

Guardo eventos / Lo trato como logs.

Si es auditoría, las consultas son pocas.
    En este caso, prima la comodidad de trabajo antes que acelerar las búsquedas.

    Es el tipico caso donde interesa una politica de ciclo de vida del tipo:
        Cada semana un índice:
            - Voy congelando índices y mergeando a 1 segmento -> Backup y me olvido de eso para el resto de la vida del índice.
            - Al mes/3 meses, los cierro/borro

           Los backups van a tardar muy poco... serán archivos pequeños.
           Mientras está vivo puedo ir haciendo incrementales.
           OJO A LA POLITICA DE MERGE. QUE NO SEA POR TIER. Y QUE SEA POR FECHA Y TAMAÑO. 

Los podeis hacer por api:
```http
PUT /_snapshot/mi_repositorio/<id>?wait_for_completion=true
{
    "indices": "indice1,indice2",
    "include_global_state": true
}

GET /_snapshot/mi_repositorio/_all

GET /_snapshot/mi_repositorio/<id>

POST /_snapshot/mi_repositorio/<id>/_restore
{
    "indices": "indice1,indice2",
    "include_global_state": true,
    "rename_replacement": "indice_restaurado",
    "rename_pattern": "indice"
}

```

---

# Alertas:

   Monitor
    v
    Ejecutar una consulta con una periodicidad
        v
        Trigger (condición)
            v
            Acción (email, webhook, slack, etc.)

Problema... que solo puedo trabajar con datos de los que ve el OpenSearch.
    Hay datos que el Opensearch no ve... y no es suficiente en un entorno de producción.

En paralelo con esto, tendría que montar una monitorización adicional:
- Consumo RAM nodos
- OOM Kill en kubernetes

Esto lo configuro en PROMETHEUS/GRAFANA.. que también genera alertas... más potentes que las de OpenSearch.
Y de paso.. ya puedo meter ahí el resto de métricas que me interesen de OpenSearch.

    Las imágenes/Charts de OpenSearch vienen con serviceMonitors para Prometheus de serie.
    Pues.. ahí en el grafana es donde quiero definir eso.

Esto no serviría si tengo por ejemplo un índice con métricas de el tamaño de cola de un rabbit.
Promotheus / GRafana no pueden hacer una consulta al indice de Opensearch.

Pero... lo normal es que en el despliegue de rabbit, monte su propio serviceMonitor a Prometheus.. Que lo tengo oficial y de serie.
Le manda huevón de datos al Prometheus. Y uso un tablero de grafana oficial.. y me importo un conjunto de alertas en el AlertManager de Prometheus. Y ya tengo alertas de RabbitMQ.


Las alertas de Opensearch tienen más sentido para datos de negocio!
Tiro una consulta y mira ver si en los últimos X minutos se han buscado más de 500 veces el mismo término.. y que me mande un email con los términos de búsqueda más usados.

Sobre datos SI... Sobre monitorización/Observability NO

---




# Anomalías (TIMESTAMP-> LOGS/METRICAS) 

En las alertas hay una condición FIJA que se evalua para mandar una notificación.Las 

Anomalías funcionan de otra forma.

Se va entrenando una IA (modelo). Va aprendiendo de lo que yo le diga: 
- Las búsquedas que se van haciendo...
- Los valores de CPU

Le doy un índice... y aprende los patrones que se repiten en el tiempo:
- Los lunes siempre hay más búsquedas
- Los jueves por la tarde también hay más búsquedas
- En general en las mañanas hay más busquedas que en las tardes.

Los patrones no los defino yo... los va identificando la herramienta.
Si un dia no se cumple un patrón -> ANOMALIA! -> ACCION (no se define mediante una condición)


Esto con datos de negocio tiene mucho sentido.