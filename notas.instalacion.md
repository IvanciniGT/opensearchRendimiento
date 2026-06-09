
# Arquitectura, Capacidad

Ejemplo conceptual del tipo de documentos y estimaciones de tamaño.. tipos de campos


## Arquitectura de cluster

Hay 2 clusters: 
- Monitorización
- Aplicación/Contenidos

Cada uno:
- 3 nodos: Master, Data      < Service (IP DE BALANCEO <- fqdn [En DNS interno de kubernetes])
    RAM? 
        Request: 5Gb
        Limit:   5Gb   JUGAR CON FUEGO! 
        JVM?     -Xms4Gb -Xmx4Gb
    Cores: 
        Request: 500m !!!
        Limit:   1

Almacenamiento:
   - Cabinas

       Cabina1
        HDD1        300G Vol1
        HDD2        300G Vol1
        HDD3        250G Vol1
        HDD4        250G Vol1

       Nodo 1
        esXi
        HDD1
            El propio disco de la VM1
        VolDatos1 500G - ES1
       Nodo 2
        esXi
        HDD1
            El propio disco de la VM2
        VolDatos1 500G - ES3
       Nodo 3
        esXi
        HDD1
            El propio disco de la VM3
        VolDatos1 500G - ES2


   - Locales/Hiperconvergente

       Nodo 1
        esXi
        HDD1 2000G
            - 500G para el vol1 de VMWare
       Nodo 2
        esXi
        HDD1 2000G
            - 500G para el vol1 de VMWare
       Nodo 3
        esXi
        HDD1 2000G
            - 500G para el vol1 de VMWare

        En VSphere defino un vol1 de 500G... pero ese volumen se guarda sobre todos los HDD de las máquinas



La ingesta quien la hace?
- Backend propio que manda datos ya preprocesados
- FluentBeat (Logs)

                     VIPA DE BALANCEO (VIPA1)
                        |
                +-------+-----------------------+---------------------------+-------------- Backend
                |                               |                           |
                IP 1                            IP2                         IP3
                |                               |                           |
            NODO 1 ES (POD)             NODO 2 ES (POD)                 NODO 3 ES (POD)
            recibe QUERY 
            (role coordinador)
            analiza
            parsea
            valida
            determina shards
            lanza consultas ------------> Shard1
                            <------------
                            ----------------------------------------------> Shard2
                            <----------------------------------------------
            Juntar resultados
            Reordenar
            Agrupar
            Devolver al cliente

    2 clusters
    - Logs (Principalmente un cluster de ENTRADA/INGESTA)           2G    60
                                                                          LA HUEVA DE GIGAS 
    - Contenidos (Principalmente es un cluster de CONSULTA)         1 Gb  25
                                                                           4 
                                                                          25 Gb

                                                            Si mis consultas trabajan con todos los datos
                                                            nos pasamos la vida subiendo índices a RAM.
                                                                Rendimiento



# Cluster de ingesta

        NODO1               NODO2               NODO3
        S1                  S1'
                            S2                  S2'

INDICE 1 de logs enero del 2026
    1 primario + 1 replica

        Veo que no da a basto a tragar tantos datos.

INDICE 1 de logs enero del 2026
    2 primario + 1 replica

        Mejoro rendimiento? Capacidad de comer datos? NADA
        Si el cuello de botella era el HDD... el HDD del NODO 2 lo acabo de reventar!

Presión de red

>    1 primario

        X documentos

        100%                100%
          |                   |
          v                   v
        NODO1               NODO2               NODO3
        S1                  S1'

>    2 primarios

        X documentos

        50%                100%                 50%
          |                   |                  |
          v                   v                  v
        NODO1               NODO2               NODO3
        S1                  S1'
                            S2                   S2'

>    3 primarios

        X documentos

        66%                 66%                 66%
          |                   |                  |
          v                   v                  v
        NODO1               NODO2               NODO3
        S1                  S1'
                            S2                   S2'
        S3                                       S3'

>    4 primarios

        X documentos

        75%                 50%                 75%
          |                   |                  |
          v                   v                  v
        NODO1               NODO2               NODO3
        S1                  S1'
                            S2                   S2'
        S3                                       S3'
        S4                                       S4'

>    6 primarios


        X documentos

        66%                 66%                 66%
          |                   |                  |
          v                   v                  v
        NODO1               NODO2               NODO3
        S1                  S1'
                            S2                   S2'
        S3                                       S3'
        S4                  S4'
                            S5                   S5'
        S6                                       S6'        


---

    Agente1         ---->        Cluster
    Agente2         ---->
    Agente3         ---->
    Agente4         ---->


    Tomcats
    Nginx
                        Ahogo al cluster            empaqueto 50 y tardan 2s
App1                    Agente1         ---->   Alguien que haga control de Back Preassure  <----   Cluster
App2                    Agente2         ---->       Cola interna
App3                    Agente3         ---->       
App4                    Agente4         ---->       Kafka
\-----------------------------/
        Mismo pod         ^
                         Sidecar
    Volumen compartido en RAM
        emptyDir:
            medium: Memory
        2 rotados a 50Kb

Rotación de logs


        Ahogo al cluster


            Rabbit es un sistema de mensajería PUSH
            Kafka es un sistema de mensajería  PULL

                Emisor ---mensaje---> Rabbit --PUSH--> Destinatario
                Emisor ---mensaje---> Kafka <--PULL--- Destinatario
                                        ||
                                     Whatsapp



El trabajo quien lo ejecuta en una máquina? COREs de CPU
Quien lo lleva a los CORES? Threads
La mayor parte de cores hoy en día permiten ejecutar / recibir instrucciones de 2 threads: MULTITHREADING





----




>    3 primarios

        X documentos

        NODO1               NODO2               NODO3
        S1                  S1'
                            S2                   S2'
        S3                                       S3'

    
Hago una query... que tiene que buscar en S1, S2, S3 del índice.
Se eligen los nodos que la responden:
    S1 Nodo1
    S2 Nodo2
    S3 Nodo3

En paralelo lleva una segunda query... que tiene que buscar en S1
No se puede ejecutar.... en cola.
Pero no es cola de Pool de ejecutores.
Es en cola a nivel de SO... el hilo ha pillado la query en el OS
El hilo no está enrutado a una cpu... te tenemos limitado a nivel de Kernel de Linux!