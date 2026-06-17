
# Tedial Opensearch Architecture

## Arquitectura Microservicios
Tedial tiene una infraestructura basada en microservicios. Existen diferentes entidades que tienen su informacion distribuida en diferentes servicios.

Algunos de los microservicios
 - Editorial
 - Folder
 - Mediafile
 - Collections
 - Strata
 - AST
 - ASTMetadata
 - Embeddings \
 ...

Todos estos microservicios envian informacion a Rabbit (creacion/actualizacion/borrado) y el microservicio `GELASTIC` revice, procesa, normaliza y envia a Opensearch


```
  Editorial    \
  Folder        \
  Mediafile      \
  Collections     ----->  RabitMQ  -----> Gelastic  ----> Opensearch
  Strata         /
  AST           /
  ASTMetadata  /
  Embeddings  /
 ```

## Entidades Principales

### Container

La entidad principal del sistema es el `CONTAINER` representa una media en particular. Contiene informacion proveniente de varios microservicios que llega que puede llegar en desorden. Gelastic conforma un documento basado en secciones segun el microservicio (contexto) del que proviene la informacion

> Realmente llega mucha mas informacion, la configuracion de gelastic determina y filtra que campos se indexan, cuales no y en que indices.

Editorial Message
```
{
    "EDITORIAL--CONTAINER": {
        "SUBTYPE": "VIDEO",
        "MEDIAID": "Water1",
        "SITE": "Phase2",
        "CREATIONDATE": "2026-04-17T10:47:29.827+00:00",
        "LASTMODIFICATIONDATE": "2026-04-17T10:47:29.827+00:00",
        "TYPE": "Multimedia",
        "CREATEDBY": "swork",
        "ISSUBCLIP": false
    }
    "doc_type": "CONTAINER",
    "@group_permissions": {
        "groups": [
            "everyone",
            "Catalogators"
        ],
    },
    "@site": "Phase2",
    "join_field": {
        "name": "level_1"
    }
}
```

Catalogation Message 1:
```
{
    "EDITORIAL_CORE--EDC_DUBLIN_CORE": {
        "DC_DESCRIPTION": {
            "DM_TITLE": "Water1"
        },
        "DC_IDENTIFIER": "Watr1"
    }
```

Catalogation Message 2:
```
{
    "EDITORIAL_CORE--TECHNICAL_INFO": {
        "DEFINITION": "HD",
        "CODEC": "XAVC",
        "EDIT_RATE": "25 1",
        "COLOR_PRIMARIES": "BT.709",
        "WRAPPER": "QT/ISO",
        "ASPECT_RATIO": "16:9",
        "DURATION": 622,
        "DISPLAY_NAME": "ISO-XAVC",
        "BITRATE": "20230493"
    }
}
```


Mefiafile Message
```
{
    "MEDIAFILE--MEDIAFILE": {
        "MEDIAID": "Water1",
        "TRACKS": [
            {
                "TRACKTYPE": "VIDEO",
                "TRACKNUMBER": 0,
                "CHANNELS": [
                    {
                        "HR": [
                            {
                                "SOBJECTNODEID": 0
                            }
                        ],
                        "CHANNELNUMBER": 0
                    }
                ]
            }
        ],
        "TITLE": "Water1",
        "gelastic_lastmodificationdate": 1781004055305
    }
}
```

En Opensearch hay cargado un script `paintless` que procesa y compara las fechas de cada seccion para distinguir si hay indexado alguna version de la seccion y actualizarla o descartarla.

```
/*
 * Gelastic - Update gelastic Document
 *
 * Use: scripted_upsert
 */

// Use to only for debug purposes
// Debug.explain(params.event);

// NOT MODIFY LINE BELOW
String SCRIPT_VERSION = "@project.version@";
String GELASTIC_SECTIONS = 'gelastic_sections';
String TIMESTAMP = '@timestamp';
String GEL_SITE = '@site';
String GEL_LASTMODIFICATION_DATE = 'gelastic_lastmodificationdate';
String GEL_ACTION = 'gelastic_action';
String GEL_DELETED = 'gelastic_deleted';
String GEL_PRESERVE_DELETED = 'gelastic_preserve_deleted';
String GEL_INDEXDATE = 'gelastic_indexdate';
String DOC_TYPE = 'doc_type';
String DOC_JOINFIELD = 'join_field';
String GEL_ACTION_CLEAR = 'clear';
String IGNORE_GROUP_PERMISSIONS = '@ignore_group_permissions';
String ROUTING = 'routing';


// Some versions of Elastic instantiate this as java.util.Collections$EmptyMap, others as java.util.HashMap. First is inmutable.
Map event = new HashMap(params.event);

// Document
List sections = Arrays.asList(params.get(GELASTIC_SECTIONS).splitOnToken(","));
String docTimestamp = params.get(TIMESTAMP);
Long lastModificationDate = params.get(GEL_LASTMODIFICATION_DATE);
String action = params.get(GEL_ACTION);
Boolean deleted = params.get(GEL_DELETED);
Boolean preserveDeleted = params.get(GEL_PRESERVE_DELETED);
Long indexDate = params.get(GEL_INDEXDATE);
String docType = params.get(DOC_TYPE);
Map joinField = event.get(DOC_JOINFIELD);
String site = event.get(GEL_SITE);
Boolean ignoreGroupPermissions = params.get(IGNORE_GROUP_PERMISSIONS);
String routing = params.get(ROUTING);


// Current
boolean updated = false;
Boolean curDeleted = ctx._source.get(GEL_DELETED);
String curDocTimestamp = ctx._source.get(TIMESTAMP);
Long curLastModificationDate = ctx._source.get(GEL_LASTMODIFICATION_DATE);

boolean updateDoc = (preserveDeleted == null || !preserveDeleted.booleanValue());

if (ctx._source.isEmpty()) {
// NEW DOCUMENT
    ctx._source = event;
    updated = true;
    
} else if (!curDeleted.booleanValue() || 
           (action != GEL_ACTION_CLEAR && (curLastModificationDate == null || (curLastModificationDate.longValue() <= lastModificationDate.longValue())))
) {
  
  if (sections.size() == 1 && sections[0] == 'NOSECTION') {
  // NO SECTIONS
  
    if (updateDoc) {
        Object curDate = ctx._source.get(GEL_LASTMODIFICATION_DATE);
        Object newDate = params.get(GEL_LASTMODIFICATION_DATE);

        if (newDate != null && (curDate == null || Long.parseLong(newDate.toString()) > Long.parseLong(curDate.toString()))) {
            event.put(GEL_LASTMODIFICATION_DATE, newDate);
        }

        ctx._source = event;
    }
    updated = true;
  } else {
  // SECTIONS
    for (int s = 0 ; s < sections.size(); s++) { 
        Object curDate = null;

        if (ctx._source.get(sections[s]) != null) {
            curDate = ctx._source.get(sections[s]).get(GEL_LASTMODIFICATION_DATE);
        }

        Object newDate = event.get(sections[s]).get(GEL_LASTMODIFICATION_DATE);
        if (updateDoc && (curDate == null || (newDate != null && Long.parseLong(newDate.toString()) > Long.parseLong(curDate.toString())))) {
            ctx._source.put(sections[s], event.get(sections[s]));
        }
    }
    updated = true;
  }
}

if (updated) {
    if (ctx._source.get(DOC_JOINFIELD) == null && joinField != null) {
        ctx._source.put(DOC_JOINFIELD, joinField);
    }

    if (ctx._source.get(GEL_SITE) == null && site != null) {
        ctx._source.put(GEL_SITE, site);
    }

    if (preserveDeleted != null) {
        ctx._source.put(GEL_PRESERVE_DELETED, preserveDeleted);
    }

    if (ignoreGroupPermissions != null && ignoreGroupPermissions.booleanValue()) {
        ctx._source.put(IGNORE_GROUP_PERMISSIONS, ignoreGroupPermissions);
    }

    ctx._source.put(GEL_DELETED, deleted);
    ctx._source.put(TIMESTAMP, docTimestamp);
    ctx._source.put(GEL_LASTMODIFICATION_DATE, lastModificationDate);
    ctx._source.put(GEL_INDEXDATE, indexDate);
    ctx._source.put(DOC_TYPE, docType);
}
```


El documento final de un `CONTAINER` es algo asi. Potencialmente mas grande, mas catalogaciones diferentes, meediafile mas complejos
```
{
  "EDITORIAL--CONTAINER": {
    "SUBTYPE": "VIDEO",
    "MEDIAID": "Water1",
    "SITE": "Phase2",
    "CREATIONDATE": "2026-04-17T10:47:29.827+00:00",
    "LASTMODIFICATIONDATE": "2026-04-17T10:47:29.827+00:00",
    "TYPE": "Multimedia",
    "CREATEDBY": "swork",
    "ISSUBCLIP": false,
    "gelastic_lastmodificationdate": 1781004053773
  },
  "@timestamp": "2026-06-09T11:20:54.036Z",
  "gelastic_indexdate": 1781004087567,
  "doc_type": "CONTAINER",
  "@group_permissions": {
    "groups": [
      "everyone"
    ],
    "gelastic_lastmodificationdate": 1781004053773
  },
  "@site": "Phase2",
  "join_field": {
    "name": "level_1"
  },
  "gelastic_lastmodificationdate": 1781004054036,
  "gelastic_deleted": false,
  "MEDIAFILE_CORE--MEDIAFILE": {
    "TXREADY": true,
    "gelastic_lastmodificationdate": 1781004055305
  },
  "MEDIAFILE--MEDIAFILE": {
    "MEDIAID": "Water1",
    "TRACKS": [
      {
        "TRACKTYPE": "VIDEO",
        "TRACKNUMBER": 0,
        "CHANNELS": [
          {
            "HR": [
              {
                "SOBJECTNODEID": 0
              }
            ],
            "CHANNELNUMBER": 0
          }
        ]
      }
    ],
    "TITLE": "Water1",
    "gelastic_lastmodificationdate": 1781004055305
  },
  "EDITORIAL_CORE--EDC_DUBLIN_CORE": {
    "DC_DESCRIPTION": {
      "DM_TITLE": "Water1"
    },
    "DC_IDENTIFIER": "Water1",
    "gelastic_lastmodificationdate": 1781004054005
  },
  "EDITORIAL_CORE--TECHNICAL_INFO": {
    "DEFINITION": "HD",
    "CODEC": "XAVC",
    "EDIT_RATE": "25 1",
    "COLOR_PRIMARIES": "BT.709",
    "WRAPPER": "QT/ISO",
    "ASPECT_RATIO": "16:9",
    "DURATION": 622,
    "DISPLAY_NAME": "ISO-XAVC",
    "BITRATE": "20230493",
    "gelastic_lastmodificationdate": 1781004054036
  }
}
```

### Locator

El `LOCATOR` es una entidad que representa un punto concreto en uN `CONTAINER`. (Si el CONTAINER representa un partido de futbol, el LOCATOR podria ser un GOL) Tiene esencialmente una marca de tiempo y catalogacion propia. La relacion es 1-N entre CONTAINER y LOCATOR. Pueden ser decenas/cientos de LOCATORS por cada CONTAINER.

Pueden llegar en desorden (LOCATOR antes que el CONTAINER) debido a la naturaleza distribuida del sistema.
Debido a su cantidad, y para evitar fragmentacion se indexan como documentos independendientes como con un `join_field` que apunta a su `CONTAINER`

```
{
  "@timestamp": "2026-06-09T11:20:52.918Z",
  "gelastic_indexdate": 1781004053216,
  "STRATA--LOCATOR": {
    "MEDIAID": "Water1",
    "SITE": "Phase2",
    "SCORE": 0,
    "CATALOGATIONOBJECT": "QC",
    "LOCATORID": 29696,
    "gelastic_lastmodificationdate": 1781004052918,
    "SEGMENTENTRYPOINT": 1,
    "SEGMENTDURATION": 1,
    "DESCRIPTION": "This a manual timeline annotation UNO",
    "TYPEID": "STRATA_CORE:QC",
    "EDITRATE": "24000 1001",
    "TEMPLATE": "STRATA_CORE",
    "CONFIDENCE": 0
  },
  "doc_type": "LOCATOR",
  "@group_permissions": {
    "groups": [
      "everyone"
    ],
    "gelastic_lastmodificationdate": 1781004052918
  },
  "@site": "Phase2",
  "join_field": {
    "parent": "Water1",
    "name": "level_2"
  },
  "gelastic_lastmodificationdate": 1781004052918,
  "gelastic_deleted": false,
  "STRATA_CORE--QC": {
    "GRADE": "INFO",
    "FAULT": "VIDEO_QUALITY",
    "gelastic_lastmodificationdate": 1781004052918
  }
}
```

### Subclips
Son `CONTAINER` que conceptualmente dependen de otro `CONTAINER` padre.
Se modelan con join_field

```
{
    ...
    "join_field": {
        "parent": "AML030326002",
        "name": "subclip"
    }
    ...
}
```

Los Subclips tambien pueden tener sus propios locators. Estos se han tenido que modelar con un join_field diferente. Opensearch no permitia usar el mismo que con los CONTAINERS padre, si se querian permitir busquedas del tipo. LOCATOR -> SUBCLIP -> CONTAINER donde especificar filtros sobre cualquier de las 3 entidades.

### Otras entidades
Hay mas entidades y relaciones entre si, con conceptos similares. `COLLECTION`, `SUBCOLLECTION` `COLLECTION_ITEM`, ...


## Mapping Indice Content
El indice `content` es uno de los indices principales que alberga las entidades CONTAINER y LOCATOR

```
{
  "voyager_content_sworkdev02_vyg_phase2_site_phase2_en_gb_index_0": {
    "aliases": {
      "voyager_content_sworkdev02_vyg_phase2_site_phase2_en_gb_index": {}
    },
    "mappings": {
      "dynamic": "false",
      "properties": {
        "@group_permissions": {
          "properties": {
            "groups": {
              "type": "text",
              "index": false,
              "fields": {
                "keyword": {
                  "type": "keyword"
                }
              }
            }
          }
        },
        "@ignore_group_permissions": {
          "type": "boolean"
        },
        "@site": {
          "type": "text",
          "fields": {
            "keyword": {
              "type": "keyword",
              "ignore_above": 256
            }
          }
        },
        "@timestamp": {
          "type": "date"
        },
        "AST--SOBJECT_CACHE_STATUS": {
          "properties": {
            "CACHESTATUS": {
              "properties": {
                "STATUS": {
                  "type": "text",
                  "index": false,
                  "fields": {
                    "keyword": {
                      "type": "keyword",
                      "ignore_above": 256
                    }
                  }
                },
                "VOLUMEID": {
                  "type": "long"
                }
              }
            },
            "SOBJECT": {
              "properties": {
                "ID": {
                  "type": "long"
                },
                "NODEID": {
                  "type": "long"
                }
              }
            }
          }
        },
        "COLLECTION--COLLECTION": {
          "properties": {
            "ID": {
              "type": "long"
            },
            "PARENTID": {
              "type": "long"
            },
            "PLAIN_IPATH": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            }
          }
        },
        "COLLECTION--DEPARTMENT": {
          "properties": {
            "CREATEDBY": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "CREATIONDATE": {
              "type": "date"
            },
            "DISPLAYNAME": {
              "dynamic": "true",
              "properties": {
                "en-GB": {
                  "type": "text",
                  "fields": {
                    "keyword": {
                      "type": "keyword",
                      "ignore_above": 256
                    }
                  }
                }
              }
            },
            "ID": {
              "type": "long"
            },
            "IPATH": {
              "type": "text",
              "index": false,
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "LASTMODIFICATIONDATE": {
              "type": "date"
            },
            "NAME": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "PARENTID": {
              "type": "long"
            },
            "PLAIN_IPATH": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "PLAIN_PATH": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "SITE": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "STATUS": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            }
          }
        },
        "EDITORIAL--CONTAINER": {
          "properties": {
            "CONTENTKIND": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "CREATEDBY": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "CREATIONDATE": {
              "type": "date"
            },
            "DEPLOYMENT": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "ISSUBCLIP": {
              "type": "boolean"
            },
            "LASTMODIFICATIONDATE": {
              "type": "date"
            },
            "MEDIAID": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "SITE": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "SUBTYPE": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "TYPE": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            }
          }
        },
        "EDITORIAL_CORE--EDC_DUBLIN_CORE": {
          "properties": {
            "DC_CREATOR": {
              "properties": {
                "ENTITY_NAME": {
                  "type": "text",
                  "fields": {
                    "keyword": {
                      "type": "keyword",
                      "ignore_above": 256
                    }
                  }
                }
              }
            },
            "DC_DESCRIPTION": {
              "properties": {
                "DM_DESCRIPTION": {
                  "type": "text"
                },
                "DM_SUBTITLE": {
                  "type": "text",
                  "fields": {
                    "keyword": {
                      "type": "keyword",
                      "ignore_above": 256
                    }
                  }
                },
                "DM_TITLE": {
                  "type": "text",
                  "fields": {
                    "keyword": {
                      "type": "keyword",
                      "ignore_above": 256
                    }
                  }
                }
              }
            },
            "DC_EPISODE_NUM": {
              "type": "long"
            },
            "DC_IDENTIFIER": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "DC_LOCATION": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            }
          }
        },
        "EDITORIAL_CORE--TECHNICAL_INFO": {
          "properties": {
            "ASPECT_RATIO": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "AUDIO": {
              "type": "text"
            },
            "BITRATE": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "CODEC": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "COLOR_PRIMARIES": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "DEFINITION": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "DISPLAY_NAME": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "DURATION": {
              "type": "long"
            },
            "EDIT_RATE": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "WRAPPER": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            }
          }
        },
        "EDITORIAL_EXTENSION--CUSTOM_EXTENSION": {
          "properties": {
            "LONG_LIST_COMPANY": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "LONG_LIST_CREDIT": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "LONG_LIST_DESC_LOCATION": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "LONG_LIST_DESC_MATERIAL": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "LONG_LIST_DESC_PERSON": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            }
          }
        },
        "EDITORIAL_EXTENSION--LEGACY": {
          "properties": {
            "DATERANGE": {
              "properties": {
                "FROM": {
                  "type": "date"
                },
                "TO": {
                  "type": "date"
                }
              }
            }
          }
        },
        "MEDIAFILE--MEDIAFILE": {
          "properties": {
            "MEDIAID": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "TITLE": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "TRACKS": {
              "properties": {
                "CHANNELS": {
                  "properties": {
                    "CHANNELNUMBER": {
                      "type": "long"
                    },
                    "HR": {
                      "properties": {
                        "SOBJECTID": {
                          "type": "long",
                          "index": false
                        },
                        "SOBJECTNODEID": {
                          "type": "long"
                        }
                      }
                    }
                  }
                },
                "COMPLEMENTS": {
                  "type": "nested"
                },
                "TRACKNUMBER": {
                  "type": "long"
                },
                "TRACKTYPE": {
                  "type": "text",
                  "fields": {
                    "keyword": {
                      "type": "keyword",
                      "ignore_above": 256
                    }
                  }
                }
              }
            }
          }
        },
        "MEDIAFILE_CORE--MEDIAFILE": {
          "properties": {
            "TXREADY": {
              "type": "boolean"
            }
          }
        },
        "STRATA--LOCATOR": {
          "properties": {
            "CATALOGATIONOBJECT": {
              "type": "text"
            },
            "COLOR": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "CONFIDENCE": {
              "type": "double"
            },
            "DESCRIPTION": {
              "type": "text"
            },
            "EDITRATE": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "ELEVATION": {
              "type": "double"
            },
            "EVENTLOGID": {
              "type": "long"
            },
            "KEYWORDS": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "LATITUDE": {
              "type": "double"
            },
            "LOCATORID": {
              "type": "long"
            },
            "LONGITUDE": {
              "type": "double"
            },
            "MEDIAID": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "PARENTMEDIAID": {
              "type": "text",
              "index": false,
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "PARENTSEGMENTDURATION": {
              "type": "long"
            },
            "PARENTSEGMENTENTRYPOINT": {
              "type": "long"
            },
            "PARTICIPANTS": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "SCORE": {
              "type": "long"
            },
            "SEGMENTDURATION": {
              "type": "long"
            },
            "SEGMENTENTRYPOINT": {
              "type": "long"
            },
            "SITE": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "SOURCEAPPLICATION": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "SOURCEENGINE": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "TEMPLATE": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "TIME": {
              "type": "date"
            },
            "TYPEID": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            }
          }
        },
        "STRATA_CORE--COM": {
          "properties": {
            "GRADE": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "SCOPE": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "TYPE": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            }
          }
        },
        "STRATA_CORE--IMF": {
          "properties": {
            "MARKER_TYPE": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            }
          }
        },
        "STRATA_CORE--NONTRANS": {
          "properties": {
            "SEGMENT_TYPE": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            }
          }
        },
        "STRATA_CORE--OVERLAY": {
          "properties": {
            "OVERLAY_TYPE": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            }
          }
        },
        "STRATA_CORE--QC": {
          "properties": {
            "FAULT": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "GRADE": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            }
          }
        },
        "STRATA_CORE--RIGHTS": {
          "properties": {
            "CONTRACT": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "RESTRICTION": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "SCOPE": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            }
          }
        },
        "STRATA_CORE--SPEECH_ROUND": {
          "properties": {
            "DESCRIPTION": {
              "type": "text"
            },
            "DOCUMENT_NUMBER": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "KIND": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "PHASE": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "POLITICAL_PARTY": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "POST": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "SPEAKER": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "SUBJECT_MATTER": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            }
          }
        },
        "STRATA_CORE--SUBJECT_MATTER": {
          "properties": {
            "CODE": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "DESCRIPTION": {
              "type": "text"
            },
            "DOCUMENT_NUMBER": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "TITLE": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            }
          }
        },
        "STRATA_DYNAMIC--FOOTBALL": {
          "properties": {
            "ANALYSIS_NOTES": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "AWAY_SCORE": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "AWAY_TEAM_NAME": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "BALL_SPEED": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "CAMERA_ANGLE": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "COMPETITION_NAME": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "COORDINATES": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "DISTANCE_GOAL": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "FIELD_AREA": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "HOME_SCORE": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "HOME_TEAM_NAME": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "POSSESION_TYPE": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "SEASON": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "SUCCESS_PROBABILITY": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "TOUCHES": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            }
          }
        },
        "TECHNICAL_CORE--EXIF": {
          "properties": {
            "COLOR_SPACE": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            }
          }
        },
        "TECHNICAL_CORE--INFO": {
          "properties": {
            "DISPLAY_NAME": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            },
            "IMF": {
              "properties": {
                "TYPE": {
                  "type": "text",
                  "fields": {
                    "keyword": {
                      "type": "keyword",
                      "ignore_above": 256
                    }
                  }
                }
              }
            },
            "WRAPPER": {
              "type": "text",
              "fields": {
                "keyword": {
                  "type": "keyword",
                  "ignore_above": 256
                }
              }
            }
          }
        },
        "TECHNICAL_CORE--TRACKS": {
          "properties": {
            "AUDIO": {
              "properties": {
                "AUDIO_CODEC": {
                  "type": "text",
                  "fields": {
                    "keyword": {
                      "type": "keyword",
                      "ignore_above": 256
                    }
                  }
                },
                "AUDIO_TYPE": {
                  "type": "text",
                  "fields": {
                    "keyword": {
                      "type": "keyword",
                      "ignore_above": 256
                    }
                  }
                },
                "ORDER": {
                  "type": "long"
                }
              }
            },
            "IMAGE": {
              "properties": {
                "COLOR_SPACE": {
                  "type": "text",
                  "fields": {
                    "keyword": {
                      "type": "keyword",
                      "ignore_above": 256
                    }
                  }
                },
                "ORDER": {
                  "type": "long"
                }
              }
            },
            "VIDEO": {
              "properties": {
                "COLOR_SPACE": {
                  "type": "text",
                  "fields": {
                    "keyword": {
                      "type": "keyword",
                      "ignore_above": 256
                    }
                  }
                },
                "DEFINITION": {
                  "type": "text",
                  "fields": {
                    "keyword": {
                      "type": "keyword",
                      "ignore_above": 256
                    }
                  }
                },
                "ORDER": {
                  "type": "long"
                },
                "VIDEO_CODEC": {
                  "type": "text",
                  "fields": {
                    "keyword": {
                      "type": "keyword",
                      "ignore_above": 256
                    }
                  }
                },
                "VR_TYPE": {
                  "type": "text",
                  "fields": {
                    "keyword": {
                      "type": "keyword",
                      "ignore_above": 256
                    }
                  }
                }
              }
            }
          }
        },
        "doc_type": {
          "type": "text",
          "index": false,
          "fields": {
            "keyword": {
              "type": "keyword",
              "ignore_above": 256
            }
          }
        },
        "gelastic_deleted": {
          "type": "boolean"
        },
        "gelastic_indexdate": {
          "type": "date"
        },
        "gelastic_lastmodificationdate": {
          "type": "date"
        },
        "gelastic_preserve_deleted": {
          "type": "boolean"
        },
        "join_field": {
          "type": "join",
          "eager_global_ordinals": true,
          "relations": {
            "subclip": "subclip_level_2",
            "level_1": [
              "subclip",
              "level_2"
            ]
          }
        },
        "knn_image_default": {
          "properties": {
            "gelastic_lastmodificationdate": {
              "type": "long"
            },
            "vector": {
              "type": "knn_vector",
              "dimension": 512,
              "method": {
                "engine": "faiss",
                "space_type": "l2",
                "name": "hnsw",
                "parameters": {
                  "ef_construction": 256,
                  "m": 24
                }
              }
            }
          }
        }
      }
    },
    "settings": {
      "index": {
        "replication": {
          "type": "DOCUMENT"
        },
        "number_of_shards": "4",
        "provided_name": "voyager_content_sworkdev02_vyg_phase2_site_phase2_en_gb_index_0",
        "knn": "true",
        "creation_date": "1781003827554",
        "analysis": {
          "analyzer": {
            "default": {
              "type": "standard"
            }
          }
        },
        "number_of_replicas": "1",
        "uuid": "CeZrfUDXTGm-THauDqs-XA",
        "version": {
          "created": "137257827"
        },
        "knn.derived_source": {
          "enabled": "true"
        }
      }
    }
  }
}
```


## Busquedas

Algunas de las busquedas mas frecuentes 

### Busqueda de un CONTAINER segun catalogacion propia
```
GET voyager_content_sworkdev02_vyg_phase2_site_phase2_en_gb_index/_search
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "doc_type.keyword": "CONTAINER"
          }
        },
        {
          "term": {
            "EDITORIAL--CONTAINER.MEDIAID.keyword": "MGOTestRelations"
          }
        }
      ]
    }
  }
}
```
> Se puede complicar todo lo que se quiera con campos del propio documento

### Busqueda Containers que tengan un Locator que cumpla condiciones
```
GET voyager_content_sworkdev02_voyager_scasta_site_scasta_en_gb_index/_search
{
   "from":0,
   "size":20,
   "query":{
      "bool":{
         "must":[
           {
               "terms":{
                  "doc_type.keyword":[
                     "CONTAINER"
                  ]
               }
               # Agregar filtros sobre catalogacion del container
            },
            {
               "has_child":{
                  "inner_hits" : {},
                  "type":"level_2",
                   "query":{
                      "bool":{
                         "must":[
                            {
                               "terms":{
                                  "doc_type.keyword":[
                                     "LOCATOR"
                                  ]
                               }
                            }
                            # Agregar filtros sobre catalogacion del locator
                         ]
                      }
                   }
               }
            }
        ]
      }
   }
}
```

### Busqueda Locators que tengan un container que cumpla condiciones
```
GET voyager_strata_sworkdev02_vyg_phase2_site_phase2_en_gb_index/_search
{
   "from":0,
   "size":20,
   "query":{
      "bool":{
         "must":[
           {
               "terms":{
                  "doc_type.keyword":[
                     "LOCATOR"
                  ]
                  # Agregar filtros sobre catalogacion del locator
               }
            },
            {
               "has_parent":{
                  "inner_hits" : {},
                  "parent_type":"level_1",
                   "query":{
                      "bool":{
                         "must":[
                            {
                               "terms":{
                                  "doc_type.keyword":[
                                     "CONTAINER"
                                  ]
                               }
                            }
                         ]
                      }
                      # Agregar filtros sobre catalogacion del container
                   }
               }
            }
        ]
      }
   }
}
```

### Busqueda de Locators con Agregado
```
GET voyager_content_sworkdev02_vyg_phase2_site_phase2_en_gb_index/_search
{
    "from": 0,
    "size": 20,
    "_source": {
        "excludes": [
            "knn_*"
        ]
    },
    "query": {
        "bool": {
            "filter": [
                {
                    "term": {
                        "gelastic_deleted": false
                    }
                },
                {
                    "term": {
                        "doc_type.keyword": "LOCATOR"
                    }
                }
            ],
            "must": [
                {
                    "has_parent": {
                        "parent_type": "level_1",
                        "query": {
                            "bool": {
                                "must": [
                                    {
                                        "terms": {
                                            "doc_type.keyword": [
                                                "CONTAINER"
                                            ]
                                        }
                                    }
                                ]
                            }
                        },
                        "inner_hits": {
                            "name": "level_1",
                            "size": 1
                        }
                    }
                }
            ],
            "should": [
                {
                    "simple_query_string": {
                        "query": "SCASTA_TEST_04 SCASTA_TEST_03",
                        "fields": [
                            "STRATA--LOCATOR.KEYWORDS",
                            "STRATA--LOCATOR.PARTICIPANTS",
                            "STRATA--LOCATOR.SOURCEAPPLICATION.keyword",
                            "STRATA--LOCATOR.SOURCEENGINE.keyword"
                        ],
                        "default_operator": "OR"
                    }
                },
                {
                    "has_parent": {
                        "parent_type": "level_1",
                        "query": {
                            "bool": {
                                "must": [
                                    {
                                        "terms": {
                                            "doc_type.keyword": [
                                                "CONTAINER"
                                            ]
                                        }
                                    },
                                    {
                                        "simple_query_string": {
                                            "query": "SCASTA_TEST_04 SCASTA_TEST_03",
                                            "fields": [
                                                "EDITORIAL_CORE--EDC_DUBLIN_CORE.DC_DESCRIPTION.DM_DESCRIPTION",
                                                "EDITORIAL--CONTAINER.MEDIAID"
                                            ],
                                            "default_operator": "OR"
                                        }
                                    }
                                ]
                            }
                        }
                    }
                }
            ],
            "minimum_should_match": 1
        }
    },
    "aggs": {
        "STRATA--LOCATOR.TYPEID.keyword": {
            "aggs": {
                "facets_counter": {
                    "terms": {
                        "field": "STRATA--LOCATOR.TYPEID.keyword",
                        "size": 100
                    }
                }
            },
            "filter": {
                "bool": {
                    "filter": [
                        {
                            "terms": {
                                "STRATA--LOCATOR.SOURCEENGINE.keyword": [
                                    "BATON"
                                ]
                            }
                        }
                    ]
                }
            }
        },
        "STRATA--LOCATOR.COLOR.keyword": {
            "aggs": {
                "facets_counter": {
                    "terms": {
                        "field": "STRATA--LOCATOR.COLOR.keyword",
                        "size": 100
                    }
                }
            },
            "filter": {
                "bool": {
                    "filter": [
                        {
                            "terms": {
                                "STRATA--LOCATOR.SOURCEENGINE.keyword": [
                                    "BATON"
                                ]
                            }
                        }
                    ]
                }
            }
        },
        "STRATA--LOCATOR.SOURCEENGINE.keyword": {
            "aggs": {
                "facets_counter": {
                    "terms": {
                        "field": "STRATA--LOCATOR.SOURCEENGINE.keyword",
                        "size": 100
                    }
                }
            },
            "filter": {
                "match_all": {}
            }
        },
        "STRATA--LOCATOR.KEYWORDS.keyword": {
            "aggs": {
                "facets_counter": {
                    "terms": {
                        "field": "STRATA--LOCATOR.KEYWORDS.keyword",
                        "size": 100
                    }
                }
            },
            "filter": {
                "bool": {
                    "filter": [
                        {
                            "terms": {
                                "STRATA--LOCATOR.SOURCEENGINE.keyword": [
                                    "BATON"
                                ]
                            }
                        }
                    ]
                }
            }
        },
        "STRATA--LOCATOR.PARTICIPANTS.keyword": {
            "aggs": {
                "facets_counter": {
                    "terms": {
                        "field": "STRATA--LOCATOR.PARTICIPANTS.keyword",
                        "size": 100
                    }
                }
            },
            "filter": {
                "bool": {
                    "filter": [
                        {
                            "terms": {
                                "STRATA--LOCATOR.SOURCEENGINE.keyword": [
                                    "BATON"
                                ]
                            }
                        }
                    ]
                }
            }
        },
        "STRATA--LOCATOR.EDITRATE.keyword": {
            "aggs": {
                "facets_counter": {
                    "terms": {
                        "field": "STRATA--LOCATOR.EDITRATE.keyword",
                        "size": 100
                    }
                }
            },
            "filter": {
                "bool": {
                    "filter": [
                        {
                            "terms": {
                                "STRATA--LOCATOR.SOURCEENGINE.keyword": [
                                    "BATON"
                                ]
                            }
                        }
                    ]
                }
            }
        }
    },
    "sort": [
        {
            "STRATA--LOCATOR.SCORE": {
                "order": "desc",
                "missing": "_last"
            }
        }
    ],
    "post_filter": {
        "bool": {
            "must": [
                {
                    "terms": {
                        "STRATA--LOCATOR.SOURCEENGINE.keyword": [
                            "BATON"
                        ]
                    }
                }
            ]
        }
    }
}
```


```
GET voyager_content_sworkdev02_vyg_phase2_site_phase2_en_gb_index/_search
{
  "from": 0,
  "size": 20,
  "_source": {
    "excludes": [
      "knn_*"
    ]
  },
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "gelastic_deleted": false
          }
        },
        {
          "term": {
            "doc_type.keyword": "CONTAINER"
          }
        }
      ],
      "must": [
        {
          "bool": {
            "should": [
              {
                "simple_query_string": {
                  "query": "MGOTestRelations",
                  "fields": [
                    "EDITORIAL_CORE--EDC_DUBLIN_CORE.DC_DESCRIPTION.DM_DESCRIPTION",
                    "EDITORIAL--CONTAINER.MEDIAID.keyword",
                    "EDITORIAL_CORE--EDC_DUBLIN_CORE.DC_DESCRIPTION.DM_SUBTITLE",
                    "EDITORIAL--CONTAINER.SUBTYPE.keyword",
                    "EDITORIAL_CORE--EDC_DUBLIN_CORE.DC_DESCRIPTION.DM_TITLE",
                    "EDITORIAL--CONTAINER.TYPE.keyword"
                  ],
                  "default_operator": "AND"
                }
              },
              {
                "has_child": {
                  "type": "level_2",
                  "query": {
                    "bool": {
                      "must": [
                        {
                          "terms": {
                            "doc_type.keyword": [
                              "LOCATOR"
                            ]
                          }
                        },
                        {
                          "simple_query_string": {
                            "query": "MGOTestRelations",
                            "fields": [
                              "STRATA--LOCATOR.PARTICIPANTS"
                            ],
                            "default_operator": "AND"
                          }
                        }
                      ]
                    }
                  },
                  "inner_hits": {
                    "name": "child_level_2_google_highlight",
                    "size": 1,
                    "_source": false,
                    "highlight": {
                      "pre_tags": [
                        "<em>"
                      ],
                      "post_tags": [
                        "</em>"
                      ],
                      "fields": {
                        "STRATA--LOCATOR.PARTICIPANTS": {}
                      }
                    }
                  }
                }
              }
            ],
            "minimum_should_match": 1
          }
        }
      ]
    }
  },
  "aggs": {
    "EDITORIAL--CONTAINER.SUBTYPE.keyword": {
      "aggs": {
        "facets_counter": {
          "terms": {
            "field": "EDITORIAL--CONTAINER.SUBTYPE.keyword",
            "size": 100
          }
        }
      },
      "filter": {
        "match_all": {}
      }
    },
    "EDITORIAL_CORE--TECHNICAL_INFO.CODEC.keyword": {
      "aggs": {
        "facets_counter": {
          "terms": {
            "field": "EDITORIAL_CORE--TECHNICAL_INFO.CODEC.keyword",
            "size": 100
          }
        }
      },
      "filter": {
        "match_all": {}
      }
    },
    "EDITORIAL_CORE--TECHNICAL_INFO.EDIT_RATE.keyword": {
      "aggs": {
        "facets_counter": {
          "terms": {
            "field": "EDITORIAL_CORE--TECHNICAL_INFO.EDIT_RATE.keyword",
            "size": 100
          }
        }
      },
      "filter": {
        "match_all": {}
      }
    },
    "EDITORIAL--CONTAINER.TYPE.keyword": {
      "aggs": {
        "facets_counter": {
          "terms": {
            "field": "EDITORIAL--CONTAINER.TYPE.keyword",
            "size": 100
          }
        }
      },
      "filter": {
        "match_all": {}
      }
    },
    "EDITORIAL_CORE--TECHNICAL_INFO.DEFINITION.keyword": {
      "aggs": {
        "facets_counter": {
          "terms": {
            "field": "EDITORIAL_CORE--TECHNICAL_INFO.DEFINITION.keyword",
            "size": 100
          }
        }
      },
      "filter": {
        "match_all": {}
      }
    },
    "EDITORIAL_CORE--TECHNICAL_INFO.WRAPPER.keyword": {
      "aggs": {
        "facets_counter": {
          "terms": {
            "field": "EDITORIAL_CORE--TECHNICAL_INFO.WRAPPER.keyword",
            "size": 100
          }
        }
      },
      "filter": {
        "match_all": {}
      }
    }
  },
  "sort": [
    {
      "EDITORIAL--CONTAINER.CREATIONDATE": {
        "order": "desc",
        "missing": "_last"
      }
    }
  ],
  "highlight": {
    "pre_tags": [
      "<em>"
    ],
    "post_tags": [
      "</em>"
    ],
    "fields": {
      "EDITORIAL_CORE--EDC_DUBLIN_CORE.DC_DESCRIPTION.DM_DESCRIPTION": {},
      "EDITORIAL--CONTAINER.MEDIAID": {},
      "EDITORIAL_CORE--EDC_DUBLIN_CORE.DC_DESCRIPTION.DM_SUBTITLE": {},
      "EDITORIAL--CONTAINER.SUBTYPE": {},
      "EDITORIAL_CORE--EDC_DUBLIN_CORE.DC_DESCRIPTION.DM_TITLE": {},
      "EDITORIAL--CONTAINER.TYPE": {}
    }
  }
}
```


### Busqueda Clip -> Subclip
```
GET voyager_content_sworkdev02_vyg_phase2_site_phase2_en_gb_index/_search
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "doc_type.keyword": "CONTAINER"
          }
        },
        {
          "term": {
            "EDITORIAL--CONTAINER.ISSUBCLIP": true
          }
        }
      ],
      "must": [
        {
          "has_parent": {
            "parent_type": "level_1",
            "query": {
              "bool": {
                "must": [
                  {
                    "terms": {
                      "doc_type.keyword": [
                        "CONTAINER"
                      ]
                    }
                  }
                ]
              }
            },
            "inner_hits": {
              "name": "parent_level_1",
              "size": 1
            }
          }
        }
      ]
    }
  }
}
```

### Busqueda Clip -> Subclip -> Locator
```
GET voyager_content_sworkdev02_vyg_phase2_site_phase2_en_gb_index/_search
{
  "_source" : {
    "includes" : [
       "EDITORIAL--CONTAINER", 
       "MEDIAFILE--MEDIAFILE.MEDIAID"
     ]
  },
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "doc_type.keyword": "CONTAINER"
          }
        },
        {
          "term": {
            "EDITORIAL--CONTAINER.ISSUBCLIP": false
          }
        }
      ],
      "must": [
        {
          "has_child": {
            "type": "subclip",
            "query": {
              "bool": {
                "must": [
                  {
                    "terms": {
                      "doc_type.keyword": [
                        "CONTAINER"
                      ]
                    }
                  },
                  {
                    "has_child": {
                      "type": "subclip_level_2",
                      "query" : {
                        "bool" : {
                          "filter" : [
                            {
                              "term": { 
                                "doc_type.keyword": "LOCATOR" 
                              }
                            }
                          ]
                        }
                      },
                      "inner_hits": { 
                        "name": "locators_in_subclip",
                        "_source" : {
                          "includes" : [
                           "STRATA--LOCATOR"
                         ]
                        }
                      }
                    }
                  }
                ]
              }
            },
            "inner_hits": {
              "_source" : {
                "includes" : [
                 "EDITORIAL--CONTAINER"
                 ]
              },
              "name": "parent_level_1",
              "size": 1
            }
          }
        }
      ]
    }
  }
}
``` 


### Busqueda subclip -> locator
```
GET voyager_content_sworkdev02_vyg_phase2_site_phase2_en_gb_index/_search
{
  "_source" : ["EDITORIAL--CONTAINER"],
  "size": 10,
  "query": {
    "bool": {
      "filter": [
        { "term": { "doc_type.keyword": "CONTAINER" } }
      ],
      "must": [
        {
          "has_child": {
            "type": "subclip_level_2",
            "query": { 
              "bool" : {
                "must" : [
                  { "term": { "doc_type.keyword": "LOCATOR" } },
                  { 
                    "has_parent" : {
                      "parent_type" : "subclip",
                      "query" : {
                        "bool" :{
                          "must" : [
                            {
                              "has_parent" : {
                                "parent_type" : "level_1",
                                "query" : {"match_all": {}},
                                "inner_hits": { "name": "subclip_clip", "_source" : ["EDITORIAL--CONTAINER"]}
                              }
                            }    
                          ]
                        }
                      },
                      "inner_hits": { "name": "locator_subclip", "_source" : false}
                    }
                  }
                ]
              }
            },
            "inner_hits": { "name": "locators_in_subclip_direct" }
          }
        }
      ]
    }
  }
}
```


### Busqueda con todos sus locators (clip + subclips)
```
GET voyager_content_sworkdev02_vyg_phase2_site_phase2_en_gb_index/_search
{
  "size": 10,
  "query": {
    "bool": {
      "filter": [
        { "term": { "doc_type.keyword": "CONTAINER" } }
      ],
      "should": [
        {
          "has_child": {
            "type": "level_2",
            "query": { "term": { "doc_type.keyword": "LOCATOR" } },
            "inner_hits": { "name": "locators_direct" }
          }
        },
        {
          "has_child": {
            "type": "subclip_level_2",
            "query": { "term": { "doc_type.keyword": "LOCATOR" } },
            "inner_hits": { "name": "locators_in_subclip_direct" }
          }
        }
      ],
      "minimum_should_match": 0
    }
  }
}
```