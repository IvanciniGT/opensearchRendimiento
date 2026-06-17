# Análisis de ingesta: ¿más shards = más ingest rate? (caso de método)

Caso real de diagnóstico hecho en clase (16-17 jun 2026). Pregunta de partida:
**medir el ingest rate con 1, 2 y 3 shards primarios (todos 1 réplica)** sobre
índices nuevos con la misma estructura que el real.

Resultado corto: **en nuestras pruebas el nº de primarios NO cambió el ingest
rate** — pero el motivo NO es el que parecía. El cuello de botella resultó ser la
**carga ofrecida por el cliente (concurrencia)**, no el NFS ni la CPU del cluster.
Es un caso perfecto de *por qué hay que validar el banco de pruebas antes de
sacar conclusiones*.

> Herramientas: `carga/bench_ingesta.py` (1 proceso) y
> `carga/bench_ingesta_multiproc.sh` (N procesos). Cluster real: 3 nodos,
> OpenSearch 3.6.0, CPU limit 4 cores/nodo, heap 4 GB, almacenamiento NFS.

---

## 1. La prueba pedida (1 proceso de cliente)

3 min/config, 8 hilos en UN proceso Python, réplica=1, misma carga:

| Primarios | docs/s | vs 1p |
| --------: | -----: | ----: |
| 1 | 2.715 | x1,00 |
| 2 | 2.832 | x1,04 |
| 3 | 2.826 | x1,04 |

Plano. Primera tentación: "el cuello no son los shards". **Correcto, pero
incompleto.** Hay que averiguar QUÉ es el cuello antes de afirmar nada.

---

## 2. Primer (falso) sospechoso: el NFS

Los 3 nodos usan PVCs `primary-nfs-class` contra **un único servidor NFS**
(`nfs.ivanosuna.com`), compartido además con otros workloads (wordpress, loki...).
Parecía el culpable obvio. Pruebas a 3 primarios (90s c/u) para aislar el camino
de escritura:

| Config | docs/s | vs baseline | Qué descarta |
| ------ | -----: | ----------: | ------------ |
| replica=1 (baseline)        | 1.615 | —    | — |
| replica=0 (½ bytes al NFS)  | 1.836 | +14% | NO es ancho de banda del NFS (si lo fuera, ½ bytes ≈ x2) |
| replica=0 + refresh=-1      | 1.904 | +18% | NO son los flush/merge de segmentos |
| replica=1 + translog=async  | 1.901 | +18% | NO es el fsync por petición del translog |

Ninguna palanca del lado disco/red rompía el techo. Y la **CPU del cluster estaba
ociosa**: durante la ingesta a tope, `kubectl top` daba 224 / 433 / 321 m sobre un
límite de **4000 m** por nodo (~6-11%). (`os.cpu.percent` da `-1` en este entorno:
el contenedor no expone el accounting de CPU del cgroup; por eso se mide con
`kubectl top`.)

**Contraprueba con disco local:** el mismo test contra `oslab` (cluster de lab con
`emptyDir`, disco local, ver `k8s/README-oslab.md`) dio **1.892 / 1.953 docs/s**:
prácticamente igual que sobre NFS. Si el NFS fuese el cuello, el disco local
habría arrasado. **No lo hizo → el NFS no era el límite.**

---

## 3. El sospechoso real: el CLIENTE (concurrencia ofrecida)

Si no es shards, ni NFS, ni CPU del cluster... ¿y el generador de carga? Probamos
a subir el nº de **procesos de cliente** (cada uno 4 hilos) contra un índice de 3
primarios:

| Procesos de cliente | docs/s | CPU cluster (nodo más cargado) |
| ------------------: | -----: | ------------------------------ |
| 1 (8 hilos)         | ~2.800 | ~11% (440m/4000m) |
| 3 (×4 hilos)        | ~5.350 | ~61% en 1 nodo (config 1 primario) |
| 6 (×4 hilos)        | **8.367** | ~45% (1799m/4000m), reparto en 3 nodos |

**El throughput escala con la concurrencia del cliente**, no con los shards. A 6
procesos seguíamos subiendo y **ni el cluster (CPU < 50%) ni el laptop (load 7.3
sobre 36 cores) estaban saturados**: el límite era cuántas peticiones en vuelo
ofrecíamos, es decir, la latencia de ida/vuelta × concurrencia (modelo de cola).

### Y los shards, ¿siguen sin importar con más clientes?

Sí: repetida la comparativa 1/2/3 primarios con **3 procesos**, sigue plana
(5.300 / 5.300 / 5.367 docs/s). Porque a ese nivel de carga el cluster tiene
margen de sobra; repartir primarios no ayuda si **ningún nodo está saturado**.

---

## 4. Conclusiones

1. **La lección no es sobre shards ni sobre NFS: es de MÉTODO.** Estuvimos a punto
   de concluir "el cuello es el NFS" con datos que lo parecían. La medición
   correcta (escalar el generador) demostró que el cuello era **el propio banco de
   pruebas** (un cliente no saturaba el cluster). *Antes de optimizar el sistema,
   asegúrate de que tu medición no está limitada por el medidor.*
2. **"Más primarios = más ingesta" tiene una precondición**: que algún nodo esté
   saturado (CPU o IO). Mientras el cluster tenga margen, repartir shards no sube
   el throughput. En estas pruebas nunca se saturó → por eso salía plano.
3. **El NFS NO era el límite aquí** (replica/refresh/translog apenas movieron; el
   disco local de `oslab` empató). Sigue siendo un recurso compartido a vigilar en
   cargas reales mucho más altas, pero no fue el cuello de estas pruebas.
4. **Para un benchmark de ingesta fiable**: usar varios procesos de cliente hasta
   que el throughput deje de subir o el cluster sature (CPU, o colas `write` con
   `rejected>0`). Ahí sí se mide el techo real, y ahí sí tendría sentido comparar
   nº de primarios.
5. Cuándo ayudarían de verdad más primarios en SU entorno: cuando la ingesta sea
   tan alta que el nodo del primario sature CPU/IO. Para verlo hay que ofrecer
   mucha más carga concurrente que la de un solo cliente.

---

## 5. Reproducir

```bash
cd carga && . .venv/bin/activate

# (a) 1 proceso por config — lo que ENGAÑA (cliente = cuello)
python bench_ingesta.py --shards-list 1,2,3 --replicas 1 --duration 180 --threads 8 --batch 1000

# (b) aislar el camino de escritura a 3 primarios (NFS no es el cuello)
python bench_ingesta.py --shards-list 3 --replicas 0 --duration 90 --threads 8 --batch 1000
python bench_ingesta.py --shards-list 3 --replicas 0 --refresh-interval -1 --duration 90 --threads 8
python bench_ingesta.py --shards-list 3 --replicas 1 --translog-durability async --duration 90 --threads 8

# (c) lo CORRECTO: saturar con N procesos de cliente
./bench_ingesta_multiproc.sh "1 2 3" 60 3 4 1     # shards | dur | procs | threads | replicas
./bench_ingesta_multiproc.sh "3"     60 6 4 1     # subir procs hasta que deje de escalar

# CPU real durante la carga (la API da -1 en este entorno)
kubectl top pods -n opensearch
```
