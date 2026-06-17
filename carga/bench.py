"""Benchmark de busqueda con concurrencia sostenida (closed-loop).

Lanza una misma "familia" de query con N peticiones concurrentes durante T
segundos y calcula latencias (mediana, p95, p99) tanto del 'took' del servidor
como del tiempo extremo-a-extremo (incluye cola/red), ademas del throughput.

Para que la CACHE no falsee la medida:
  - Cada peticion va PARAMETRIZADA con un valor aleatorio (id, subtype, engine...),
    asi el cache key del request_cache cambia y se tocan datos distintos.
  - Ademas se envia request_cache=false (desactivable con --cache).

Ejemplos:
  python bench.py --query join --concurrency 5 --duration 30
  python bench.py --query term1 -c 10 -d 20
  python bench.py --query agg --concurrency 5 --duration 30 --cache   # con cache
"""
import argparse
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor

import config

# Vocabularios reales del indice (coinciden con el generador).
# Los prefijos de MEDIAID se pueden sobreescribir por entorno para que un alumno
# los ajuste a SU carga (p.ej. export OS_BENCH_PREFIXES="LAB0_,LAB1_,LAB2_,LAB3_").
PREFIXES = os.environ.get("OS_BENCH_PREFIXES", "BIG_0_,BIG_1_,BIG_2_,BIG_3_,BIG_4_,BIG_5_").split(",")
SUBTYPES = ["VIDEO", "AUDIO", "IMAGE", "DOCUMENT", "SEQUENCE"]
ENGINES = ["BATON", "MANUAL", "AI_VISION", "SPEECH2TEXT", "INGEST"]
TYPES = ["Multimedia", "News", "Sports", "Movie", "Series", "Promo"]


def _mediaid(rnd):
    return f"{rnd.choice(PREFIXES)}{rnd.randint(1, 70000):08d}"


# Cada template recibe un random.Random y devuelve el body parametrizado.
def q_term1(rnd):
    # Devuelve 0/1: busca un CONTAINER por MEDIAID aleatorio (cache-busting por id)
    return {"size": 1, "query": {"bool": {"filter": [
        {"term": {"doc_type.keyword": "CONTAINER"}},
        {"term": {"EDITORIAL--CONTAINER.MEDIAID.keyword": _mediaid(rnd)}},
    ]}}}


def q_filter(rnd):
    # Devuelve muchos (size:0): conteo de CONTAINER por SUBTYPE aleatorio
    return {"size": 0, "query": {"bool": {"filter": [
        {"term": {"doc_type.keyword": "CONTAINER"}},
        {"term": {"EDITORIAL--CONTAINER.SUBTYPE.keyword": rnd.choice(SUBTYPES)}},
    ]}}}


def q_join(rnd):
    # has_child: CONTAINER (de un SUBTYPE aleatorio) que tengan algun LOCATOR
    return {"size": 0, "query": {"bool": {
        "filter": [{"term": {"EDITORIAL--CONTAINER.SUBTYPE.keyword": rnd.choice(SUBTYPES)}}],
        "must": [{"has_child": {"type": "level_2",
                                "query": {"term": {"doc_type.keyword": "LOCATOR"}}}}],
    }}}


def q_agg(rnd):
    # faceta de TYPEID filtrando por un SOURCEENGINE aleatorio (cache key distinto)
    return {"size": 0,
            "query": {"bool": {"filter": [
                {"term": {"doc_type.keyword": "LOCATOR"}},
                {"term": {"STRATA--LOCATOR.SOURCEENGINE.keyword": rnd.choice(ENGINES)}},
            ]}},
            "aggs": {"t": {"terms": {"field": "STRATA--LOCATOR.TYPEID.keyword", "size": 100}}}}


TEMPLATES = {"term1": q_term1, "filter": q_filter, "join": q_join, "agg": q_agg}


def _pct(v, p):
    v = sorted(v)
    k = max(0, min(len(v) - 1, int(len(v) * p / 100) - 1))
    return v[k]


def run_level(client, tmpl, params, index, concurrency, duration):
    """Ejecuta un nivel de concurrencia 'duration' segundos. Devuelve stats."""
    results = []
    errors = [0]
    stop_at = time.time() + duration

    def worker(wid):
        rnd = random.Random(wid * 7919 + 1)
        local = []
        while time.time() < stop_at:
            body = tmpl(rnd)
            t0 = time.perf_counter()
            try:
                resp = client.search(index=index, body=body, params=params)
                local.append(((time.perf_counter() - t0) * 1000, float(resp.get("took", 0))))
            except Exception:
                errors[0] += 1
        results.extend(local)

    t_start = time.time()
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        list(ex.map(worker, range(concurrency)))
    wall = time.time() - t_start

    el = [r[0] for r in results] or [0]
    tk = [r[1] for r in results] or [0]
    n = len(results)
    return {
        "c": concurrency, "n": n, "wall": wall, "errors": errors[0],
        "rps": n / wall if wall else 0,
        "e_med": _pct(el, 50), "e_p95": _pct(el, 95), "e_p99": _pct(el, 99), "e_max": max(el),
        "t_med": _pct(tk, 50), "t_p95": _pct(tk, 95), "t_p99": _pct(tk, 99), "t_max": max(tk),
    }


def main():
    ap = argparse.ArgumentParser(description="Benchmark de busqueda concurrente")
    ap.add_argument("--index", default=config.OS_INDEX)
    ap.add_argument("--query", required=True, choices=list(TEMPLATES))
    ap.add_argument("-c", "--concurrency", type=int, default=5)
    ap.add_argument("-d", "--duration", type=int, default=30, help="segundos por nivel")
    ap.add_argument("--ramp", default=None,
                    help="lista de concurrencias para barrer y buscar saturacion, p.ej. '1,2,5,10,20,40'")
    ap.add_argument("--cache", action="store_true", help="permitir request_cache (por defecto desactivado)")
    ap.add_argument("--warmup", type=int, default=3, help="segundos de calentamiento (no se miden)")
    args = ap.parse_args()

    client = config.get_client()
    tmpl = TEMPLATES[args.query]
    params = {} if args.cache else {"request_cache": "false"}

    # Warmup (no medido): un nivel corto a la concurrencia base
    if args.warmup > 0:
        run_level(client, tmpl, params, args.index, args.concurrency, args.warmup)

    cache_txt = "ON" if args.cache else "OFF"

    if args.ramp:
        levels = [int(x) for x in args.ramp.split(",")]
        print(f"\n=== RAMPA  query={args.query}  cache={cache_txt}  {args.duration}s/nivel  index={args.index} ===")
        print(f"{'conc':>5} {'req/s':>8} {'took_med':>9} {'took_p95':>9} {'took_p99':>9} {'e2e_med':>8} {'e2e_p95':>8} {'errores':>8}")
        prev_rps = None
        for c in levels:
            s = run_level(client, tmpl, params, args.index, c, args.duration)
            flag = ""
            if prev_rps is not None and s["rps"] < prev_rps * 1.05:
                flag = "  <- satura (throughput ya no sube)"
            prev_rps = max(prev_rps or 0, s["rps"])
            print(f"{s['c']:>5} {s['rps']:>8.1f} {s['t_med']:>9.0f} {s['t_p95']:>9.0f} {s['t_p99']:>9.0f} {s['e_med']:>8.0f} {s['e_p95']:>8.0f} {s['errors']:>8}{flag}")
        return

    # Modo simple (un solo nivel)
    s = run_level(client, tmpl, params, args.index, args.concurrency, args.duration)
    print(f"\n=== query={args.query}  concurrency={args.concurrency}  duracion={s['wall']:.0f}s  cache={cache_txt} ===")
    print(f"  peticiones={s['n']}  throughput={s['rps']:.1f} req/s  errores={s['errors']}")
    print(f"  e2e  (ms): med={s['e_med']:.0f}  p95={s['e_p95']:.0f}  p99={s['e_p99']:.0f}  max={s['e_max']:.0f}")
    print(f"  took (ms): med={s['t_med']:.0f}  p95={s['t_p95']:.0f}  p99={s['t_p99']:.0f}  max={s['t_max']:.0f}")


if __name__ == "__main__":
    main()
