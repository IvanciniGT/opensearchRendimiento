
Título
Descripción
Sinopsis


Título + Descripción + Sinopsis

---

Habrá campos muy concretos de FILTRADO.
Y luego hay campos de búsqueda textual.

La mayoría de las búsquedas serán de tipo textual... y en algunas (quizás incluso un % alto) pueden aplicar filtros.

    GOOGLE: 
    
    [                                       | BUSCAR ]


---

Búsquedas semnánticas (Modelos de IA)


OpenSearch indexa documentos JSON... y luego permite búsquedas.
Pero tanto ingesta como búsquedas se realizan por peticiones HTTP

Kibana / Opensearch Dashboards
Esto es una app WEB que aporta funcionalidades de búsquedas / análisis de datos sobre datos que tengo indexados en un cluster Opensearch.


GET http://RUTA_CLUSTER:PUERTO/_cluster/health

---

name               node.role master heap.current heap.max heap.percent ram.percent cpu load_1m disk.used_percent
opensearch-nodes-1 dim       -             1.4gb      4gb           36          91  -1    5.23             25.13
opensearch-nodes-2 dim       -             411mb      4gb           10          78  -1    0.20             25.13
opensearch-nodes-0 dim       *             1.2gb      4gb           31         100  -1    0.48             25.13

Role "dim"?
    NO... roles:
        d   data
        i   ingest
        m   master

heap.max            Total de heap que puede usarse (4Gb)
heap.current        Lo que hay en uso de esos 4Gbs
heap.percent        (heap.current/heap.max) * 100

    Es malo que esté alto? El problema es que este valo no podemos medirlo de forma aislada.
    La cache si... puedo entrar aqui y sacar una foto... del estado actual... y no cambia mucho con el tiempo

    El heap hay que mirarlo en perspectiva... por el comportamiento de la JVM y bendito recolector de basura.
    Aqui hay un dato significativo en vacio: MINIMO.
    Según vamos haciendo operaciones va generando "mierda" BASURA! y usando heap. Hasta que :
        - Tiene mucho rato ocioso
        - Ya no le queda hueco
    En esos momentos puede entrar el GC (GARBAGE COLLECTOR) y libera (tira la basura a la basura)
    El mínimo es lo que se está guardando en Opensearch (propiamente) en CACHE.
        - Lucene tiene caches de INDICES (shards) ... ficheros de segmentos... esos los gestiona el Sistema operativo
          - > RAM del Sistema Operativo
        - OpenSearch guarda / tiene otras caches:
          - Caches de queries
          - > RAM (HEAP JVM)

    heap        max
    293.3mb      4gb

    Esto significa que mi cluster puede perfectamente sobrevivir con 300mb de RAM (HEAP)
    A partir de ahi, necesito espacio para ir dejando basura.
    Cuanto menos tenga, más rápìdo tiene que entrar el GC
    Cuánto más rápido entre el GC menos rendimiento (La CPU se la come el GC)
    Si hay demasiada poca heap... puede llevar a entrar en bucle...
        Entra librera bytes (kb) y nada mas que sale ya necesita liberar poque no entra ahi lo que tiene que meter... Y AQUI EL SISTEMA MUERE !

    De qué depende el espacio que tengo que configurar de HEAP para basura (Sobrante)? Del uso del sistema.
    Más usuarios simúltaneos usando el sistema, más basura simultanea.
    Secuenciales me dan igual... cuando acabe uno tiro su basura y ya hay hueco para otro.
    Si llega un momento que no hay hueco para más basura... GC entra... pero si no consigue liberar... sistema muere... GC al 100%
    A las 2 o 3 horas... puede salta un OUT OF MEMORY EXCEPTION de la JVM.
    Pero a su vez, de qué depende la cantidad de usuarios / peticiones en paralelo? DE CUANTA CPU TENGO DISPONIBLE
    Si tengo mucha CPU, puedo atender a más usuarios -> EXIGE MAS RAM
    Menos CPU = Menos capacidad de procesamiento paralelo... -> NECESITO MENOS RAM (Iré generando menos basura)
    El objetivo es encontrar un buen ratio CPU/RAM... Dicho de otra forma...
    Buscar una cantidad de RAM que no pueda llenarse con la cantidad de operaciones que mi cpu pueda absorber. -> MONITORIZACION
    En muchos casos, sobredimensiono CPU (request vs liimit en kubernetes.)
    Te garantizo poco.. si hay pilla más.

ram.percent         Porcentaje de la RAM del NODO (máquina física, virtual o un contenedor)
    Es malo que este valor esté muy alto? 95 - 100
    ESTO ES GENIAL! Quiero todas las máquinas al 100% de RAM
        RAM = heap + caches + código (poco) + información de los procesos de SO (despreciable)
              -------------
              Esto es lo gordo.

              Cache... quiero que complete siempre al heap, para llegar al 100%

              Si no saturo la RAM... es que tengo el sistema hipersobredimensiaonado


voyager_content_system_atp_site_atp_en_gb_index_0                0     r      STARTED  612305 142.7mb 10.128.4.11 opensearch-bi-masters-2
voyager_content_system_atp_site_atp_en_gb_index_0                0     p      STARTED  612306 142.4mb 10.131.2.19 opensearch-bi-masters-1
voyager_content_system_atp_site_atp_en_gb_index_0                1     r      STARTED  644167   148mb 10.128.4.11 opensearch-bi-masters-2
voyager_content_system_atp_site_atp_en_gb_index_0                1     p      STARTED  644167 147.8mb 10.130.2.8  opensearch-bi-masters-0


1.250.000 / 3 = 475.000    140 mb -> 110mb

Si junto los shards son 300mb... Podría plantearme tenerlo en un solo primario con 2 réplicas (para consultas)
    Cuango haga POST (ingesta), devirle ese parámetro: wait_for_active_shards = 2