
# Entrada original en fichero

```log
172.20.0.1 - - [24/Apr/2024:08:42:55 +0000] "GET / HTTP/1.1" 200 45 "-" "curl/7.81.0"
```

85 caracteres -> Fichero?       85 bytes

Cuanto ocupa esto en OS?        



'172.20.0.1 - - [24/Apr/2024:08:42:55 +0000] "GET / HTTP/1.1" 200 45 "-" "curl/7.81.0"' -> JSON

# Lo que manda filebeat

```json
{
  "@timestamp": "2024-04-24T09:24:35.495Z",   -> 4 bytes (término) + ubicacion 4-8 bytes
  "@metadata": {
    "beat": "filebeat",                         ubicación
    "type": "_doc",                             ubicación
    "version": "8.13.2"                         ubicación
  },
  "host": {
    "name": "7e63dae95f69"
  },
  "agent": {
    "type": "filebeat",
    "version": "8.13.2",
    "ephemeral_id": "97eb2a33-4880-4d97-9de4-b1ea1d3e0dd2",
    "id": "d83e9dc7-b0b0-4f8b-b469-d49e553fa9f4",
    "name": "7e63dae95f69"
  },
  "message": "172.20.0.1 - - [24/Apr/2024:08:42:55 +0000] \"GET / HTTP/1.1\" 200 45 \"-\" \"curl/7.81.0\"",
  "log": {
    "offset": 1032,
    "file": {
      "path": "/tmp/logs/access_log",
      "device_id": "66305",
      "inode": "1551712"
    }
  },
  "input": {
    "type": "filestream"
  },
  "ecs": {
    "version": "8.0.0"
  }
}
```

Solo filebeat hace un x10... y aun no está indexado!
Pero.. una cosa que hará el OpenSearch es guardar el "_source" un capoia del documento

```
{
  "@timestamp": "2024-04-24T09:24:35.495Z",   -> 4 bytes (término) + ubicacion 4-8 bytes
  "host": "7e63dae95f69",
  "message": "172.20.0.1 - - [24/Apr/2024:08:42:55 +0000] \"GET / HTTP/1.1\" 200 45 \"-\" \"curl/7.81.0\"",
}
```


```json
{
"source": {
"address": "62.83.227.217"
},
"user_agent": {
"original": "curl/7.81.0"
},
"http": {
"response": {
    "status_code": 304
},
"request": {
    "method": "GET"
}
},
"host": {
"name": "cdec5fba7033"
},
"url": {
"original": "/"
},
"timestamp": "25/Apr/2024:06:37:55 +0000",
}
```
750 SIN PREPROCESAR que manda FILEBEAT > LOGSTASH (transformación)      1000bytes o más
285 PREPROCESADO!                                                       400bytes

Solo con este trabajo, la red al tercio
La presion a disco 40%
El tamaño del shard al 40%
Libero RAM A CASCOPORRO!



---


{
    "@timestamp": "2026-06-10T15:22:32.143Z",
    "logtime": "2026-06-10T15:22:32.142Z",
    "message": "] o.s.m.s.b.SimpleBrokerMessageHandler     : Stopped.",
    "logtag": "F",
    "time": "2026-06-10T15:22:32.142842261+00:00",
    "level": "INFO",
    "thread": "ionShutdownHook",
    "pid": "21",
    "stream": "stdout",
    "kubernetes": {
      "labels": {
        "ted-environment": "pro",
        "ted-release": "4.1.0",
        "app_version": "4.1.0-13",
        "ted-tenant": "qa-cicd",
        "ted-appname": "platform-ui",
        "app.kubernetes.io/part-of": "platform-ui",
        "ted-ecosystem": "platform",
        "pod-template-hash": "9b8596587"
      },
      "pod_id": "6bba8369-3289-4cfd-9e57-f26a949abbe6",
      "docker_id": "5c387253bef34359e416bcd087fcab0f9564dae6f00562f27ac192fdbdad09c6",
      "pod_ip": "10.131.0.246",
      "pod_name": "platform-ui-9b8596587-cfs4z",
      "host": "qa-cicd-bblkm-worker-4",
      "container_name": "platform-ui",
      "container_hash": "europe-southwest1-docker.pkg.dev/clouvip-static-resources/tedial/platform-ui@sha256:6892d7bad98a97bdf2f45d3f2baeb44cde0b83da993a9f419412306b56677813",
      "container_image": "europe-southwest1-docker.pkg.dev/clouvip-static-resources/tedial/platform-ui:4.1.0-13",
      "namespace_name": "qa-cicd-platform-pro"
    },
    "class": "[",
    "tedial_target_index": "log-qa-cicd-platform-pro-2026-23"
  },
 
}

1400bytes



{
    "@timestamp": "2026-06-10T15:22:32.143Z",
    "logtime": "2026-06-10T15:22:32.142Z",
    "message": "] o.s.m.s.b.SimpleBrokerMessageHandler     : Stopped.",
    "logtag": "F",
    "level": "INFO",
    "pod_ip": "10.131.0.246",
    "pod_name": "platform-ui-9b8596587-cfs4z",
    "host": "qa-cicd-bblkm-worker-4",
    "container_name": "platform-ui",
}
400 bytes

Es 30%.

Cúanta RAM libero? -> 75%
Cuánto gano en disco? 75%
Cuanto mejora la red? 70%
Cuanto bajo la CPU para procesar todo eso?

---

    NO!

    Fluentd ------> Opensearch
        (puede meter preprocesamiento... de hecho ya hace algo -> JSON)
        pero puedo meterle más: Filtrado, extracción                      NO SUELO QUERER por CPU 
                                                                          Aunque en ocasiones me lo planteo (IMPACTO ENROME EN RED)
                                                                            A MIRAR !

    Tomcat
        Compartiendo disco RAM
    Fluentd ------> KAFKA <--- DataPepper ----> Opensearch
                                Control de backpreassure
                                Enrutamiento 
                                Transformación

    GELASTIC ----> 

    Stack ELK