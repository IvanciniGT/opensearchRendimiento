3 nodos
cpu : 4
ram: 4/6

Los volumenes de datos están en nfs
Ese nfs son 2 discos rotaciones en espejo (3Tb)

He hecho pruebas de ingesta con 1, 2 y 3 primarios + 1 réplica.

1º no había mejora en rendimiento entre poner 1, 2 o 3 shards primarios.

El disco da unos 150 Mbytes/seg
El problema no era disco -> RED (1Gbit) -> máximo teórico de transferencia? 125 Mbytes/seg
He pensado que la red era quien saturaba.
El problema es que tenía configurados poco ENVIADORES de datos...

He subido ENVIADORES... 36 cores. HEMOS EXPLOTAO pero no el elastic. BALANCEADOR DE CARGA QUE MANDA DATOS A KUBERNETES: 
    8.367 docs/segundo * 400bytes = 4.000.000 = 4Mb/Segundo

Montar un nuevo cluster con 1 core y almacenamiento en local

Workers	    1 primario	    2 primarios	    3 primarios
    4	        850	        1.920	        2.080

En vuestro caso, habia muuchos índices muy pequeños en ingesta (LOGS)
1 primario / 2 réplicas si hay mucha lectura.
1 primero 1 réplica será lo normal. y muy poca rotacion de indices 

Los grandes a 3 primarios + 1 réplica.

Peor posiblemente al subir CPU estemos bien

32518762 máximo documentos en un índice de logs semanal: 4 Millón al día
20.6gb
En 10 horas -> 400.000 a la hora = 6666 docs/min... 100 docs/seg

No obstante no está de más partirlo en 3 primarios + 1 réplica.. para no saturar máquinas

670 bytes/doc * 100 = 67.000 b / segundo = 67 Kbs / segundo
                                            150Mb/segundo

Ni saturo red, ni saturo disco.

---

Ahora mismo, en cuántos índices estamos grabando? 10

Y las búsquedas de este cluster son muy simples: 
    FECHA
        Texto: ERROR

En un cluster como este:
- RAM/HEAP Mínimo 1.5Gb / 2Gbs  
- Filesystem cache igual -> Pod 4Gbs  req y limit

CPU Limit = 2,3,4

SHARDS PRIMARIOS? (réplica siempre 1)
    1 SI NO 1
    3 SI ES MUY GRANDE Y HAY MUCHA INGESTA

---

En el cluster de contenidos:

RAM HEAP 2-4
Filesystemache: A nivel de pod req 6-8 = limit

CPU Limit = 2,3,4


---

Si en el cluster de contenidos sigo con problemas:

    4 nodos
        2 data              2 shards primarios + 1 replica  -> LIMIT=REQUEST ALTO y HEAP medio
                                3(heap)-6(ram pod)
        2 coordinacion      HEAP ALTO Y LIMIT Y REQUEST MUY AJUSTADO
                                4(heap)-4.7(ram pod)

No mejora tanto rendimiento, pero si me da más visibilidad de lo que pasa!

---

# REFRESH y MERGES

Cuando llegan documentos (JSONs), Lucene se pone a generar índices (directos-KEYWORDS- e inversos-TEXT-).
Esos índices se generan en memoria RAM (HEAP). 

    T0= Llegan 10 documentos
        Se generan sus indices.
    T0.1= Llegan otros 10 documentos
        Se generan sus indices y se consolidan en RAM con los indices de los anteriores
    T0.2= Llegan otros 10 documentos
        Se generan sus indices y se consolidan en RAM con los indices de los anteriores

---

    Doc1   Campo1=A    Campo2=1
    Doc2   Campo1=B    Campo2=2
    Doc3   Campo1=C    Campo2=1
    Doc4   Campo1=D    Campo2=2

        ->  Indice Campo1
                A   Doc1
                B   Doc2
                C   Doc3
                D   Doc4
        ->  Indice Campo2
                1   Doc1 Doc3
                2   Doc2 Doc4
---

    Doc5   Campo1=A    Campo2=1
    Doc6   Campo1=B    Campo2=2
    Doc7   Campo1=E    Campo2=2

        ->  Indice Campo1
                A   Doc1 Doc5
                B   Doc2 Doc6
                C   Doc3
                D   Doc4
                E   Doc7
        ->  Indice Campo2
                1   Doc1 Doc3 Doc5 Doc7
                2   Doc2 Doc4 Doc6
---

Y así hasta que se haga un refresh:
Cuándo se hace un refresh... Esa estructura se vuelca a disco si hay datos!
- Si hay datos se guardan a disco en un nuevo archivo de segmento
- Si hay muchos datos, puede ser que en lugar de 1 archivo de segmento se guarden en 4 archivos de segmento.
- Si no hay datos... no se genera archivo de segmento

---

Adicionalmente, Elastic puede ir generando archivos transaccionales, como ORACLE (RedoLogs) o POSTGRES (WAL).
Ese guardado es un append en un fichero. MUY RAPIDO.

El refresh no es para persistencia/ha... asegurarme que no pierdo el dato... eso me lo dan los transaccionales.

El refresh es cuando los datos se guardan para que se puedan usar en BUSQUEDAS!

---

Me interesa un refresh alto o bajo?
    Dependiendo del objetivo. Lo que pasa es que Elastic tiene un valor por defecto: 1s (Y eso me interesa? AH!)

    Ventajas de un refresh bajo?
        - Los datos se pueden consultar antes... casi al cargarlos
    Desventajas de un refresh bajo?
        - Me va generando archivos de segmento a tocomocho!
          Qué problema tiene esto?
            - Espacio en disco 
              - datos actualizados, que los viejos siguen
              - términos repetidos -> FRAGMENTACION
            - Búsquedas
              - La búsqueda la tengo que hacer en cada fichero de segmento.
                - El Campo1:A lo puedo tener en 20 archivos de segmento... no en 1
    Ventajas de un refresh alto?
        - Me genera pocos archivos de segmento:
          - Menos espacio
          - Búsquedas más eficientes (menos fragmentación)
    Desventajas de un refresh alto?
        - Los datos tardan más en salir en búsquedas.
  
  Y ahora decisiones.

  Si necesito que las búsquedas vayan bien: 
    Reducir fragmentación y cuantos menos archivos mejor.
        Si genero muchos -> MERGE FRECUENTES
        Si genero pocos -> GUAY = MERGE MENOS FRECUENTES
  Si necesito que los datos estén pronto disponibles.
        Voy a generar muchos!
  Si no necesito que los datos estén pronto disponibles
        Voy a generar menos!

  Cluster de Logs:
    Para qué quiero este cluster? Para qué quiero tener los logs indexados?
     - Para encontrar fallos (ERROR) para qué?
       - Para arreglar los defectos que provocan esos fallos <-     Cuánto tardo en arreglar un defecto? y ponerlo en producción?
                                                                    2 días, 1 semana? Necesito un refresh de 1s?  En serio?
       - Para subsanar las consecuencias del fallo           <-     Cuánto tardo en subsanarlas? horas, dias, semanas...
                                                                    Necesito un refresh de 1s?  En serio?
     - Tomar acción inmediata sobre el sistema para prevenir consecuencias grandes del fallo.
         - PARO!
         - O... no se... lo que necesite.
                Lo tengo automatizado? Posiblemente no
                Necesito un refresh de 1s?  En serio?
                Si al final es Algiuien de Operaciones (Raul o Baltasar) mirando una pantalla y poniendo perejil a San Pancracio.
                Necesito 1 segundo de refresh? Si tardan más en parpadear! Posiblemente con 3, 5 segundos ... estoy igual.
        
  Cluster de contenidos:
    Carga masiva, necesito que los datos estén al segundo disponibles? NO... y esto ya lo hacéis (desactivar el refresh)
    Carga normal, necesito que los datos estén al segundo disponibles????

        No hablamos de pasar de 1 segundo a 1 hora.
        Hablamos de pasar de 1 segundo a 3 segundos o de 1 segundo a 5 segundos.

    A qué podría impactar el refresh más alto? a RAM...
        Mientras no hago refresh, los datos están en RAM.
        Si cargo la hueva huevon de datos por segundo... me interesa ir volcando a disco POR NECESIDAD para no quedarme sin RAM.
        Pero no es vuestro escenario (al menos en la ventana de 1s, 3s, 5s)

    Cuanto más amplie esa ventana menos segmentos.
    Si me la trae al peiro el disco ESTA GUAY! NO ME IMPORTA!
        En vuestro caso, os la tree al peiro el disco? SI
            1.5Gb -> 1.7Gb... y a la semana empaqueto! (MERGE)
    En el de logs, la búsqueda siempre limita por fecha -> Limita los segmentos en los que busco. Los segmentos van asociados a fechas.
        Y buscar YO SOLITO y mi compi la palabra "error" en 1 o 7 ficheros... da igual
    
    POSIBLEMENTE EN el cluster de logs, no me preocupa que se generen muchos segmentos... cuando congele/cierre el INDICE ya hago un merge, para limpiar espacio.
    NO QUIERO AUTOMERGEOS... y me da igual que haya muchos segmentos. -> Realmente me da igual el refresh... Cuanto más bajo mejor 1s.. 3s...

    En el de CONTENIDOS.
        Hay un hueco de actualizaciones... y no hay ROTACION... y hay un huevo de BUSQUEDAS < Necesito los datos lo menos fragmentados
                            v                           v
                        requieren merge     no puedo confiar en momentos concretos donde mergeo (close/freeze)

    1. Necesito definir una politica de merge CON CRITERIO
    2. Necesito que se hagan la menor cantidad de merges (optimizar el uso de recursos) - TEORIA
    3. Necesito los datos lo menos fragmentados de continuo.
    4. Puedo permitirme hasta N segundos de demora en las apariciones en queries de los datos.

    Cuanto tardo en regenerar un ficheros de 140Mb... En escribirlo a disco? Nada!
    Si fueran Gigas.... hablamos! Si tengo encima 10 shards de 20 Gigas... flipas! 200Gb Lleva un ratito, que dejas el HDD jodido!

    Aquí busco una combinación que me sea satisfactoria (SUFICIENTE != OPTIMO)
                                                         BARATO        CARO
---

NO SIEMPRE UN UNICO FICHERO DE SEGMENTO ES LA SITUACION IDEAL
De hecho en ocasiones es CONTRAPRODUCENTE!

Por qué?
- Al mergear se bloquea el segmento(s) en mergeo.
  Más segmentos, menos contención a la hora de inserciones/búsquedas (menos probabilidad)
- Prefiero reescribir un fichero de 10Gb?  o 10 de 1Gb?

        El de 10Gbs: Bloquea mucho (genmera mucha contención) y tarda mucho
        Los de 1 Gb generan mucha menos contención y tardan mucho menos.

- Cuando un índice está cerrado/congelado me interesa 1 segmento, no pasa nada si es gordo!
- Cuando un índice está en uso activo, quizás me interesa que tenga varios segmentos... más manejables.
  - En un momento que lucene tiene tiempo, organiza 1 segmento (borra los obsoletos)... Fusiona 2 pequeños

En vuestro caso, cuando los indices de log los roto -> congelarlo -> 1 segmento.
Vuestros índices de contenidos? funcionan como los de logs?
Ni de cerca

Aquí es donde me podría beneficiar de tener varios segmentos.
Merece la pena? Para vuestro volumen actual posiblemente no. 
Con archivos máximos de 140Mb No merece la pena invertirle ni un segundo.

Si tengo archivos de 1Gb+... quizás me lo planteo...Si tengo muchas consultas y pocos espacios de tiempo libre.

Podría en algún caso limitar ficheros de segmento a 200-300 Mbs

---
Opensearch se fija en varias cosas a la hora de determinar cuándo mergear:
- Una cosa es la frecuencia de mergeo que defina (scheduling)
- Otra cosa lo que hara cuando tenga que mergear (que puede ser nada)

Aunque hablamos de politicas de merge, no es como las politicas de ciclo de vida de índices. Solo son settings que se configuran a nivel de índice o de plantilla (template) de índice.

En qué cosas se fija OpenSearch:
- Cuántos segmentos debe haber de un determinado tamaño para decidirse a juntarlos / mergearlos.
- Tamaño máximo
- % de documentos borrados

Por defecto, Opensearch aplica lo que se llama una policita Tiered de mergeo
Opensearch fusiona archivos por nivel de tamaño (orden de magnitud):
- cuando tiene muchos pequeños, los junta en uno mediano.
  kbs -> Megas
- cuando tiene muchos medianos , los junta en uno grande: decenas o cientos de megas
  Mbs -> Cientos de Megas
Y Así!

En un momento del tiempo puedo tener 1 gradisimo, 4 grandes, 3 medianos y 6 pequeños

- index.merge.policy.max_merged_segment : TAMAÑO MAXIMO AL MERGEAR
- index.merge.policy.segments_per_tier  : NUMERO DE SEGMENTOS DE UN TAMAÑO SIMILAR antes de fusionar
- index.merge.policy.max_merge_at_one: Cuantos segmentos le permito que fusione como mucho en una operación de merge.
- index.merge.policy.deletes_pct_allowed: A partir de qué porcentaje de documentos eliminados te planteas seriamente el mergear

En vuestro caso: LO QUE PODRIAMOS LLEGAR A TOCAR:
- index.merge.policy.max_merged_segment : 100-200Mb
- index.merge.policy.deletes_pct_allowed: 15%-20%
    En realidad, el de bajao ya lo ajust muy bie el opensearch...
    En la práctica el único que puede tener imacto significativo es el primero:

    - index.merge.policy.max_merged_segment : 100-200Mb

Todo esto son INDICACIONES (HINTS, PISTAS) al programa que hacer los merge.
HARA LO QUE QUIERA! Con estos parámetros puedo influir en ese programa y sus decisiones.

Y ojo! Aquí hay otra cosa importante...
En las cargas masivas, hemos dicho que habéis desactivado el refresh...
Pero si lo desactivo, corro el riesgo de que me genere un segmento LA OSTIA de grande en una reindexación con TODO! de 3Gbs
Posiblemente ahí me interese: 
- ForceMerge a un número determinado de segmentos.
- Más fácil: Cada X documentos que proceso en el bulk, le hago yo un refresh manual

Cosas a vigilar:
- Si hay muchos deleted
- En las estadísticas si me sale mucho tiempo consumido en mergeo:
  - aumentar refresh
---




ERROR               Los humanos cometemos errores.
DEFECTO (BUG)       Al cometer un error, un humano puede meter un defecto en el producto.
 ^
FALLO   <----       La manifestación de ese defecto al usar el producto.

---

Monto AMAZON
-> Cada busqueda de un producto -> LOG -> ElasticSearch: Cuadro en Tiempo Real con las búsqedas...
Y si hay muchas cubre un determinado artículo: SUBO PRECIO
                                                    UBER