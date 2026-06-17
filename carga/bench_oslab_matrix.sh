#!/usr/bin/env bash
# Matriz CONTROLADA de ingest rate en oslab (1 core/nodo, disco local efimero):
# para cada nº de primarios (1,2,3) sube workers poco a poco y mide docs/s, CPU y
# la cola de escritura. PARA la rampa de un shard si aparecen 'rejected' (satura).
#
# No toca ningun ingress: usa port-forward al servicio de oslab.
# Uso: ./bench_oslab_matrix.sh "1 2 3" "1 2 3 4" 25 4
#        shards            workers      dur thr
set -u
cd "$(dirname "$0")"; . .venv/bin/activate
NS=opensearch-lab
SHARDS_LIST="${1:-1 2 3}"; WORKERS_LIST="${2:-1 2 3 4}"; DUR="${3:-25}"; THREADS="${4:-4}"
PORT=19200
export OS_URL="https://localhost:${PORT}"

# ---------- 1) esperar al rollout: 3 nodos ready con limit.cpu=1 ----------
echo "[wait] esperando rollout de oslab a 1 core (3 nodos ready)..."
while :; do
  OK=$(kubectl get pods -n $NS -o json 2>/dev/null | python3 -c '
import sys,json
d=json.load(sys.stdin)
pods=[p for p in d["items"] if p["metadata"]["name"].startswith("oslab-nodes-")]
ok=0
for p in pods:
    lim=p["spec"]["containers"][0]["resources"]["limits"].get("cpu")
    ready=any(cs.get("ready") for cs in p.get("status",{}).get("containerStatuses",[]))
    if lim=="1" and ready: ok+=1
print(ok)')
  echo "  nodos a 1core+ready: ${OK:-0}/3"
  [ "${OK:-0}" = "3" ] && break
  sleep 10
done

# ---------- 2) port-forward al servicio ----------
kubectl port-forward -n $NS svc/oslab ${PORT}:9200 >/tmp/pf_oslab.log 2>&1 &
PF=$!; trap 'kill $PF 2>/dev/null' EXIT
sleep 6
python - <<'PY'
import config
print("[ok] oslab:", config.get_client(timeout=15).cluster.health(params={"filter_path":"status,number_of_nodes"}))
PY

# ---------- helpers ----------
count() { python - "$1" <<'PY'
import sys, config
c=config.get_client(timeout=60); c.indices.refresh(index=sys.argv[1]); print(c.count(index=sys.argv[1])["count"])
PY
}
wstats() { python - <<'PY'
import config
c=config.get_client(timeout=15)
s=c.nodes.stats(metric="thread_pool",params={"filter_path":"nodes.*.thread_pool.write"})
q=r=0
for n in s["nodes"].values():
    w=n["thread_pool"]["write"]; q+=w.get("queue",0); r+=w.get("rejected",0)
print(f"{q} {r}")
PY
}

# ---------- 3) matriz ----------
echo ""
echo "=== MATRIZ oslab (1 core/nodo) | dur=${DUR}s thr/proc=${THREADS} ==="
printf "%8s %8s %12s %14s %8s %9s\n" "primary" "workers" "docs/s" "cpu_tot(m)" "wqueue" "wrejected"
for S in $SHARDS_LIST; do
  IDX="ing_os_p${S}"
  python - "$IDX" "$S" <<'PY'
import sys, json, config
idx, shards = sys.argv[1], int(sys.argv[2])
c=config.get_client(timeout=60)
if c.indices.exists(index=idx): c.indices.delete(index=idx)
mp=json.load(open("../datos/mapping_content.json")).get("mappings")
c.indices.create(index=idx, body={"settings":{"index":{"number_of_shards":shards,"number_of_replicas":1}},"mappings":mp})
c.cluster.health(index=idx, params={"wait_for_status":"green"}, request_timeout=60)
PY
  R0=$(wstats | awk '{print $2}')   # rejected base de este indice
  for W in $WORKERS_LIST; do
    C0=$(count "$IDX")
    for i in $(seq 1 "$W"); do
      python cargador.py --index "$IDX" --containers 100000000 --prefix "W${i}_" \
        --threads "$THREADS" --batch 1000 >/tmp/os_${IDX}_${i}.log 2>&1 &
    done
    sleep $((DUR - 7))
    CPU=$(kubectl top pods -n $NS 2>/dev/null | awk '/oslab-nodes/{gsub(/m/,"",$2); s+=$2} END{print s}')
    read WQ WR < <(wstats)
    sleep 7
    pkill -f "cargador.py --index $IDX" 2>/dev/null; sleep 2
    C1=$(count "$IDX")
    RATE=$(python3 -c "print(f'{($C1-$C0)/$DUR:,.0f}')")
    printf "%8s %8s %12s %14s %8s %9s\n" "$S" "$W" "$RATE" "${CPU:-?}" "$WQ" "$((WR-R0))"
    # parar la rampa de este shard si hay rechazos (satura) -> no explotar
    if [ "$((WR-R0))" -gt 0 ]; then echo "   [satura] rejected>0 con $W workers en ${S}p -> paro rampa de este shard"; break; fi
  done
  python - "$IDX" <<'PY'
import sys, config
config.get_client(timeout=60).indices.delete(index=sys.argv[1])
PY
  echo ""
done
echo "=== fin ==="
