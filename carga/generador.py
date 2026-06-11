"""Generador de documentos estilo Tedial (CONTAINER / LOCATOR / SUBCLIP).

Reproduce lo esencial del modelo real:
  - CONTAINER  -> join_field {name: level_1}              (raiz)
  - LOCATOR    -> join_field {parent: <mediaid>, name: level_2}
  - SUBCLIP    -> join_field {parent: <mediaid>, name: subclip}      (es un CONTAINER)
  - LOC subclip-> join_field {parent: <subclip_id>, name: subclip_level_2}

CLAVE: el parent-child join de OpenSearch obliga a que TODA la familia
(container raiz + sus locators + subclips + locators de subclips) viva en el
MISMO shard. Por eso el routing de TODOS los documentos del arbol es SIEMPRE
el MEDIAID del container raiz. Esto es exactamente lo que se ve en sus datos
reales y es el origen natural de "hot shards" (una media con 500 locators
manda los 500 al mismo shard).

Las secciones y campos generados coinciden con el mapping real (datos/mapping_content.json)
para que las busquedas de tedial.md funcionen tal cual.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

# --- Vocabularios controlados (cardinalidad realista para facetas/aggs) ---
SITES = ["Phase2"]
SUBTYPES = ["VIDEO", "AUDIO", "IMAGE", "DOCUMENT", "SEQUENCE"]
TYPES = ["Multimedia", "News", "Sports", "Movie", "Series", "Promo"]
CONTENT_KINDS = ["Original", "Proxy", "Master", "Lowres"]
DEPLOYMENTS = ["onprem", "cloud", "hybrid"]
CODECS = ["XAVC", "H264", "ProRes", "MPEG2", "DNxHD", "HEVC"]
DEFINITIONS = ["SD", "HD", "UHD", "4K"]
WRAPPERS = ["QT/ISO", "MXF", "MP4", "GXF"]
EDIT_RATES = ["25 1", "24000 1001", "30000 1001", "50 1", "60000 1001"]
ASPECT_RATIOS = ["16:9", "4:3", "21:9", "1:1"]
COLOR_PRIMARIES = ["BT.709", "BT.2020", "BT.601"]
DISPLAY_NAMES = ["ISO-XAVC", "MXF-OP1a", "ProRes-HQ", "H264-HD"]
USERS = ["swork", "administrator", "jdoe", "mlopez", "agarcia", "operator", "ingest_bot"]
GROUPS_POOL = ["everyone", "Catalogators", "Journalists", "Editors", "Sports", "Archive"]

# Tipos de locator y la seccion STRATA_CORE/DYNAMIC asociada
LOCATOR_TYPES = ["QC", "COM", "FOOTBALL", "SPEECH_ROUND", "SUBJECT_MATTER", "RIGHTS", "NONTRANS"]
SOURCE_ENGINES = ["BATON", "MANUAL", "AI_VISION", "SPEECH2TEXT", "INGEST"]
SOURCE_APPS = ["Voyager", "QCStation", "AutoTag", "Newsroom"]
LOCATOR_COLORS = ["red", "green", "blue", "yellow", "orange", "purple", "cyan"]
QC_GRADES = ["INFO", "WARNING", "ERROR", "CRITICAL"]
QC_FAULTS = ["VIDEO_QUALITY", "AUDIO_LEVEL", "BLACK_FRAME", "FREEZE", "SILENCE", "COLOR_BARS"]
FOOTBALL_TEAMS = ["Madrid FC", "Barca United", "Sevilla CF", "Valencia", "Bilbao", "Vigo"]
COMPETITIONS = ["La Liga", "Champions", "Copa", "Premier", "Serie A"]


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _epoch_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _rand_dt(fake, start_days_ago=720):
    base = datetime.now(timezone.utc) - timedelta(days=random.randint(0, start_days_ago))
    return base - timedelta(seconds=random.randint(0, 86400))


def _groups():
    extra = random.sample(GROUPS_POOL[1:], k=random.randint(0, 2))
    return ["everyone"] + extra


def _container_sections(fake, mediaid, subtype=None, issubclip=False, title=None):
    """Devuelve las secciones tipicas de un CONTAINER (o SUBCLIP)."""
    cdt = _rand_dt(fake)
    lmod = cdt + timedelta(seconds=random.randint(0, 3600))
    lmod_ms = _epoch_ms(lmod)
    subtype = subtype or random.choice(SUBTYPES)
    title = title or fake.sentence(nb_words=random.randint(2, 6)).rstrip(".")

    src = {
        "EDITORIAL--CONTAINER": {
            "SUBTYPE": subtype,
            "MEDIAID": mediaid,
            "SITE": random.choice(SITES),
            "CREATIONDATE": _iso(cdt),
            "LASTMODIFICATIONDATE": _iso(lmod),
            "TYPE": random.choice(TYPES),
            "CONTENTKIND": random.choice(CONTENT_KINDS),
            "DEPLOYMENT": random.choice(DEPLOYMENTS),
            "CREATEDBY": random.choice(USERS),
            "ISSUBCLIP": issubclip,
            "gelastic_lastmodificationdate": lmod_ms,
        },
        "EDITORIAL_CORE--EDC_DUBLIN_CORE": {
            "DC_DESCRIPTION": {
                "DM_TITLE": title,
                "DM_SUBTITLE": fake.sentence(nb_words=3).rstrip("."),
                "DM_DESCRIPTION": fake.paragraph(nb_sentences=random.randint(1, 3)),
            },
            "DC_IDENTIFIER": mediaid,
            "DC_CREATOR": {"ENTITY_NAME": fake.name()},
            "DC_LOCATION": fake.city(),
            "DC_EPISODE_NUM": random.randint(1, 200),
            "gelastic_lastmodificationdate": lmod_ms,
        },
        "EDITORIAL_CORE--TECHNICAL_INFO": {
            "DEFINITION": random.choice(DEFINITIONS),
            "CODEC": random.choice(CODECS),
            "EDIT_RATE": random.choice(EDIT_RATES),
            "COLOR_PRIMARIES": random.choice(COLOR_PRIMARIES),
            "WRAPPER": random.choice(WRAPPERS),
            "ASPECT_RATIO": random.choice(ASPECT_RATIOS),
            "DURATION": random.randint(5, 7200),
            "DISPLAY_NAME": random.choice(DISPLAY_NAMES),
            "BITRATE": str(random.randint(2_000_000, 80_000_000)),
            "gelastic_lastmodificationdate": lmod_ms,
        },
        "MEDIAFILE--MEDIAFILE": {
            "MEDIAID": mediaid,
            "TITLE": title,
            "TRACKS": [
                {
                    "TRACKTYPE": "VIDEO",
                    "TRACKNUMBER": 0,
                    "CHANNELS": [{"HR": [{"SOBJECTNODEID": 0}], "CHANNELNUMBER": 0}],
                }
            ],
            "gelastic_lastmodificationdate": lmod_ms,
        },
        "MEDIAFILE_CORE--MEDIAFILE": {
            "TXREADY": random.random() > 0.2,
            "gelastic_lastmodificationdate": lmod_ms,
        },
    }
    return src, lmod_ms


def _wrap_doc(src, doc_type, join_field, site, lmod_ms):
    """Anade los campos comunes de nivel raiz y devuelve el _source final."""
    now = datetime.now(timezone.utc)
    src["@timestamp"] = _iso(now)
    src["gelastic_indexdate"] = _epoch_ms(now)
    src["doc_type"] = doc_type
    src["@group_permissions"] = {"groups": _groups(), "gelastic_lastmodificationdate": lmod_ms}
    src["@site"] = site
    src["join_field"] = join_field
    src["gelastic_lastmodificationdate"] = lmod_ms
    src["gelastic_deleted"] = False
    return src


def build_container(fake, mediaid):
    src, lmod = _container_sections(fake, mediaid, issubclip=False)
    site = src["EDITORIAL--CONTAINER"]["SITE"]
    return _wrap_doc(src, "CONTAINER", {"name": "level_1"}, site, lmod)


def build_subclip(fake, subclip_id, parent_mediaid):
    src, lmod = _container_sections(
        fake, subclip_id, subtype="SEQUENCE", issubclip=True,
        title="(Subclip) " + fake.sentence(nb_words=3).rstrip("."),
    )
    site = src["EDITORIAL--CONTAINER"]["SITE"]
    join = {"parent": parent_mediaid, "name": "subclip"}
    return _wrap_doc(src, "CONTAINER", join, site, lmod)


def build_locator(fake, parent_id, locatorid, join_name):
    """Construye un LOCATOR (doc independiente) con su seccion STRATA segun tipo."""
    ltype = random.choice(LOCATOR_TYPES)
    entry = random.randint(0, 7000)
    dur = random.randint(1, 600)
    ldt = _rand_dt(fake)
    lmod_ms = _epoch_ms(ldt)

    src = {
        "STRATA--LOCATOR": {
            "MEDIAID": parent_id,
            "SITE": random.choice(SITES),
            "SCORE": random.randint(0, 100),
            "CATALOGATIONOBJECT": ltype,
            "LOCATORID": locatorid,
            "SEGMENTENTRYPOINT": entry,
            "SEGMENTDURATION": dur,
            "DESCRIPTION": fake.sentence(nb_words=random.randint(4, 12)),
            "TYPEID": f"STRATA_CORE:{ltype}",
            "EDITRATE": random.choice(EDIT_RATES),
            "TEMPLATE": "STRATA_CORE",
            "CONFIDENCE": round(random.random(), 3),
            "KEYWORDS": " ".join(fake.words(nb=random.randint(1, 5))),
            "PARTICIPANTS": ", ".join(fake.name() for _ in range(random.randint(0, 3))),
            "SOURCEAPPLICATION": random.choice(SOURCE_APPS),
            "SOURCEENGINE": random.choice(SOURCE_ENGINES),
            "COLOR": random.choice(LOCATOR_COLORS),
            "TIME": _iso(ldt),
            "gelastic_lastmodificationdate": lmod_ms,
        }
    }

    # Seccion especifica segun tipo de locator (igual que el modelo real)
    if ltype == "QC":
        src["STRATA_CORE--QC"] = {
            "GRADE": random.choice(QC_GRADES),
            "FAULT": random.choice(QC_FAULTS),
            "gelastic_lastmodificationdate": lmod_ms,
        }
    elif ltype == "FOOTBALL":
        src["STRATA_DYNAMIC--FOOTBALL"] = {
            "HOME_TEAM_NAME": random.choice(FOOTBALL_TEAMS),
            "AWAY_TEAM_NAME": random.choice(FOOTBALL_TEAMS),
            "HOME_SCORE": str(random.randint(0, 5)),
            "AWAY_SCORE": str(random.randint(0, 5)),
            "COMPETITION_NAME": random.choice(COMPETITIONS),
            "SEASON": f"{random.randint(2018, 2026)}",
            "gelastic_lastmodificationdate": lmod_ms,
        }
    elif ltype == "SPEECH_ROUND":
        src["STRATA_CORE--SPEECH_ROUND"] = {
            "SPEAKER": fake.name(),
            "SUBJECT_MATTER": fake.word(),
            "DESCRIPTION": fake.sentence(),
            "gelastic_lastmodificationdate": lmod_ms,
        }
    elif ltype == "SUBJECT_MATTER":
        src["STRATA_CORE--SUBJECT_MATTER"] = {
            "CODE": fake.lexify(text="??-####").upper(),
            "TITLE": fake.sentence(nb_words=3).rstrip("."),
            "DESCRIPTION": fake.sentence(),
            "gelastic_lastmodificationdate": lmod_ms,
        }
    elif ltype == "RIGHTS":
        src["STRATA_CORE--RIGHTS"] = {
            "CONTRACT": fake.bothify(text="CTR-#####"),
            "RESTRICTION": random.choice(["NONE", "EMBARGO", "GEOBLOCK", "INTERNAL"]),
            "SCOPE": random.choice(["WORLD", "EU", "ES", "WEB"]),
            "gelastic_lastmodificationdate": lmod_ms,
        }

    site = src["STRATA--LOCATOR"]["SITE"]
    join = {"parent": parent_id, "name": join_name}
    return _wrap_doc(src, "LOCATOR", join, site, lmod_ms)


def generate_tree(fake, mediaid, *, locators=(5, 30), subclip_prob=0.3,
                  subclips=(1, 2), subclip_locators=(2, 10)):
    """Genera un arbol completo para un container raiz.

    Yields tuplas (doc_id, routing, source). El routing SIEMPRE es `mediaid`
    (el container raiz), porque el join exige misma familia = mismo shard.

    Parametros de rango son tuplas (min, max).
    """
    routing = mediaid

    # 1) CONTAINER raiz
    yield mediaid, routing, build_container(fake, mediaid)

    # 2) LOCATORS del container raiz (level_2)
    nloc = random.randint(*locators)
    for i in range(nloc):
        locid = i + 1
        lid = f"{mediaid}:L{locid}"
        yield lid, routing, build_locator(fake, mediaid, locid, "level_2")

    # 3) SUBCLIPS (opcionales) y sus propios locators (subclip_level_2)
    if random.random() < subclip_prob:
        nsub = random.randint(*subclips)
        for s in range(nsub):
            subclip_id = f"{mediaid}S{s:05d}:{mediaid}"
            yield subclip_id, routing, build_subclip(fake, subclip_id, mediaid)
            for j in range(random.randint(*subclip_locators)):
                locid = j + 1
                lid = f"{subclip_id}:L{locid}"
                # parent = subclip; pero routing sigue siendo el container raiz
                yield lid, routing, build_locator(fake, subclip_id, locid, "subclip_level_2")
