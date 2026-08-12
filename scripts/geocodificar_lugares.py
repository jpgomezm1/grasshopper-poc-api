"""Le pone coordenadas a los lugares de los dos catálogos · una sola vez.

    python scripts/geocodificar_lugares.py            # sólo lo que falta
    python scripts/geocodificar_lugares.py --rehacer  # también lo ya resuelto
    python scripts/geocodificar_lugares.py --limite 20

Recorre los lugares distintos de `programs` y `programas_investigados`, los
normaliza con `services/lugares.py` y guarda lat/lng en la tabla `lugares`.

## Lo que este script NO hace

**No adivina.** Si Nominatim no encuentra el lugar, la fila queda con
`precision='sin_resolver'` y sin coordenadas. Un pin en el sitio equivocado es
peor que un pin que no está: el estudiante confía en lo que ve en un mapa.

Lo mismo con los campos que traen varios lugares a la vez —
`'Madrid, Valencia, Canarias'`, `'Chelmsford, Cambridge'`— que se detectan
antes de preguntar y se marcan `sin_resolver` sin gastar una petición.

Y cuando el geocodificador devuelve algo más grande que una ciudad
(`'Ontario'` es una provincia), se guarda con `precision='region'`: la
coordenada sirve para orientar, no para decir "la universidad queda aquí". La
interfaz puede tratarlas distinto.

## Por qué va despacio a propósito

Nominatim es gratis y lo mantiene la comunidad de OpenStreetMap. Su política de
uso pide **como máximo una petición por segundo** y un User-Agent que
identifique a quien llama. Se respeta: son ~890 lugares, unos 15 minutos, y se
corre una sola vez. Saltarse eso es la forma de que nos bloqueen la IP.

## TLS en Windows

Esta máquina tiene Avast interceptando el TLS, y Python no reconoce su
certificado (usa `certifi`, no el almacén de Windows). El script exporta los
certificados del sistema a un PEM temporal y lo usa para verificar. En un host
normal esto no hace nada y la verificación sigue siendo la de siempre —
**nunca se desactiva**.
"""
from __future__ import annotations

import argparse
import logging
import os
import ssl
import sys
import tempfile
import time
from datetime import datetime
from typing import Dict, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Lugar, Program, ProgramaInvestigado  # noqa: E402
from app.services.lugares import (  # noqa: E402
    clave_lugar,
    nombre_de_ciudad,
    pais_canonico,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("geocodificar")

NOMINATIM = "https://nominatim.openstreetmap.org/search"
# La política de uso de Nominatim exige identificarse con algo real.
USER_AGENT = "Grasshopper/1.0 (plataforma de orientación vocacional · contacto: soporte@grasshopper.co)"
PAUSA_S = 1.1  # su límite es 1 req/s · un pelo por encima para no rozarlo

#: Lo que Nominatim considera "una ciudad". Cualquier otra cosa es más grande y
#: se marca como región.
TIPOS_CIUDAD = {"city", "town", "village", "municipality", "hamlet", "suburb"}


def _bundle_de_certificados() -> Optional[str]:
    """Exporta los certificados del almacén de Windows a un PEM temporal.

    Devuelve `None` fuera de Windows · ahí `requests` ya funciona con certifi.
    """
    if not hasattr(ssl, "enum_certificates"):
        return None
    try:
        pem = []
        for store in ("ROOT", "CA"):
            for der, enc, _trust in ssl.enum_certificates(store):
                if enc == "x509_asn":
                    pem.append(ssl.DER_cert_to_PEM_cert(der))
        if not pem:
            return None
        fd, ruta = tempfile.mkstemp(suffix=".pem", prefix="ca-windows-")
        with os.fdopen(fd, "w") as f:
            f.write("".join(pem))
        logger.info("TLS · usando %d certificados del almacén de Windows", len(pem))
        return ruta
    except Exception:  # pragma: no cover
        return None


def _parece_varios_lugares(ciudad: str) -> bool:
    """`'Madrid, Valencia, Canarias'` no es un punto · no se pregunta siquiera."""
    return any(sep in ciudad for sep in (",", "/", " y ", " & ", ";"))


def _lugares_de_los_catalogos(db) -> Dict[str, Tuple[str, str]]:
    """`{clave: (ciudad para mostrar, iso)}` de las dos tablas juntas."""
    encontrados: Dict[str, Tuple[str, str]] = {}

    filas = (
        db.query(Program.city, Program.country)
        .filter(Program.active == True)  # noqa: E712
        .distinct()
        .all()
    )
    filas += db.query(ProgramaInvestigado.ciudad, ProgramaInvestigado.pais).distinct().all()

    for ciudad, pais in filas:
        clave = clave_lugar(ciudad, pais)
        if clave and clave not in encontrados:
            encontrados[clave] = (nombre_de_ciudad(ciudad), pais_canonico(pais).iso)
    return encontrados


def _preguntar(sesion: requests.Session, ciudad: str, iso: str, verify) -> Optional[dict]:
    try:
        r = sesion.get(
            NOMINATIM,
            params={
                "city": ciudad,
                # Acotar por país evita el clásico Birmingham UK / Birmingham
                # Alabama, y de paso hace la búsqueda mucho más precisa.
                "countrycodes": iso.lower(),
                "format": "jsonv2",
                "limit": 1,
            },
            headers={"User-Agent": USER_AGENT},
            timeout=20,
            verify=verify,
        )
        if r.status_code != 200:
            logger.warning("  HTTP %s para %s/%s", r.status_code, ciudad, iso)
            return None
        datos = r.json()
        return datos[0] if datos else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("  fallo de red para %s/%s: %s", ciudad, iso, exc)
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rehacer", action="store_true",
                    help="vuelve a preguntar también por lo ya resuelto")
    ap.add_argument("--limite", type=int, default=None,
                    help="corta después de N peticiones (para probar)")
    args = ap.parse_args()

    verify = _bundle_de_certificados() or True
    db = SessionLocal()
    sesion = requests.Session()

    try:
        lugares = _lugares_de_los_catalogos(db)
        ya = {l.clave: l for l in db.query(Lugar).all()}
        logger.info("lugares en los catálogos: %d · ya en la tabla: %d",
                    len(lugares), len(ya))

        pendientes = [
            clave for clave in lugares
            # Idempotente: sólo se pregunta por lo que no tiene coordenadas.
            # Correrlo dos veces no gasta una sola petición de más.
            if args.rehacer or clave not in ya or ya[clave].lat is None
        ]
        # Lo ya marcado `sin_resolver` no se reintenta salvo `--rehacer`: no va
        # a cambiar de opinión y son minutos de espera.
        if not args.rehacer:
            pendientes = [
                c for c in pendientes
                if not (c in ya and ya[c].precision == "sin_resolver")
            ]
        if args.limite:
            pendientes = pendientes[: args.limite]

        logger.info("por geocodificar: %d (~%d min)\n",
                    len(pendientes), round(len(pendientes) * PAUSA_S / 60))

        conteo = {"ciudad": 0, "region": 0, "sin_resolver": 0}

        for i, clave in enumerate(pendientes, 1):
            ciudad, iso = lugares[clave]
            fila = ya.get(clave)
            if fila is None:
                fila = Lugar(clave=clave, ciudad=ciudad, pais_iso=iso)
                db.add(fila)
                ya[clave] = fila

            if _parece_varios_lugares(ciudad or ""):
                fila.precision = "sin_resolver"
                fila.fuente = "descartado"
                fila.verificado_en = datetime.utcnow()
                conteo["sin_resolver"] += 1
                logger.info("[%d/%d] %s · %s → varios lugares en un campo",
                            i, len(pendientes), ciudad, iso)
                continue

            resultado = _preguntar(sesion, ciudad, iso, verify)
            time.sleep(PAUSA_S)

            if not resultado:
                fila.precision = "sin_resolver"
                fila.fuente = "nominatim"
                fila.verificado_en = datetime.utcnow()
                conteo["sin_resolver"] += 1
                logger.info("[%d/%d] %s · %s → no encontrado",
                            i, len(pendientes), ciudad, iso)
                continue

            tipo = (resultado.get("addresstype") or resultado.get("type") or "").lower()
            precision = "ciudad" if tipo in TIPOS_CIUDAD else "region"
            fila.lat = float(resultado["lat"])
            fila.lng = float(resultado["lon"])
            fila.precision = precision
            fila.fuente = "nominatim"
            fila.verificado_en = datetime.utcnow()
            conteo[precision] += 1
            logger.info("[%d/%d] %s · %s → %s (%s)",
                        i, len(pendientes), ciudad, iso, precision, tipo or "?")

            # Se guarda cada 25 · si el script se corta a los 12 minutos, no se
            # pierde el trabajo hecho.
            if i % 25 == 0:
                db.commit()

        db.commit()
        logger.info("\nlisto · ciudad=%d region=%d sin_resolver=%d",
                    conteo["ciudad"], conteo["region"], conteo["sin_resolver"])
        return 0
    finally:
        db.close()
        if isinstance(verify, str):
            try:
                os.unlink(verify)
            except OSError:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
