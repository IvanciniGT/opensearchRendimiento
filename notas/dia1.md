
# Fundamentos de monitorización en Opensearch

En esta formación vamos muy orientados a "mejoras de rendimiento".
- Cómo se reparte/gestiona el trabajo dentro del cluster
- Que elementos tienen que ver con esto del "rendimiento"
- Métricas
- Cómo preparar una linea base antes de aplicar cambios

## Mejoras de rendimiento

Operaciones de más alto nivel: 

- Mejora de tiempo de búsqueda de resultados <- Pantalla de búsqueda
- Mejora de tiempo de cálculos agregados     <- Dashboard
- Mejora de tiempo de indexaciones
- Optimización de recursos (RAM, CPU, Almacenamiento)

Hay muchas tareas por debajo:
- Recepción de documentos
- Analisis de los mismos
- Indexación
- Gestión de segmentos
- Replicación
- Queries
- Cálculo de agregados
- Ordenación
- Paginación

# 2 conceptos separados:

- Latencia de una operación: Lo que tarda en hacerse una operación en condiciones ideales.
- Throughput: Cantidad de operaciones paralelas que somos capaces de hacer:
  - Cargas por unidad de tiempo
  - Búsquedas por unidad de tiempo

A veces me interesa mejorar el tiempo que tarda una operación SUELTA, AISLADA!
Otras veces lo que necesito es que ese dato (tiempo) no se degrade cuando:
- Más usuarios paralelos
- Picos de trabajo
- Más datos

# Estabilidad:
Capacidad del sistema para mantener un comportamiento predecible.

---

# Qué cosas pensáis que pueden afectar al rendimiento?

- Recursos Hardware
  - CPU
  - RAM
  - IO: 
    - Almacenamiento
    - Red

Todo esto afecta realmente al rendimiento? SI
Qué margen de maniobra tengo aquí? EN GENERAL POCO!

El objetivo no va a pasar en principio por mejorar la capacidad del Hardware... Es CONTEXTO!
El objetivo es optimizar el uso de ese hardware... hasta donde de sí... A veces.. no hay ya optimización posible... y toca subir!

## Para que usa un programa en general y OpenSearch en particular, los recursos de HW?

### CPU

  - Cálculos
  - Indexación 
        -> Transformación
  - Ordenación... el tener los datos indexados, evita ordenaciones? NO
    - Los índices nos ayudan muuucho a la hora de encontrar datos.
    - Ahora bién.. para ordenarlos... teóricamente si:
      - 1. Que estén ordenados como me interesa en el índice.
           En general lo van a estar? No lo se... depende la funcionalidad que quiera conseguir.
            - Quiera mostrar los datos ordenados por el campo X
            - Quiera mostrar los datos ordenados por relevancia
      - 2. Si los datos están guardados en varios índices paralelos... hay que unificar... y eso lleva curro!
           No tanto como el anterior (punto 1) 
    - Las ordenaciones, que son de lo peor de lo peor:
      - Chupan huevon de RAM
      - Hay muchas operaciones que hacen ordenaciones de forma encubierta

  En general la cpu no va a ser el factor limitante.

### RAM:

Tener los datos de trabajo:
    - Los datos que vamos ordenando
    - Los datos que salen de una query a devolver a usuario
    - Los datos que vamos agregando (cálculos)
Caché:
    - Índices
      - token/elemento a indexar
      - ubicación
        - Ambos crecen igual?
          - A priori, una vez estabilizado un sistema, las ubicaciones (documentos donde está ese token) se van dando de alta a mucho más ritmo que los tokens.
          - Se guardan 1 vez los tokens? (Ver persistencia)
            - La hueva!
    - queries / planes de ejecución
Buffers entrada / salida
    - Si tengo muchos más ficheros, más fragmentación... y por ende los términos aparecen muchas más veces,
    tendré ficheros en total que ocuparán más volumen .. y necesitaré más buffers
    Quién gestiona esos Buffers? SO.

        Contenedor: ElasticSearch
            4Gbs RAM
            Puedo poner la JVM con 4 Gbs de RAM? Tengo que dejar sitio para los buffers...
            En paralelo tenemos cache de lecturas de archivo (Gestionada por el SO)

### Almacenamiento:

Lucene guarda esos archivos de segmento.
Lo ideal que sea una operación one-way: Llegan datos al lucene.. los guarda a disco y no se vuelven a leer en la santa vida! Entonces, para qué los guardo? Por si hay que leerlos.
Vamos a conseguir esto?
- Va a depender de muchas cosas.
  - De la cantidad de datos
  - De las queries que se hagan
  - Del diseño de índices que tenga
  - Del mantenimiento que lleve a los índices.



Persistencia de los índices se hace dónde?
HDD

El uso de esos índices.. si lo hago desde HDD... apaga y vamonos.
Quiero los datos precargados en RAM -> CACHE


### OS corre sobre JVM

Dentro de la JVM definimos varias zonas de RAM.
Una de ellas es el HEAP.
El HEAP es donde:
- Tener los datos de trabajo
- Caché



---


# Lanzar una query al Opensearch

Petición HTTP .. y que le mando en el body:
JSON con el detalle de la query.
JSON = TEXTO (String)
    -> Parsearlo = Análisis sintactico + validación de sintaxis.
    -> Validación del metadata: Nombres de índices, existen los campos? de qué tipo son?
       Las operaciones que me están pidiendo son aplicables sobre esos tipos de datos?
    -> Calcular un plan de ejecución!

Hay mucho trabajo ahí.
Si me tiran 25 veces la misma query.... coño.. si ya lo he hecho una vez... aprovechemoslo!


---


# INDICE 

En ElasticSearch/Openseach:
Un conjunto de shards

## Shard

Un shard es una instancia de Lucene.

Y que contiene? Conjuntos de documentos + índices que creo para acelerar búsquedas

Y cómo se estructura un shard? Cómo guarda un lucene sus datos? En archivos llamados Segmentos.
Cuántos? de 1 a Torpecientos.
Si lo sé.. lo puedo mirar.
En un fichero de segmento cuántas veces aparece un término de búsqueda? Complejo.
Los archivos de segmento en ES no son como los archivos de BBDD tradicional (a los que accedermo mediante acceso aleatorio). Se tratan mediante acceso SECUENCIAL.. Lo único que hago en ellos es append()

No es lo mismo tener un Shard con un archivo de segmento que 1 shard con 20 archivos de segmento.
No es lo mismo un archivo de segmento fragmentado que no fragmentado.

> Tenemos control de la fragmentación que se va generando dentro del lucene? NO

Eso depende de qué y como se cargue en el sistema. Y eso depende del uso.

Lo que si puedo es ir reescribiendo esos archivos... de forma que vaya reduciendo fragmentación.. y vaya consolidando archivos de segmento

Más fragmentación y más archivos de segmento -> Más espacio en disco
                                             -> Más tiempo en carga de índices
                                             -> RAM? Ya ves truz!

---
Lo primero que necesitamos es entender cómo está funcionando ElasticSearch en general.
Lo primero que necesitamos es entender cómo está funcionando nuestro ElasticSearch:
    - Plano teórica
    - Mediante monitorización

Una vez entendido esto.. y tiene que ver mucho con la funcionalidad y el USO, miro qué tal es el comportamiento del sistema:
- Vacio
- Carga sostenida (real)

Y entonces me planteo, qué me interesa mejorar?
ESTO NO ES.. EL ES va lento!
Qué va lento? Comparado con qué? Qué es necesario mejorar?
Cuándo? Cuánto?

Hay veces que por mejorar el rendimiento de una operación, empeoro el rendimiento de otras operaciones.
En ocasiones puedo conseguir mejoras parciales cambiando 4 parámetros (raro)
En ocasiones tengo que cambiar código/modelo/arquitectura
En ocasiones tengo que cambiar funcionalidad


---

# Analizar una petición.


## Ingesta

Lanzo petición HTTP GET.... URL : https://VIPA:9200
1. El cluster recibe la petición y es ENCOLADA!
2. Un hilo (Execution pool) toma esa petición de la cola y la procesa.
   > La petición tarda mucho en comenzar a procesarse -> El pool de ejecutores es muy bajo... hay que subirlo
   > Pero esto no va a pasar en el primer análisis (carga vacía)
3. Se procede a parsear y analizar la ingestion... lo que tardará un tiempo... el que sea!
4. Se aplica el algoritmo de routing y se determina el Shard
5. Se manda a los lucenes gestores de ese shard (primerio + replicas) a que indexe < CPU (generamos el índice invertido)
6. Cuando se contesta al cliente OK?
      Depende de la política de la query! 
        - Por defecto, el coordinador responde cuando todos los lucenes han acabado
        - Pero eso lo puedo cambiar a nivel de query:
           POST     /logs-enero/_doc?wait_for_active_shards=all
            {SUPER JSON con el registro} 
        - A nivel del índice:
          - index.translog.durability= request | async
            La operación se reconoce cuando el log transacciones se ha sincronizado a disco 
            O si el trabajo se responde con OK antes de la persistencia a disco 

## Consulta

Lanzo petición HTTP GET.... URL : https://VIPA:9200
1. El cluster recibe la petición y es ENCOLADA!
2. Un hilo (Execution pool) toma esa petición de la cola y la procesa.
   > La petición tarda mucho en comenzar a procesarse -> El pool de ejecutores es muy bajo... hay que subirlo
   > Pero esto no va a pasar en el primer análisis (carga vacía)
3. Se procede a parsear y analizar la query... lo que tardará un tiempo... el que sea!
4. Planificación de la query. Plantear la estrategia para procesarla.
   > Querré echarle un ojo... a ver si tiene sentido o me gustaría (huele) que puede haber una mejor opción... raro!
5. Se determina que índices se usan en la query... y en qué shards puede haber datos (routing) 
   Más shards primarios   -> Más queries en paralelo (a priori menos tiempo).. pero luego hay que consolidar resultados
   Menos shards primarios -> Menos consolidación... eso si.. más datos por shard... que puede tardar más.
   El extremo sería 1 shard -> Elimino la consolidación

    Qué pesa más?
        - Que un nodo (fragmento=shard) me devuelva 10 veces más datos
            Sube mucho el tiempo por buscar en un solo nodo muchos más datos? NO... esa es la magia de los índices.. y su algoritmo
                de O(log(n))
        - Tener que buscar los datos en 3 shards en lugar de en 1
            Sube mucho el tiempo de consolidación a más shards (SI) ... los sorts son malignos y perniciosos... aunque....
                Hay 2 estrategias de sort en base a la forma en la que quiera obtener los resultados:
                    - Si necesito todos los datos de una?
                       - Necesito esperar a tener todos los datos de todos los nodos. Después reordenar entre si todos los datos de todos los nodos. Esta ordenación es más jodida
                    - Si estoy paginando que va a pasar? 
                       - Necesito esperar a cúantos datos de cada nodo? El tamaño de página
                       - Y cuantos ordeno? Esos que es un subconjunto pequeño.
                              Esta ordenación es más simple

                    Elijo yo si quiero tener paginación o no? NO 
                    Quién lo decide? LA QUERY.
                        Dame los contenidos del mes de abril... que vea a ver cual me interesa, que hablen de gatitos. <- PAGINACION
                        Dame los contenidos del mes de abril, que quiero ver cuantas horas de reproducción suman <- PAGINACION? NO

6. Se lanza la búsqueda en cada shard. Es procesada por Lucene.
   6.1. Lo primero es mirar si tiene el índice en RAM? A priori lo tendrá? En el caso más favorable que estamos midiendo SI
        En un caso general ? NPI
   6.2  Si no lo tiene en RAM? Preguntarse si tiene sentido (si le trae cuenta) cargarlo en RAM. De qué dependerá?
        - Del tamaño del índice.. aunque no debería condicionar mucho. A priori si un shard no entra en RAM... mal shard!
        - Si hay hueco. Hay hueco? Si no hay hueco:
          - Hacer hueco (tirando otros índices/shards que estén cargados en ram)
            Es peligroso... si este índice/shard o se usa mucho... posiblemente no interese evacuar uno que si se usa mucho 
            para cargar este 

          - Hacer la búsqueda en disco => RUINA!
            Hacer fullscan sobre todos los ficheros de segmento. 
        Si decide cargarlo:
          - Leer todos los ficheros de segmento     \
          - + Consolidar en RAM                     / Esto lleva bastante tiempo
                                                       Cómo evoluciona ese tiempo con el paso del tiempo.
                                                        A más datos... peor.. ficheros de segmento más grandes... más tiempo de lectura
                                                        Más tiempo de consolidación.
            Escenario óptimo para cargar un índice/shard de disco? Tener un solo fichero de segmento sin fragmentación.
            Cuánto cuesta hacer eso? Bastante! 
            Cuándo trae cuenta hacerlo? Cuando ya no voy a modificar el shard. Cuando lo cierro.
   6.3 Devuelve el resultado

7. Se va recibiendo poco a poco en el nodo coordinador... el que recibió la petición
8. Y cuando tenga suficientes (o todos) los datos, éste los consolida.
9. Si hay que aplicar agregados se aplican
10. Devolvemos los datos al cliente

     EN LA PRUEBA DE LINEA BASE qué concepto mido realmente?
     - Análisis de la query / validación            ESTO ES DESPRECIABLE! (en general)
     - Preparación del plan de ejecución            ESTO ES DESPRECIABLE! (en general)
                Si la query se hace continuamente (cada segundo... o menos... revisar el impacto) 
                    Ejemplo de query que se hace de continuo como me descuide? DASHBOARDS!
     - Búsquedas sobre ram     <- Procesamiento / Estructura del índice / query
     - Tiempo de consolidación <- Estrategia de routing

     Me olvido de:
        - Estado de sobrecarga de las máquinas
        - Tiempos de lectura en RAM de shards

     Esto mide los recursos de la máquina? Se ve afectado por los recursos de la máquina? NO...
     La máquina tiene los recursos que tiene.
     - Si el tiempo no me gusta:
       - La estrategia de routing es adecuada?
       - El plan de ejecución es adecuado?
       - La estructura del índice es adecuada?
       - La query está bien planteada/puede simplificarse?
       - Subo hardware? GANO si subo hardware?
         - Subo CPU, gano? Por velocidad de la CPU.. poco... Y metiendo más CPUS? Tampoco. Al final tengo que hacer el sort
           - Más cpus me dará más trhoughput (atender más peticiones en paralelo)
         - Subo RAM, gano? En la prueba de linea base nada.
         - Subo disco? o más rápido

La recomendación oficial en Elastic es que un shard esté entre 10-50 Gbs




---

# Cómo analizamos una petición que no nos gusta como está yendo en el cluster de Elastic?

> Lo primero establecer una linea base.

Qué es y cómo lo hago?

Lo que interesa es averiguar el tiempo mejor posible (en las mejores condiciones posibles) de esa operación que quiero investigar.

Para ello:
- Teniendo una instancia (cluster) que esté en reposo.. donde solo lanzo esa operación.
Cúantas veces? La hueva: 50-100 veces

Por qué?
- Eliminar Ruido (máquina, red)
- Cargar caches y buffers
- Calentar el JIT de la JVM (que le lleva rato)
  JAVA es un lenguaje compilado... que se compila a otro lenguaje llamado byte-code
  Y byte-code es un lenguaje interpretado.. Se "compila" en tiempo de ejecución.
  Y la JVM guarda un historial (caché) de compilaciones (Eso es el proyecto HotSpot del JIT. Java 1.2)

Y mido.. y hago media... usando posiblemente Percentil 95. Quito las mediciones más altas 5%... ruido!
Si ese tiempo me gusta, el problema no lo tengo tanto en principio en el diseño... aunque seá necesario mirar más.
Si ese tiempo no me gusta, el problema posiblemente lo tengo en diseño (indices, query...)

## Routing:

Algoritmo que determina en que shard de un índice se va a guardar un dato... o se ha guardado un dato.

### Shards

Un índice es una colección de shards.

INDICE: Las facturas de enero.

Puedo tener varios shards primarios en ese índice.
Cada shard primario contiene un subconjunto de las facturas de enero... excluyentes entre si.
Una factura estará solo en un shard primario.
En cuál? Depende del algoritmo de routing:
- Dia       \
- Semana     \
- Cuantía     \  Cuando la gran mayoría de búsquedas contenga como filtro siempre uno de estos campos
- Cliente     /  Problema? que se llene un shard más que otro
- Pais       /             que no esté aprovechando las capacidades de escritura en paralelo

- Aleatorio! ESTE ES EL MAS USADO... en general me ofrece reparto óptimo de carga de trabajo
  A cada shard le va la misma cantidad de datos 
                Problema? Al hacer una búsqueda potencialmente los datos estará en qué shard? EN CUALQUIERA!

En general, cuándo creo más shards primarios? siempre comienzo con 1.
    Si no da a basto en escritura. Si cargo tantos datos que un nodo no da a basto... reparto... más primarios

Luego están las réplicas que me ofrecen? HA del dato, paralelismo en lectura

Si tengo un sistema que busca más que escribe -> más réplicas
Si tengo un sistema que escribe más que busca -> más primarios

-> Logs                                 <- ESCRITURA        más primarios
-> Gestión de contenidos (búsquedas)    <- CONSULTAS        más réplicas

Teniendo en cuenta: 
Más réplicas impactan adicionalmente en los tiempos de escritura. Más réplicas, más tiempo... 
    (aquí hay sus trucos: el número de shards en los que debe haber escrito antes de darme confirmación (Commit))


---

Ocupa lo mismo un índice en disco que en RAM?
Ni parecido.
- En RAM Está consolidado.. por lo que debería ocupar menos (Básicamente, los términos están solo una vez... mentira.. si hay varios shards siguen duplicados en cada shard... lo que quito es la duplicación intra - shard)
- Los datos ocupan distinto en HDD y en memoria... donde ocupan más? EN RAM!