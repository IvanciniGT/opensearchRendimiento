"""Cargador masivo de documentos al indice de laboratorio (bulk).

Genera arboles CONTAINER+LOCATORS(+SUBCLIPS) y los indexa con _bulk usando
opensearch-py (parallel_bulk = varios hilos por proceso). Es streaming: la
memoria se mantiene acotada aunque generes millones de documentos.

Para paralelismo entre PROCESOS (lanzar_paralelo.sh), cada worker usa un
--prefix distinto para que los MEDIAID (y por tanto los _id) nunca colisionen.

Ejemplos:
  python cargador.py --containers 1000
  python cargador.py --containers 50000 --threads 8 --batch 1000
  python cargador.py --containers 10000 --prefix LAB0_ --locators 10 50 --subclip-prob 0.4

Tras lanzar carga, vigila en el cluster:
  GET /_cat/thread_pool/write?v
  GET /_nodes/stats/indices/indexing?pretty
  GET /_cat/shards/lab_content?v       (busca hot shards por el routing)
"""
import argparse
import time

import config
from generador import generate_tree


def build_actions(fake, index, prefix, start, count, opts, counters):
    """Generador perezoso de acciones bulk para opensearch-py."""
    for n in range(count):
        seq = start + n
        mediaid = f"{prefix}{seq:08d}"
        for doc_id, routing, source in generate_tree(fake, mediaid, **opts):
            counters["docs"] += 1
            yield {
                "_op_type": "index",
                "_index": index,
                "_id": doc_id,
                "routing": routing,
                "_source": source,
            }


def main():
    ap = argparse.ArgumentParser(description="Carga masiva estilo Tedial")
    ap.add_argument("--index", default=config.OS_INDEX)
    ap.add_argument("--containers", type=int, required=True, help="Numero de containers raiz a generar")
    ap.add_argument("--prefix", default="LAB_", help="Prefijo de MEDIAID (unico por worker en paralelo)")
    ap.add_argument("--start", type=int, default=0, help="Secuencia inicial de MEDIAID")
    ap.add_argument("--locators", type=int, nargs=2, metavar=("MIN", "MAX"), default=[5, 30],
                    help="Rango de locators por container")
    ap.add_argument("--subclip-prob", type=float, default=0.3, help="Probabilidad de que un container tenga subclips")
    ap.add_argument("--subclips", type=int, nargs=2, metavar=("MIN", "MAX"), default=[1, 2])
    ap.add_argument("--subclip-locators", type=int, nargs=2, metavar=("MIN", "MAX"), default=[2, 10])
    ap.add_argument("--batch", type=int, default=500, help="chunk_size del bulk")
    ap.add_argument("--threads", type=int, default=4, help="hilos del parallel_bulk en este proceso")
    ap.add_argument("--seed", type=int, default=None, help="Semilla para reproducibilidad")
    args = ap.parse_args()

    import random
    from faker import Faker
    from opensearchpy import helpers

    if args.seed is not None:
        random.seed(args.seed)
        Faker.seed(args.seed)
    fake = Faker()

    client = config.get_client()
    opts = {
        "locators": tuple(args.locators),
        "subclip_prob": args.subclip_prob,
        "subclips": tuple(args.subclips),
        "subclip_locators": tuple(args.subclip_locators),
    }
    counters = {"docs": 0}

    actions = build_actions(fake, args.index, args.prefix, args.start, args.containers, opts, counters)

    ok = 0
    failed = 0
    t0 = time.time()
    last = t0
    print(f"[i] [{args.prefix}] cargando {args.containers} containers -> '{args.index}' "
          f"(threads={args.threads}, batch={args.batch})")

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
            if failed <= 5:
                print(f"[err] {item}")
        now = time.time()
        if now - last >= 5:
            rate = ok / (now - t0) if now > t0 else 0
            print(f"[{args.prefix}] docs_ok={ok} fail={failed} ({rate:,.0f} docs/s)")
            last = now

    dt = time.time() - t0
    rate = ok / dt if dt else 0
    print(f"[OK] [{args.prefix}] terminado: {ok} docs en {dt:,.1f}s ({rate:,.0f} docs/s), fallos={failed}")


if __name__ == "__main__":
    main()
