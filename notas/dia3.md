# mmapfs 

Esto es una estrategia que puede usar el kernel de LINUX a la hora de montar un archivo en RAM.

Ayer comentaba que puedo usar un trozo de la ram como si fuera disco.

    /
        bin/
        etc/
        carpeta/ ---> RAM (500Kbs)
        nfscliente/ ---> NFS Server

Eso es una estrategia.. y ese trozo de memoria se formatea con un sistema de archivos como si fuera un disco.

Pero hay más formas! Una de ellas MMAPFS

Eso es algo de Linux.

Me permite coger un fichero (con una estructura interna muy especial) y montarlo en memoria
pero con un índice que me permite acceder a las distintas partes del fichero ULTRARAPIDO

Map<String,String>

Sabeís quién usa esto? LUCENE!
Los ficheros de segmento se montan directitos en RAM.
Y eso lo hace JAVA? NO. Lo hace el SO (Linux)

Dicho de otra forma, los índices están en el HEAP DE JAVA? Me temo que no...
Estan en el file system cache (LINUX)

---

Pod:
Request de 4Gbs     <- Esto es lo que Kubernetes garantiza al Programa / Contenedor
                        Se usa en la planificación (al decidir en que nodo se mete un contenedor)
Limit   de 6Gbs     <- No se usa para planificación. Simplemente si el contenedor pide más ram de la garantizada (request) Y si en el nodo hay hueco, se le da hasta este límite

El problema es que otro contenedor del mismo nodo quiere memoria RAM... si no hay disponible y debe entregarsele por tenerla garantizada.... Kubernetes hace un OOM Kill de mi contenedor:
kill -9


NODO 1          Total:      16Gbs de RAM        sin comprometer 0

    os1           req 4
                  lim 6
                  uso   4
    os2           req 4
                  lim 6
                  uso   4gbs
    rabbit1       req 4
                  lim 6
                  uso   4 
    postgres      req 4
                  lim 6
                  uso   4

En los os... tenemos una configuracion para la JVM:
    HEAP 4Gbs
Qué es el HEAP?   Donde se guardan los datos!
CODIGO DE LA JVM
CODIGO DEL PROGRAMA
EL THREAD STACK

Si tengo ya problemas de esto... debería.

    restarts de los OS?
        SI      Estamos viendo el comportamiento.. y es malo.. en cualquier momento sin previo aviso... cataplaf
        NO      Señal de que no tiene sentido la distribucion de recursos dentro del cluster de kubernetes
                Hay pods, que les estoy dando memoria, que no están usando.. QUITALE!
                Y ponle al OS


     1 peticion                              1 peticion                                     2 peticiones
    masters0                                  masters1                                      masters2
                                                0                                            0r
       1                                                                                     1r 
       2r                                       2

Momento 1   CPU 100% (dato1)                           CPU 100% (dato2)                         CPU 100% (dato1)
Momento 2   CPU 0%  dato3                          CPU 0%        dato3                           CPU 100% (dato2)

    Llegan 2 ingestas a la vez... Donde se guardan.. caso que fueran a distinto shard 50%

        P1==P2
        1.  1
        0.  0
        0.  1
        0.  0   




---


ID              STATE               FECHA
1               ALTA                1 de enero
1               GESTION             2 de enero         POST por id

    Si es por id -> 
        Foto actual
    Si no es por ID (documentos distintos)->
        Altas de enero

    
Tengo un índice de donde voy sacando documentos cuando pasen 30 días


Tener 2 índices rotados de 30 días
    La busqueda en los 2... con filtro por fecha a 30 días

        1-enero   - 1 febrero       MES ANTERIOR
        1-febrero - 1 marzo         MES VIGENTE

        Pero hoy es 17 de febrero
            La búsqueda en los 2
                filtro por fecha > 17 enero
                Como son transaccionales.. y se guardan por fecha... ese filtro es inmediato

21.6gb 50M
20.000 50
        x
       400 = bytes