
                                                            Índices internos
                                                             ^  v
    Usuario Carga un contenido o actualiza un contenido -> POSTGRES    ----> OPENSEARCH
                                                         <- OK

                                    SERVICIO
                                    editorial

                                        Cúal es la repsonsabilidad de este servicio? GUARDAR EL DATO A SALVO
                                            Mandar un mail


    OPENSEARCH

                                Backend
                            ----------------------------------------------------------------------------------------------------------------
        Cliente     http
                    ---->   HTTP Rest Controller                 -->  Service             ->    Repository              ----->  Postgres?
                            Lógica de exposición del servicio         Lógica de negocio         Lógica de persistencia             


                            Cuando el dato esta en postgres 


                                         Postgres                               Opensearch
                                                                                    ^
                            Rabbit  -----GESLASTIC----------------------------------+

    Si interesa en OS guardar solo el grande o
        tanto pequeño como grande

        Para búsquedas de usuario el grande es el que hace falta
        Para cuadros de mando, los pequeños vendrían bien ???





                                        GELASTIC 1
                                          v2                              OPENSEARCH
                                                                            Documento AAA v2
                                        GELASTIC 2
                                          v2'(v1)
                                          Retry ---> GET NUEVO
                                            v2 -> V2' ---> INSERT
