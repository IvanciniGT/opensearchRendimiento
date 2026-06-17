#!/usr/bin/env bash
# Comparativa de ingest rate por nº de primarios SATURANDO el cluster con varios
# PROCESOS de cliente (no un solo Python, que era el cuello). Para cada config
# crea el indice, lanza N procesos cargador durante D segundos, mide docs/s via
# delta de _count, y borra el indice.
#
# Uso: ./bench_ingesta_multiproc.sh "1 2 3" 60 3 4 1
#                                     shards   dur procs threads replicas
set -u
cd "$(dirname "$0")"
. .venv/bin/activate
SHARDS_LIST="${1:-1 2 3}"; DUR="${2:-60}"; PROCS="${3:-3}"; THREADS="${4:-4}"; REPLICAS="${5:-1}"

echo "=== INGEST por primarios (multiproc): procs=$PROCS x threads=$THREADS, ${DUR}s, replica=$REPLICAS ==="
printf "%9s %12s %10s\n" "primarios" "docs/s" "docs"
for S in $SHARDS_LIST; do
  IDX="ing_mp_p${S}"
  python - "$IDX" "$S" "$REPLICAS" <<'PY'
import sys, json, config
idx, shards, reps = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
c = config.get_client(timeout=60)
if c.indices.exists(index=idx): c.indices.delete(index=idx)
mp = json.load(open("../datos/mapping_content.json")).get("mappings")
c.indices.create(index=idx, body={"settings":{"index":{"number_of_shards":shards,"number_of_replicas":reps}},"mappings":mp})
c.cluster.health(index=idx, params={"wait_for_status":"green"}, request_timeout=60)
PY
  # lanzar PROCS cargadores
  for i in $(seq 1 "$PROCS"); do
    python cargador.py --index "$IDX" --containers 100000000 --prefix "MP${i}_" \
      --threads "$THREADS" --batch 1000 >/tmp/mp_${IDX}_${i}.log 2>&1 &
  done
  sleep "$DUR"
  pkill -f "cargador.py --index $IDX" 2>/dev/null
  sleep 2
  python - "$IDX" "$S" "$DUR" <<'PY'
import sys, config
idx, S, dur = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
c = config.get_client(timeout=60)
c.indices.refresh(index=idx)
n = c.count(index=idx)["count"]
print(f"{S:9d} {n/dur:12,.0f} {n:10,}")
c.indices.delete(index=idx)
PY
done
echo "=== fin ==="
