#!/usr/bin/env bash
# RAMPA de saturacion: indice fijo de 3 primarios; para cada nivel de procesos de
# cliente, ingesta 30s, mide docs/s (delta de _count) y la CPU real del cluster.
# Busca el punto donde el throughput deja de subir = saturacion.
#
# Uso: ./bench_ingesta_ramp.sh "6 12 18 24 32" 30 4 3 1
#                                niveles_procs  dur thr shards replicas
set -u
cd "$(dirname "$0")"
. .venv/bin/activate
LEVELS="${1:-6 12 18 24 32}"; DUR="${2:-30}"; THREADS="${3:-4}"; SHARDS="${4:-3}"; REPLICAS="${5:-1}"
IDX="ing_ramp"
NS="${OS_K8S_NS:-opensearch}"   # namespace para kubectl top

python - "$IDX" "$SHARDS" "$REPLICAS" <<'PY'
import sys, json, config
idx, shards, reps = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
c = config.get_client(timeout=60)
if c.indices.exists(index=idx): c.indices.delete(index=idx)
mp = json.load(open("../datos/mapping_content.json")).get("mappings")
c.indices.create(index=idx, body={"settings":{"index":{"number_of_shards":shards,"number_of_replicas":reps}},"mappings":mp})
c.cluster.health(index=idx, params={"wait_for_status":"green"}, request_timeout=60)
print(f"[i] indice {idx} listo: {shards}p/{reps}r")
PY

echo "=== RAMPA saturacion (3 primarios): dur=${DUR}s, threads/proc=${THREADS} ==="
printf "%6s %12s %14s %18s\n" "procs" "docs/s" "laptop_load" "cpu_cluster(m)"
for N in $LEVELS; do
  C0=$(python - "$IDX" <<'PY'
import sys, config
c=config.get_client(timeout=60); c.indices.refresh(index=sys.argv[1])
print(c.count(index=sys.argv[1])["count"])
PY
)
  for i in $(seq 1 "$N"); do
    python cargador.py --index "$IDX" --containers 100000000 --prefix "R${i}_" \
      --threads "$THREADS" --batch 1000 >/tmp/ramp_${i}.log 2>&1 &
  done
  sleep $((DUR - 5))
  CPU=$(kubectl top pods -n "$NS" 2>/dev/null | awk '/opensearch-nodes/{gsub(/m/,"",$2); s+=$2; mx=($2>mx?$2:mx)} END{printf "tot=%d max=%d", s, mx}')
  LOAD=$(uptime | sed 's/.*averages*: //' | awk '{print $1}')
  sleep 5
  pkill -f "cargador.py --index $IDX" 2>/dev/null; sleep 2
  C1=$(python - "$IDX" <<'PY'
import sys, config
c=config.get_client(timeout=60); c.indices.refresh(index=sys.argv[1])
print(c.count(index=sys.argv[1])["count"])
PY
)
  RATE=$(python3 -c "print(f'{($C1-$C0)/$DUR:,.0f}')")
  printf "%6s %12s %14s %18s\n" "$N" "$RATE" "$LOAD" "$CPU"
done

python - "$IDX" <<'PY'
import sys, config
config.get_client(timeout=60).indices.delete(index=sys.argv[1]); print("[i] indice borrado")
PY
echo "=== fin ==="
