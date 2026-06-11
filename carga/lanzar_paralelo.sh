#!/usr/bin/env bash
#
# Lanza varios procesos cargador.py en paralelo (varios "productores"),
# cada uno con su propio prefijo de MEDIAID para que no colisionen los _id.
# Cada proceso a su vez usa bulk multihilo -> paralelismo en dos niveles.
#
# Uso:
#   ./lanzar_paralelo.sh <WORKERS> <CONTAINERS_POR_WORKER> [args extra para cargador.py]
#
# Ejemplos:
#   ./lanzar_paralelo.sh 4 5000
#   ./lanzar_paralelo.sh 8 20000 --threads 4 --batch 1000 --locators 20 80
#
# Total de containers = WORKERS * CONTAINERS_POR_WORKER (+ sus locators/subclips).
#
# Para ver el efecto en el cluster mientras carga:
#   watch -n2 'curl -sk -u admin:Pa$$w0rd2026 https://opensearch.iochannel.tech/_cat/thread_pool/write?v'

set -euo pipefail

WORKERS="${1:?Falta WORKERS (numero de procesos en paralelo)}"
CPW="${2:?Falta CONTAINERS_POR_WORKER}"
shift 2 || true
EXTRA_ARGS=("$@")

cd "$(dirname "$0")"
PY="${PYTHON:-python3}"

# Base de prefijo de MEDIAID. Cambiala entre lotes (env PREFIX_BASE) para no
# colisionar _id al recargar sobre un indice que ya tiene datos.
#   PREFIX_BASE=LOTE2 ./lanzar_paralelo.sh 4 1250 ...
PREFIX_BASE="${PREFIX_BASE:-LAB}"

echo "[i] Lanzando $WORKERS workers x $CPW containers = $((WORKERS * CPW)) containers raiz"
echo "[i] base de prefijo: ${PREFIX_BASE}"
echo "[i] args extra: ${EXTRA_ARGS[*]:-(ninguno)}"

pids=()
for ((i=0; i<WORKERS; i++)); do
    prefix="${PREFIX_BASE}${i}_"
    echo "[i] -> worker $i  prefix=$prefix"
    "$PY" cargador.py --containers "$CPW" --prefix "$prefix" "${EXTRA_ARGS[@]}" &
    pids+=("$!")
done

# Propaga fallo si algun worker peta
rc=0
for pid in "${pids[@]}"; do
    if ! wait "$pid"; then
        rc=1
    fi
done

echo "[OK] Todos los workers han terminado (rc=$rc)."
exit "$rc"
