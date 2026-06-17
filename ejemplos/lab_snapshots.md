# Lab: Snapshots y recuperación (punto 9)

Backup/restore de índices con la API `_snapshot`. Un snapshot es **incremental**
(solo copia segmentos nuevos respecto al anterior) y se guarda en un **repositorio**.

> Variables `OS_URL`/`OS_AUTH`/`osq()` como en `lab_slowlogs_alerting.md`.

---

## 0. PRERREQUISITO: un repositorio compartido por TODOS los nodos

El tipo de repo `fs` exige una ruta (`path.repo`) **montada y accesible desde
todos los nodos data** (un FS compartido). Esto NO está por defecto:
- En el **cluster real** (PVCs NFS), cada nodo monta su propio volumen → habría
  que añadir un volumen NFS **compartido** y declararlo en `path.repo`.
- En **oslab** (emptyDir, disco local por nodo) **no hay FS compartido** → un repo
  `fs` no funcionaría tal cual; hay que añadir un volumen compartido.

Alternativas de repo: `fs` (NFS compartido) o `s3`/`azure`/`gcs` (object store).
El módulo `repository-s3` se incluye en la distribución; si hay un **MinIO/S3** en
el entorno es la opción más limpia en Kubernetes.

### Añadir un repo `fs` compartido a oslab (operador)

Añadir al `nodePool` del CR un volumen extra montado en todos los nodos y el
setting `path.repo`:

```yaml
# en spec.nodePools[0]:
      additionalVolumes:
        - name: snapshots
          path: /usr/share/opensearch/snapshots
          nfs:
            server: nfs.ivanosuna.com
            path: /datos/kubernetes-pvs/opensearch-lab/snapshots   # crear en el NFS
# y en spec.general (additionalConfig se inyecta en opensearch.yml):
  general:
    additionalConfig:
      path.repo: "/usr/share/opensearch/snapshots"
```

(Requiere recrear los pods; el operador hace rolling restart.)

---

## 1. Registrar el repositorio

```bash
# Repo de filesystem (tras configurar path.repo en todos los nodos)
osq "/_snapshot/repo-lab" -X PUT -H 'Content-Type: application/json' -d '{
  "type": "fs",
  "settings": { "location": "repo-lab", "compress": true }
}'

# Repo S3 (si hay object store; requiere credenciales en el keystore de cada nodo)
# osq "/_snapshot/repo-s3" -X PUT -d '{ "type":"s3",
#   "settings": { "bucket":"opensearch-backups", "base_path":"oslab", "endpoint":"minio:9000" } }'

# Verificar y comprobar acceso desde todos los nodos
osq "/_snapshot/repo-lab"
osq "/_snapshot/repo-lab/_verify" -X POST
```

---

## 2. Crear un snapshot

```bash
# snapshot de un índice (o varios; o de todo si se omite "indices")
osq "/_snapshot/repo-lab/snap-1?wait_for_completion=true" -X PUT -H 'Content-Type: application/json' -d '{
  "indices": "lab_content",
  "include_global_state": false
}'

# en producción NO usar wait_for_completion (puede tardar); lanzar async y seguir:
# osq "/_snapshot/repo-lab/snap-1" -X PUT -d '{ "indices":"lab_content" }'
osq "/_snapshot/repo-lab/snap-1/_status"
osq "/_cat/snapshots/repo-lab?v"
```

---

## 3. Restaurar

```bash
# Restaurar a un nombre nuevo (no pisa el original) con regla de rename
osq "/_snapshot/repo-lab/snap-1/_restore" -X POST -H 'Content-Type: application/json' -d '{
  "indices": "lab_content",
  "rename_pattern": "(.+)",
  "rename_replacement": "$1-restored",
  "include_global_state": false
}'

# OJO: para restaurar SOBRE el mismo nombre, el índice debe estar cerrado o borrado.
# osq "/lab_content/_close" -X POST   # luego restore sin rename
osq "/_cat/indices/lab_content*?v"
```

---

## 4. Política automática de snapshots (SM)

El plugin de Snapshot Management programa snapshots y su retención:

```bash
osq "/_plugins/_sm/policies/diaria" -X POST -H 'Content-Type: application/json' -d '{
  "description": "Snapshot diario, retencion 7",
  "creation": { "schedule": { "cron": { "expression": "0 2 * * *", "timezone": "Europe/Madrid" } } },
  "deletion": { "condition": { "max_count": 7 } },
  "snapshot_config": { "repository": "repo-lab", "indices": "lab_content,logs-*" }
}'
osq "/_plugins/_sm/policies/diaria/_explain"
```

En **Dashboards → Snapshot Management** se ve todo visual (repos, snapshots,
políticas, restore con asistente).

---

## 5. Buenas prácticas (punto 9 del temario)

- Snapshot **antes** de cambios grandes (reindex, cambio de mapping, upgrade) →
  es la red de seguridad de la metodología "validar cambios antes/después".
- Repositorio **fuera** del cluster (object store o NFS dedicado), no en los
  mismos discos de datos.
- Probar el **restore** periódicamente: un backup que no se ha restaurado nunca
  no es un backup.
- `include_global_state`: incluir solo si quieres restaurar también plantillas,
  ISM policies, settings de cluster (cuidado al restaurar en otro cluster).

## 6. Limpieza

```bash
osq "/_snapshot/repo-lab/snap-1" -X DELETE
osq "/_snapshot/repo-lab" -X DELETE
# (en oslab desechable, basta con borrar el cluster)
```
