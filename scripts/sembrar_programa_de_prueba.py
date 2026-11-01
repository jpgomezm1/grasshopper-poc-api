"""Un programa de prueba · F-2/F-4, Sprint 4 (2026-11-01).

F-2/F-4 dieron a las organizaciones un tipo (`schools.tipo`: colegio · programa
· empresa) y un panel acorde: un programa o una empresa no ven datos clínicos ni
invitan psicólogos, y su tablero muestra solo agregados con mínimo 5 personas
(`tablero_anonimo_service`). En producción no existe ninguna organización de
tipo programa, así que nadie había podido ver ese panel. Este script crea una,
con el mismo cuidado que `sembrar_cuentas_por_grado.py`:

- **"Programa de Prueba Mentoring"**, tipo `programa`, licencia activa.
- **Un coordinador** (`school_admin`) para entrar al panel.
- **Seis participantes** con el onboarding hecho y plan `pago` sin vencimiento.
  Son seis y no menos porque el tablero no muestra nada por debajo de 5: con
  menos, lo único que se vería es el aviso de "aún no hay suficientes".

## Lo que NO hace, a propósito

- No sincroniza con Bitrix ni manda correos (los consentimientos de CRM y
  comunicaciones quedan vacíos, igual que en las cuentas por grado).
- No inventa tests ni resultados: se hacen entrando con las cuentas.
- Solo toca lo suyo: `prueba.programa.*@grasshopper.dev` y la organización con
  su slug. Si ya existen, no las pisa.

## Las claves

Aleatorias, impresas UNA vez al crear. No hay ninguna en el repo.

## Uso (en producción, lo corre JP)

    heroku run "python scripts/sembrar_programa_de_prueba.py"             # muestra qué haría
    heroku run "python scripts/sembrar_programa_de_prueba.py --aplicar"   # lo crea
    heroku run "python scripts/sembrar_programa_de_prueba.py --aplicar --desactivar"
        # apaga las cuentas y la licencia del programa cuando termine la validación
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Se reusa el script de las cuentas por grado (estado inicial, plan, claves) en
# vez de copiarlo: si cambia lo obligatorio del onboarding, cambia en los dos.
_RUTA_GRADOS = Path(__file__).resolve().parent / "sembrar_cuentas_por_grado.py"
_spec = importlib.util.spec_from_file_location("sembrar_cuentas_por_grado", _RUTA_GRADOS)
grados = sys.modules.get(_spec.name) or importlib.util.module_from_spec(_spec)
if _spec.name not in sys.modules:
    sys.modules[_spec.name] = grados  # `@dataclass` busca el módulo aquí
    _spec.loader.exec_module(grados)

NOMBRE = "Programa de Prueba Mentoring"
SLUG = "programa-de-prueba-mentoring"
TIPO = "programa"

COORDINADOR = f"prueba.programa.coordinador@{grados.DOMINIO}"

# Un programa (un bootcamp, una beca, una aceleradora) reúne a adultos: tres
# universitarios y tres que ya trabajan, para que el tablero tenga de los dos.
PARTICIPANTES: List[Any] = [
    grados.Cuenta(
        f"programa.{i}",
        f"Prueba Programa {i}",
        "Participante del programa de prueba · onboarding hecho",
        grados._onboarding("university" if i <= 3 else "working", **grados._CARRERA),
        2004 if i <= 3 else 1995,
    )
    for i in range(1, 7)
]


def _organizacion(db: Any, *, aplicar: bool) -> tuple[Any, str]:
    from app.db.models import School

    org = db.query(School).filter(School.slug == SLUG).first()
    if org is not None:
        return org, "ya existe (no se toca)"
    if not aplicar:
        return None, "crear"
    org = School(
        name=NOMBRE,
        slug=SLUG,
        tipo=TIPO,
        license_active=True,
        city="Bogotá",
        country="CO",
    )
    db.add(org)
    db.flush()  # para tener `org.id` y enlazar las cuentas
    return org, "crear"


def sembrar(db: Any, *, aplicar: bool, desactivar: bool = False) -> List[Dict[str, str]]:
    """Crea lo que falte · devuelve qué pasó con cada cosa (y la clave, si la hay)."""
    from app.api.v1.auth import get_password_hash
    from app.db.models import School, User, UserRole

    informe: List[Dict[str, str]] = []

    if desactivar:
        org = db.query(School).filter(School.slug == SLUG).first()
        informe.append({"quien": NOMBRE, "accion": "desactivar licencia" if org else "no existe", "descripcion": TIPO})
        if aplicar and org is not None:
            org.license_active = False
        for email in [COORDINADOR] + [c.email for c in PARTICIPANTES]:
            u = db.query(User).filter(User.email == email).first()
            informe.append({"quien": email, "accion": "desactivar" if u else "no existe", "descripcion": ""})
            if aplicar and u is not None:
                u.is_active = False
        if aplicar:
            db.commit()
        return informe

    org, accion = _organizacion(db, aplicar=aplicar)
    informe.append({"quien": NOMBRE, "accion": accion, "descripcion": f"organización tipo {TIPO}"})

    # El coordinador · entra al panel de la organización.
    u = db.query(User).filter(User.email == COORDINADOR).first()
    fila = {"quien": COORDINADOR, "accion": "ya existe (no se toca)", "descripcion": "Coordinador del programa (panel)"}
    if u is None:
        fila["accion"] = "crear"
        if aplicar:
            clave = grados._clave_nueva()
            u = User(
                email=COORDINADOR,
                name="Coordinación Programa de Prueba",
                hashed_password=get_password_hash(clave),
                role=UserRole.SCHOOL_ADMIN,
                school_id=org.id,
            )
            # Tratamiento de datos sí (sin él la app no deja pasar); CRM y
            # comunicaciones no, como en las cuentas por grado.
            u.consent_data_processing_at = datetime.utcnow()
            u.consent_data_processing_version = "prueba"
            db.add(u)
            fila["clave"] = clave
    informe.append(fila)

    # Los participantes · estudiantes de la organización, con plan pago.
    for c in PARTICIPANTES:
        u = db.query(User).filter(User.email == c.email).first()
        fila = {"quien": c.email, "accion": "ya existe (no se toca)", "descripcion": c.descripcion}
        if u is None:
            fila["accion"] = "crear"
            if aplicar:
                clave = grados._clave_nueva()
                u = User(
                    email=c.email,
                    hashed_password=get_password_hash(clave),
                    role=UserRole.STUDENT,
                    school_id=org.id,
                )
                grados._aplicar_estado(u, c)
                db.add(u)
                db.flush()
                grados._asegurar_plan(db, u, c)
                fila["clave"] = clave
        informe.append(fila)

    if aplicar:
        db.commit()
    return informe


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--aplicar", action="store_true", help="escribir en la base (si no, solo muestra)")
    parser.add_argument("--desactivar", action="store_true", help="apagar las cuentas y la licencia del programa")
    args = parser.parse_args()

    from app.db.database import SessionLocal

    db = SessionLocal()
    try:
        informe = sembrar(db, aplicar=args.aplicar, desactivar=args.desactivar)
    finally:
        db.close()

    modo = "APLICADO" if args.aplicar else "SIMULACIÓN (nada se escribió · usa --aplicar)"
    print(f"\nPrograma de prueba · {modo}\n")
    for fila in informe:
        print(f"  {fila['accion']:<24} {fila['quien']:<48} {fila['descripcion']}")
        if fila.get("clave"):
            print(f"  {'':<24} clave: {fila['clave']}")
    if any(f.get("clave") for f in informe):
        print("\n  ⚠️ Las claves se muestran solo esta vez. Pásalas por fuera; no las guardes en el repo.\n")


if __name__ == "__main__":
    main()
