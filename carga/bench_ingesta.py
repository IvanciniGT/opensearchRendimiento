"""Benchmark de INGEST RATE comparando numero de shards PRIMARIOS.

Objetivo (dia4, prioridad #3): medir cuantos documentos/segundo aguanta la
ingesta segun el numero de shards primarios, manteniendo TODO lo demas igual
(misma replica, mismo mapping real, misma carga, misma duracion). Asi se aisla
la unica variable: PRIMARIOS = 1 vs 2 vs 3.

Metodo (identico para cada configuracion, para que sea comparable):
  1. Crea un indice NUEVO y vacio con el mapping real (datos/mapping_content.json)
     y los settings {number_of_shards: N, number_of_replicas: R}.
  2. Espera a green.
  3. Genera arboles CONTAINER+LOCATORS(+SUBCLIPS) "de su estilo" con el mismo
     generador de produccion y los indexa con _bulk (parallel_bulk) de forma
     SOSTENIDA durante --duration segundos (por defecto 180 = 3 min).
  4. Mide docs_ok / docs_fail / elapsed -> docs/s, y lee las stats de indexacion
     y el tamano en disco del indice.
  5. (Opcional) borra el indice de prueba.

Por que cambia el resultado con los primarios (lo que se cuenta en clase):
  - 1 primario  -> TODA la escritura cae en 1 nodo (+ su replica en otro). No se
    reparte: el nodo de ese shard es el cuello. Es el caso "hot shard".
  - 2-3 primarios-> la escritura se reparte entre 2-3 nodos -> mas paralelismo de
    ingesta. Con 3 nodos, 3 primarios = 1 primario por nodo (reparto ideal).
  El join obliga a routing por MEDIAID del container raiz, asi que cada arbol
  entero cae en un shard; con muchos arboles el reparto entre shards se equilibra.

Ejemplos:
  python bench_ingesta.py                          # 1,2,3 primarios; replica=1; 3 min c/u
  python bench_ingesta.py --duration 60            # prueba rapida de 1 min por config
  python bench_ingesta.py --shards-list 1,3 --threads 8 --batch 1000
  python bench_ingesta.py --keep                   # no borra los indices al terminar

Apunta al cluster por variables de entorno (config.py); por defecto, el del curso.
"""
import argparse
import json
import time

import config
# Reutilizamos el generador de produccion y el mapping real del laboratorio.
from generador import generate_tree
from crear_indice import DEFAULT_MAPPING, SIMPLE_MAPPINGS


def load_mappings(use_simple, mapping_path):
    """Devuelve el bloque 'mappings' a usar (real por defecto, o minimo con --simple)."""
    if use_simple:
        print("[i] Mapping minimo autocontenido (--simple)")
        return SIMPLE_MAPPINGS
    with open(mapping_path, encoding="utf-8") as f:
        doc = json.load(f)
    print(f"[i] Mapping real: {mapping_path}")
    return doc.get("mappings", doc)


def recreate_index(client, index, shards, replicas, mappings, refresh_interval,
                   translog_durability=None):
    """Borra (si existe) y crea el indice con los settings de la prueba. Espera green."""
    if client.indices.exists(index=index):
        client.indices.delete(index=index)
    index_settings = {
        "number_of_shards": shards,
        "number_of_replicas": replicas,
        "analysis": {"analyzer": {"default": {"type": "standard"}}},
    }
    if refresh_interval is not None:
        index_settings["refresh_interval"] = refresh_interval
    # translog.durability=async -> NO fsync por peticion (fsync periodico). Clave
    # para aislar si el cuello es la latencia de fsync del disco/NFS.
    if translog_durability is not None:
        index_settings["translog.durability"] = translog_durability
    body = {"settings": {"index": index_settings}, "mappings": mappings}
    client.indices.create(index=index, body=body)
    client.cluster.health(index=index, params={"wait_for_status": "green"}, request_timeout=60)
    print(f"[i] Indice '{index}' creado: shards={shards} replicas={replicas} "
          f"refresh={refresh_interval if refresh_interval is not None else '(default)'}"
          f" translog={translog_durability or '(request)'}")


def timed_actions(fake, index, prefix, opts, counters, stop_at):
    """Generador perezoso de acciones bulk hasta que se cumpla el deadline.

    Genera un arbol completo por container (routing = MEDIAID raiz). Comprueba el
    reloj una vez por arbol (no por doc) para no penalizar con llamadas a time().
    """
    seq = 0
    while time.time() < stop_at:
        mediaid = f"{prefix}{seq:08d}"
        seq += 1
        counters["containers"] += 1
        for doc_id, routing, source in generate_tree(fake, mediaid, **opts):
            counters["docs_gen"] += 1
            yield {
                "_op_type": "index",
                "_index": index,
                "_id": doc_id,
                "routing": routing,
                "_source": source,
            }


def run_one(client, index, shards, replicas, mappings, opts, args, fake):
    """Ejecuta una configuracion completa y devuelve su fila de resultados."""
    recreate_index(client, index, shards, replicas, mappings, args.refresh_interval,
                   args.translog_durability)

    from opensearchpy import helpers

    counters = {"containers": 0, "docs_gen": 0}
    ok = failed = 0
    t0 = time.time()
    stop_at = t0 + args.duration
    last = t0
    print(f"[i] >>> Ingestando {args.duration}s en '{index}' "
          f"(threads={args.threads}, batch={args.batch}) ...")

    actions = timed_actions(fake, index, args.prefix, opts, counters, stop_at)
    for success, item in helpers.parallel_bulk(
        client, actions,
        thread_count=args.threads,
        chunk_size=args.batch,
        queue_size=args.threads * 2,
        raise_on_error=False,
        raise_on_exception=False,
    ):
        if success:
            ok += 1
        else:
            failed += 1
            if failed <= 3:
                print(f"   [err] {item}")
        now = time.time()
        if now - last >= 10:
            print(f"   [{index}] docs_ok={ok:,} fail={failed} "
                  f"({ok / (now - t0):,.0f} docs/s) t={now - t0:.0f}s")
            last = now

    elapsed = time.time() - t0

    # Refrescar y leer stats reales del indice (primarios).
    client.indices.refresh(index=index)
    st = client.indices.stats(index=index, params={"filter_path":
        "indices.*.primaries.indexing.index_total,"
        "indices.*.primaries.indexing.index_time_in_millis,"
        "indices.*.primaries.store.size_in_bytes,"
        "indices.*.primaries.docs.count"})
    pri = next(iter(st["indices"].values()))["primaries"]
    store_mb = pri["store"]["size_in_bytes"] / (1024 * 1024)
    idx_total = pri["indexing"]["index_total"]
    idx_ms = pri["indexing"]["index_time_in_millis"]

    row = {
        "shards": shards, "replicas": replicas,
        "containers": counters["containers"], "docs_ok": ok, "docs_fail": failed,
        "elapsed": elapsed, "docs_s": ok / elapsed if elapsed else 0,
        "cont_s": counters["containers"] / elapsed if elapsed else 0,
        "store_mb": store_mb, "docs_count": pri["docs"]["count"],
        "avg_index_ms": (idx_ms / idx_total) if idx_total else 0,
    }
    print(f"[OK] {index}: {ok:,} docs en {elapsed:.0f}s = {row['docs_s']:,.0f} docs/s "
          f"({store_mb:,.0f} MB, fallos={failed})")

    if not args.keep:
        client.indices.delete(index=index)
        print(f"[i] Indice '{index}' borrado (usa --keep para conservarlo).")
    return row


def print_table(rows):
    print("\n" + "=" * 78)
    print(f"  COMPARATIVA INGEST RATE  (replica=1, {rows[0]['elapsed']:.0f}s aprox/config)")
    print("=" * 78)
    h = f"{'primarios':>9} {'docs/s':>10} {'arboles/s':>10} {'docs_ok':>11} {'fail':>5} {'MB(pri)':>9} {'ms/doc':>7}"
    print(h)
    print("-" * len(h))
    base = rows[0]["docs_s"] or 1
    for r in rows:
        speedup = r["docs_s"] / base
        print(f"{r['shards']:>9} {r['docs_s']:>10,.0f} {r['cont_s']:>10,.1f} "
              f"{r['docs_ok']:>11,} {r['docs_fail']:>5} {r['store_mb']:>9,.0f} "
              f"{r['avg_index_ms']:>7.2f}   (x{speedup:.2f} vs 1p)")
    print("=" * 78)


def main():
    ap = argparse.ArgumentParser(description="Benchmark de ingest rate por nº de shards primarios")
    ap.add_argument("--shards-list", default="1,2,3", help="lista de primarios a probar, p.ej. '1,2,3'")
    ap.add_argument("--replicas", type=int, default=1, help="replicas (igual en todas las pruebas)")
    ap.add_argument("--duration", type=int, default=180, help="segundos de ingesta por config (def 180=3min)")
    ap.add_argument("--threads", type=int, default=4, help="hilos parallel_bulk por proceso")
    ap.add_argument("--batch", type=int, default=500, help="chunk_size del bulk")
    ap.add_argument("--index-prefix", default="bench_ingest", help="prefijo de los indices de prueba")
    ap.add_argument("--prefix", default="ING_", help="prefijo de MEDIAID de los docs generados")
    ap.add_argument("--mapping", default=DEFAULT_MAPPING)
    ap.add_argument("--simple", action="store_true", help="mapping minimo en vez del real")
    ap.add_argument("--refresh-interval", default=None,
                    help="p.ej. '-1' para desactivar refresh (mas throughput) o '1s'")
    ap.add_argument("--translog-durability", default=None, choices=["request", "async"],
                    help="'async' = sin fsync por peticion (aisla la latencia de fsync del disco/NFS)")
    ap.add_argument("--keep", action="store_true", help="no borrar los indices de prueba al terminar")
    # rangos del arbol (mismos defaults que cargador.py = "su estilo")
    ap.add_argument("--locators", type=int, nargs=2, metavar=("MIN", "MAX"), default=[5, 30])
    ap.add_argument("--subclip-prob", type=float, default=0.3)
    ap.add_argument("--subclips", type=int, nargs=2, metavar=("MIN", "MAX"), default=[1, 2])
    ap.add_argument("--subclip-locators", type=int, nargs=2, metavar=("MIN", "MAX"), default=[2, 10])
    ap.add_argument("--seed", type=int, default=42, help="semilla (misma carga en cada config)")
    args = ap.parse_args()

    import random
    from faker import Faker

    shards_list = [int(x) for x in args.shards_list.split(",")]
    mappings = load_mappings(args.simple, args.mapping)
    opts = {
        "locators": tuple(args.locators),
        "subclip_prob": args.subclip_prob,
        "subclips": tuple(args.subclips),
        "subclip_locators": tuple(args.subclip_locators),
    }

    client = config.get_client()
    print(f"[i] Cluster: {config.OS_URL}  | configs: {shards_list} primarios x replica={args.replicas}"
          f"  | {args.duration}s cada una\n")

    rows = []
    for shards in shards_list:
        # Misma carga en cada config: re-sembramos antes de cada run.
        random.seed(args.seed)
        Faker.seed(args.seed)
        fake = Faker()
        index = f"{args.index_prefix}_p{shards}r{args.replicas}"
        rows.append(run_one(client, index, shards, args.replicas, mappings, opts, args, fake))
        time.sleep(3)  # pequeño respiro entre configs

    print_table(rows)


if __name__ == "__main__":
    main()
