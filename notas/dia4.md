
1. RAM                                                       ***     BARATO , RAPIDO, MUY BUENA MEJORA (ALTO IMPACTO - CONCURRENCIA)
                                                                        4.6Gbs (POD)    Hoy está en 6Gb
2. CPU                                                       ***     BARATO , RAPIDO, MUY BUENA MEJORA (ALTO IMPACTO - CONCURRENCIA)
3. SHARDS PRIMARIOS Y REPLICAS                               ***     MEJORA MUCHO EN INGESTA(BUSQUEDAS) Seguir esta tabla!

    Los índices deberían tener: 1, 3 o múltiplos de 3 shards
        Si tengo un índice pequeño y con pocas escrituras: 1        PRIMARIOS       REPLICAS
            Pequeño... 200Mb - 500Mb                                    1               1       HA y pocas consultas
                                                                                        2       Cantidad de consultas
        Si tengo índice grande:                                         3               1       HA y pocas consultas
                                                                                        2       Muchas consultas
                                                                        6
                                                                        Solo si los shards se hacen muy grandes (> 30Gbs)
                                                                        El problema aquí son las operaciones de mnto

        En vuestro caso:;
        - Indices de logs: 3 primarios + 1 réplica
        - Indices de contenidos: 
          - Posiblemente 1 primario + 2 réplicas puede dar muy buen resultado
          - Si hay problemas en ingesta (poca ingesta) subimos a 3 primarios + 2 réplicas.

    Es fácil subir o bajar replicas de un shard a un número aleatorio? CHUPAO! Eso si... cuidado con los tiempos y la red (FUERA DE HORA PICO)
        Tocar el setting del índice
    Es fácil subir primarios de un shard? Depende:
        Si duplico o bajo a la mitad fácil... Si quiero numeritos custom RECREAR INDICE! = CHUNGO!
        3 -> 6 CHUPAO  Esta operación existe en OS split
        2 -> 3 JODIDO!
        6 -> 3 CHUPAO  Esta operación existe en OS srhink
        3 -> 2 JODIDO!

    La politica de rotación de índices no está bien ajustada. Tenemos índices con 0 documentos... 1000 documentos... de kbs.. mbs
    No tiene sentido.. hay que rotar cuando vayamos por 5Gbs+

    NOTA: Esto es lo estandar en Opensearch... Luego está vuestro caso de uso: MUY POCA RAM para indexaciones. En un caso como el vuestro, shards de 1Gb... medio giga pueden dar mejor resultado por el tema del file system cache, al haber poca RAM. Pero nunca Kbs, Mbs

4. MAPPINGS                                                 **      Limpiar todo lo que realmente si se indexa y no se usa.
                                                                                Revisión de mappings es rápida 
                                                                                    Necesito quitar!
                                                                                        Los campos String
                                                                                            Opensearch por defecto: KEYWORD + TEXT
                                                                                                O Keyword o Text...
                                                                                                puede haber ocasiones que quiera los 2?
                                                                                                - Más allá de las búsquedas... hay que mirar otras cosas:
                                                                                                  - Sorts -> Keyword <- Salpica a todo lo sean AGRUPACIONES
                                                                                            Descripción: TEXT               (YAGNI)
                                                                                Necesito reindexar / Recrear el índice 
                                                                                No hay que cambiar código, ni herramientas adicionales

    El campo descipción es un campo de alta o baja cardinalidad?    ALTA CARDINALIDAD
        El índice keyword será grande o pequeño?                    GRANDE! (Los términos no se reusan)


5. DOCUMENTOS QUE NO APLICAN                              ***       QUERY Y FUERA! + MERGE (pesado)
6. ARQUITECTURA DE INGESTA LOGS                            *        IMPACTO ENORME: Ingesta, Red, volumen Almacenamiento, Presión Almacenamiento, CPU, Liberación de RAM
6.1. TENEMOS MUUUUUUCHOS DATOS DE MAS! Sin necesidad real.

    Meter sistema de mensajería que haga persistencia y haga la amortiguación                   MEDIO
    Montar un datapepper o similar ( y configurar pipelines de trasformaicón, enrutado...)      FACIL
        |
        v
    Una vez que tenemos esto podemos montar la escritura de logs a memoria (y no a disco)
    Quitar huevon de datos que no aportan nada
7. ESTRUCTURA INDICES / FUNCIONALIDAD / DISEÑO DE SISTEMA   *       ESTO ES COMPLEJO... pero a largo plazo hay que mirarlo.

    Aquí salen cosas como lo del índice de auditoría que tenéis para el BPM.

        Índice por fechas de auditoría: LOG -> Esto em da una capidad análitica de cojones que ahora mismo no existe.
            Cuántos nuevas actividades se han iniciado este mes

        Consolidaciones que puede interesar hacer para ciertos dashboards... o consultas:
            Si quiero saber las que están en este momento en A, B o C
                - Depende: Agregados sobre el índice de auditoría . Depende del volumen puede ir lento
                           Si va lento... me interesa montar un índice preparado (UPDATES) para la foto final. 
                  
                  En tiempo REAL?


---

    SOLID
        S: SRP = Single Responsability Principle

        Que un componente haga solo una cosa / tenga una sola responsabilidad -> Cohexión/Acoplamiento
        Que un componente atienda a un único actor de negocio


        ---> SACAR DATOS DE AUDITORIA (Log)  ---> OS
                función
                                                    Consolidar datos (Índice materializado) para que ciertas búsquedas sean más rápidas

    Los dashboards pueden ser herramientas de operación                 <- Necesitan Muchas veces Casi Tiempo Real
                 o pueden ser herramientas de Business Intelligence     <- No necesito para nada Tiempo real, ni nada que se le parezca
                                                    ^^^
                                                    Herramientas mucho más potentes que Kibana/Dashboards y MUCHO MAS BARATAS 
                                                        (licencias, CPU, RAM)

                                                        No necesito que trabajen contra un indexador.
                                                        Postgres
---

    OPERACIONES
    Necesito saber si dentro de mi web tengo 500 personas ahora buscando datos de un escándalo que ha habido. -> 4 reporteros 

    BI
    Cuántos contenidos nuevos hemos publcado de cada tipo en los ultimos 6 meses para ver si tengo que reajustar los deptamentos y llevar periodistas de uno a otro.

---



    # REINDEXACION = RECREAR EL INDICE Esto no se hace

    CREACION DE UN INDICE NUEVO
    Y una vez creado -> Cambio alias
        Desarrollo no debe haber usado ni un puñetero NOMBRE DE INDICE en los POST/GET.. peticiones


Máquina 1
    Nodo-OS1*
        Primario
Máquina 2
    Nodo-OS2
        Replica1 < Es la de HA y además aporta cierta escabilidad en lectura
Máquina 3
    Nodo-OS3
        Replica2 < Esta réplica solo sirve para escabilidad en lectura


    En vuestro caso, la jugaís a 1 nodo que caiga.



Máquina 2
    Nodo-OS2*
        Primaria < Es la de HA y además aporta cierta escabilidad en lectura
Máquina 3      v 
    Nodo-OS3   v
        Réplica1 (para mantener lo que he pedido: 1 primario + 1 réplica)
            ESTO ES TOTALMENTE INDESEABLE! Hay que desactivarlo.
                No gano nada en HA, pero si pasa... el movimiento de ese volumen de datos en RED colapsa el cluster
                "index.unassigned.node_left.delayed_timeout": "10m"


Cuando no trabajo con Kubernetes y tengo almacenamiento local


    Maquina 1 física.. Con su almacenamiento físico local           Si se caen 1 y 2 el cluster sigue.. pero sin dato.. Si necesito mover dato
        Primario
    Maquina 2 física.. Con su almacenamiento físico local
        Replica1
    Maquina 3 física.. Con su almacenamiento físico local
    Maquina 4 física.. Con su almacenamiento físico local
    Maquina 5 física.. Con su almacenamiento físico local
    

---

# El cluster de monitorización (LOGS)

Necesita mucha CPU? Algo si.. lucene (invertidos)
Necesita mucha memoria? Más bien poca
Me importa si una búsqueda tarda 3 segundos? NO
Muy pocas búsquedas concurrentes.
Muchas inserciones concurrentes!
Para eso no necesito memoria en JAVA... Necesito un mínimo en SO... para lucene.. las 2 búsquedas que se hagan
Pero los índices deben ser medianos /FECHA
3Gbs HEAP (SOBRADO)

    Quiero almacenamiento HOT       /   COLD
                          NVME/SSD      ROTACIONES  


# El cluster de contenidos

Necesito CPU y RAM por un tubo (BUSQUEDAS)

Servidores esXI
    NICs? 1 red de 25


OKD (Openshift)
    OpenVLan/OpenVSwitch
    Redes por Namespace (proyecto de OKD)
    con QoS