"""Configuracion y cliente OpenSearch para el laboratorio de carga.

Todo es sobreescribible por variables de entorno para no hardcodear nada
sensible en los scripts. Valores por defecto = cluster del curso.
"""
import os

OS_URL = os.environ.get("OS_URL", "https://opensearch.iochannel.tech")
OS_USER = os.environ.get("OS_USER", "admin")
OS_PASS = os.environ.get("OS_PASS", "Pa$$w0rd2026")

# Indice de laboratorio (nombre controlado, NO toca nada de produccion)
OS_INDEX = os.environ.get("OS_INDEX", "lab_content")

# El cluster usa certificado autofirmado -> por defecto no verificamos.
OS_VERIFY_CERTS = os.environ.get("OS_VERIFY_CERTS", "false").lower() in ("1", "true", "yes")

# Defaults del indice de lab. 3 nodos -> 3 shards reparte 1 primario por nodo.
DEFAULT_SHARDS = int(os.environ.get("OS_SHARDS", "3"))
DEFAULT_REPLICAS = int(os.environ.get("OS_REPLICAS", "1"))


def get_client(timeout: int = 120):
    """Devuelve un cliente OpenSearch listo para usar."""
    from opensearchpy import OpenSearch

    if not OS_VERIFY_CERTS:
        # Silenciar el warning de certificado autofirmado.
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    return OpenSearch(
        hosts=[OS_URL],
        http_auth=(OS_USER, OS_PASS),
        verify_certs=OS_VERIFY_CERTS,
        ssl_show_warn=False,
        timeout=timeout,
        max_retries=3,
        retry_on_timeout=True,
    )
