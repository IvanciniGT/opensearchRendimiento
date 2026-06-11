"""Crea (o recrea) el indice de laboratorio con el mapping real de Tedial.

El mapping se lee de un fichero JSON (por defecto datos/mapping_content.json,
que esta fuera de git). Los settings (shards/replicas/refresh) se construyen
aqui para poder experimentar sin tocar el mapping.

Ejemplos:
  python crear_indice.py                          # crea lab_content con defaults
  python crear_indice.py --recreate               # borra y recrea
  python crear_indice.py --shards 1 --replicas 0  # config minima para linea base
  python crear_indice.py --shards 4 --replicas 1  # replica su entorno real
"""
import argparse
import json
import os
import sys

import config

DEFAULT_MAPPING = os.path.join(os.path.dirname(__file__), "..", "datos", "mapping_content.json")


def main():
    ap = argparse.ArgumentParser(description="Crear indice de laboratorio")
    ap.add_argument("--index", default=config.OS_INDEX)
    ap.add_argument("--mapping", default=DEFAULT_MAPPING, help="Fichero JSON con la clave 'mappings'")
    ap.add_argument("--shards", type=int, default=config.DEFAULT_SHARDS)
    ap.add_argument("--replicas", type=int, default=config.DEFAULT_REPLICAS)
    ap.add_argument("--refresh-interval", default=None,
                    help="p.ej. '-1' para desactivar refresh durante carga masiva, o '1s'")
    ap.add_argument("--recreate", action="store_true", help="Borra el indice si existe")
    args = ap.parse_args()

    with open(args.mapping, encoding="utf-8") as f:
        mapping_doc = json.load(f)
    mappings = mapping_doc.get("mappings", mapping_doc)

    index_settings = {
        "number_of_shards": args.shards,
        "number_of_replicas": args.replicas,
        "analysis": {"analyzer": {"default": {"type": "standard"}}},
    }
    if args.refresh_interval is not None:
        index_settings["refresh_interval"] = args.refresh_interval

    body = {"settings": {"index": index_settings}, "mappings": mappings}

    client = config.get_client()

    if client.indices.exists(index=args.index):
        if args.recreate:
            print(f"[i] Borrando indice existente '{args.index}'...")
            client.indices.delete(index=args.index)
        else:
            print(f"[!] El indice '{args.index}' ya existe. Usa --recreate para borrarlo.",
                  file=sys.stderr)
            sys.exit(1)

    print(f"[i] Creando '{args.index}'  shards={args.shards} replicas={args.replicas}"
          + (f" refresh={args.refresh_interval}" if args.refresh_interval is not None else ""))
    client.indices.create(index=args.index, body=body)
    print(f"[OK] Indice '{args.index}' creado.")


if __name__ == "__main__":
    main()
