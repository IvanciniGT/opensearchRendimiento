# oslab — cluster OpenSearch de laboratorio (ligero y efímero)

Cluster pequeño con almacenamiento **efímero** (`emptyDir`, disco local del nodo)
para practicar Alerting / Anomaly Detection / Observability / Snapshots / ISM /
merge policies **sin tocar el cluster real** y asegurando que el dataset cabe en RAM.

## Especificaciones

| | Valor |
|---|---|
| Versión | OpenSearch 3.6.0 + Dashboards 3.6.0 |
| Nodos | 3 (`master,data,ingest`) |
| Heap | 2 GB (`-Xms2g -Xmx2g`) |
| RAM pod | request 2.5Gi / limit 3Gi |
| CPU pod | request 0.5 / limit 1 |
| Almacenamiento | **emptyDir** (local, efímero — NO usa el NFS compartido) |
| Namespace | `opensearch-lab` |
| Operador | el mismo que el cluster real (cluster-wide) |

> **Efímero**: si un pod se reinicia, ese nodo pierde sus shards (se recuperan de
> las réplicas). Si caen los 3 a la vez, se pierde el dato. Es lo deseado para un
> lab desechable. Por eso `emptyDir`: evita el cuello del NFS y al ser el dataset
> pequeño cabe entero en el page cache → "todo en RAM".

## Desplegar

```bash
# 1) namespace + copia del secret de admin (mismas credenciales que el real)
kubectl create namespace opensearch-lab
kubectl get secret opensearch-admin-credentials -n opensearch -o json \
 | python3 -c "import sys,json; d=json.load(sys.stdin); m=d['metadata']; [m.pop(k,None) for k in ('namespace','resourceVersion','uid','creationTimestamp','ownerReferences','managedFields','annotations')]; m['namespace']='opensearch-lab'; print(json.dumps(d))" \
 | kubectl apply -f -

# 2) cluster
kubectl apply -f k8s/oslab-cluster.yaml

# 3) esperar (3 nodos 1/1 + dashboards)
kubectl get pods -n opensearch-lab -w
kubectl get opensearchcluster oslab -n opensearch-lab
```

## Acceder

No tiene ingress (es interno). Usar port-forward:

```bash
# API OpenSearch
kubectl port-forward -n opensearch-lab svc/oslab 19200:9200
#   -> https://localhost:19200  (admin / misma contraseña que el real)

# Dashboards
kubectl port-forward -n opensearch-lab svc/oslab-dashboards 5601:5601
#   -> http://localhost:5601
```

Para los scripts de `carga/` apuntar a oslab:
```bash
export OS_URL='https://localhost:19200'
export OS_USER='admin'; export OS_PASS='<misma del real>'
# crear un índice de lab y cargar datos pequeños:
cd carga && . .venv/bin/activate
OS_URL=https://localhost:19200 python crear_indice.py --index lab --simple --recreate --shards 1 --replicas 1
OS_URL=https://localhost:19200 python cargador.py --index lab --containers 2000
```

## Borrar (dejar el entorno como estaba)

```bash
kubectl delete -f k8s/oslab-cluster.yaml          # borra el CR (y sus pods/STS/PVCs efímeros)
kubectl delete namespace opensearch-lab           # borra ns + secret copiado
```

## Para qué usarlo (cuadernos de `ejemplos/`)

- `lab_slowlogs_alerting.md` — slow logs, Alerting, Anomaly Detection.
- `lab_ism_rollover.md` — ISM y rollover.
- `lab_merge_policies.md` — merges y forcemerge.
- `lab_snapshots.md` — snapshots (ver prerrequisito de repo compartido).
- `lab_observability_prometheus.md` — Observability y métricas.
