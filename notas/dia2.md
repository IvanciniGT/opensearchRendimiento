# Uso de memoria en Opensearch

Tengo índices con 10G de datos en disco.

> Cuánta RAM requiere el Opensearch?

Como poco más de 10G.
Eso sería para tener índices en RAM....   > La consumiría Lucene... y donde se guarda eso en que RAM? 
- En el HEAP DE JAVA? NO
- En filesystem cache del Sistema Operativo
Pero Opensearch usa la ram para más cosas:
- Resultados temporales de queries antes de devolver a cliente
- Ordenaciones
- Transformaciones de ingesta
- ...

Con 10G nos va a servir? Complicao. Apunta 15!
Si quieres tener todo en RAM... quizás no es necesario.

Si tuviera 200Gb de RAM... los usaría para algo el OpenSearch? o he sobredimensionado?
Se los traga enteros (cachés)
Las cachés no tienen límite.

Si tuviera 2Tbs de RAM... pa' dentro!

NO HAY LIMITE EN LA CANTIDAD DE RAM QUE ESTAS HERRAMIENTAS PUEDEN COMER.

Tengo que calcular el mínimo razonable... le hecho un poco más!

---

# Tipos de nodos en ES/OS

No tiene sentido esto.. lo que ahay son FUNCIONES (Roles) que pueden ejecutar los nodos.
A cada nodo le digo el tipo de funciones (ROLES) que puede ejecutar.

Cuando yo asigno roles a nodos... acabo creando TIPOS DE NODOS en mi cluster.

Roles:
- Master            (al menos 3.. aunque solo 1 ejercer de maestro.. los otros 2 están por si las moscas)
                    tareas de gestión a nivel de cluster.
                        - Monitorización de los nodos
                        - Determinación de donde se ubican shards
                        - ... 
- Data
  - Tienen lucenes (almacenan shards)
  - Osea:
    - Guardan datos (Indexación)
    - Búsquedas 
- Ingesta
  - Transformaciones de datos previas a su indexación
- ML
  - Dodne corren modelos que usaremos para temas de IA más avanzados.

- Coordinador ( No es un rol en si.. no se explicita..)
  Es la función básica de recibir peticiones y contestar al mundo... Y cualquier nodo puede ejercerla...
    No se puede desactivar, ni activar. Simplemente todo nodo tiene esta función por existir.




----

Voy cargando logs
    Los meto en indices por fechas (meses)
    Los indices vigentes (mes en curso) los meto en unos data calientes (NVME)
    Según pasa el tiempo los muevo a otros tipos de nodos con peor almacenamiento
        - Al mes -> warm
        - A los 6 meses -> cold

Los índices en los que más busco -> hot             Mis almacenamiento en ambos
Los índices en los que menos busco -> cold

Limito la rotación a fichero/ram
En los hot no tengo muchos indices.. y el ratio de uso de cache mejora
En los cold tengo muchos indices.. y el ratio de uso de cache empeora.. hay más movimiento (disco-> RAM)

# Consulta de contenidos

"Potencialmente" me pueden interesar contenidos de hace 10 años.
La probabilidad de que prefiera un contenido más actualizado es grande!

    Nuevos      --->        Viejos

    Y en el formulario                  [√] Incluir datos más antiguos

---


PASO 1: Identifico algo que me escuece! Carga no da a basto.. query tarda mucho
PASO 2: Mido en limpio -> Establezco linea base
  Monitorizo:
    Tiempo total de la operación
    Metricas de Hardware en cada pod
      CPU
      RAM
      I/O HDD
      IO RED
    Query? 
      Plan de ejecución
      Analizar el plan de ejecución frente a la query
      Identificar Shards
        De los shards su tamaño
          


   * Pregunta... para la linea base.. me hacen falta muchos datos? 
      De 500 datos a 5M de datos...
      El hacer la búsqueda cambia mucho? NO
      La ordenación/agregados si pueden cambiar mucho

DESPUES:
  - Si el dato no me cuadra:
    - Query: Problemas?
      - Recursos físicos? No debería!
      - Política de índices: La query, trabaja con muchos/pocos datos? están en un índice? Se pueden quitar datos de índice?
      - Estructura del índice : Campos que no se indexen de la forma adecuada
          ^
          v 
      - Query
      - Política de la query:
        - Necesito esperar a todos los resultados? OVERHEAD ENORME!
        - O en cuanto tengo 4-200 puedo responder / Paginación
    - Indexación: Problema
      - Tamaño del documento afecta.. pero aquí no hay margen de maniobra! Me sobran datos?
      - Procesamiento que le meto al indexar (analizador , stremmer)
  - Si el dato me cuadra:

PASO 3: El problema es que hay muchas cosas que pueden estar jodiendo... Necesito formular hipótesis.
PASO 4: Compruebo esas hipótesis que he planteado.. y a ver que sale.


---


PROBLEMAS GENERALES DE OPTIMIZACION:
- Tengo 20 campos indexados que no se usan para nada!
  - Más espacio en HDD
  - Más espacio en RAM -> Menos espacio para caché de los segmentos.
- 