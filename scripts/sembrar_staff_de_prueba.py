"""Cuentas de prueba del staff · auditoría de producción (2026-11-02).

JP pidió recorrer "literal todo" con Playwright: también el administrador, el
equipo comercial de la agencia y los roles de colegio. Hasta hoy solo había
cuentas de prueba de estudiantes (`sembrar_cuentas_por_grado.py`) y del
coordinador de un programa (`sembrar_programa_de_prueba.py`). Este script crea:

- **Equipo de la agencia:** `prueba.admin` (super_admin), `prueba.comercial`
  (gh_commercial) y `prueba.asesor` (gh_advisor).
- **Un colegio de prueba** ("Colegio de Prueba Mentoring", tipo `colegio`,
  licencia activa) con `prueba.colegio.admin` (school_admin),
  `prueba.psicologa` (psychologist), `prueba.colegio.estudiante` (11°) y
  `prueba.acudiente` (parent), este último ligado al estudiante.

## Ojo: estas cuentas ven datos reales

El admin, el comercial y el asesor ven prospectos y estudiantes REALES, menores
incluidos. Por eso: claves aleatorias que se imprimen una sola vez (nunca en el
repo), ninguna clave fija, y **`--desactivar` al terminar la auditoría**.
Desactivar, no borrar: lo que se hizo con ellas queda auditado.

Lo que NO hace: no toca cuentas que no sean `prueba.*@grasshopper.dev`, no las
sincroniza con Bitrix ni les manda correos, y si una ya existe la deja como está.

Uso (lo corre JP en producción):

    heroku run -a grasshopper-api "python scripts/sembrar_staff_de_prueba.py"              # simula
    heroku run -a grasshopper-api "python scripts/sembrar_staff_de_prueba.py --aplicar"    # crea
    heroku run -a grasshopper-api "python scripts/sembrar_staff_de_prueba.py --aplicar --desactivar"
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sembrar_cuentas_por_grado as grados  # noqa: E402

COLEGIO = "Colegio de Prueba Mentoring"
SLUG = "colegio-de-prueba-mentoring"

# (usuario, nombre, rol, ¿va en el colegio?)
STAFF = [
    ("admin", "Prueba Admin", "SUPER_ADMIN", False),
    ("comercial", "Prueba Comercial", "GH_COMMERCIAL", False),
    ("asesor", "Prueba Asesor", "GH_ADVISOR", False),
    ("colegio.admin", "Prueba Colegio Admin", "SCHOOL_ADMIN", True),
    ("psicologa", "Prueba Psicóloga", "PSYCHOLOGIST", True),
    ("acudiente", "Prueba Acudiente", "PARENT", True),
]
ESTUDIANTE = grados.Cuenta(
    "colegio.estudiante", "Prueba Colegio Estudiante", "Estudiante de 11° del colegio de prueba",
    grados._colegio("high_school", 11, 11, 2010), 2010, 11,
)


def _email(usuario: str) -> str:
    return f"prueba.{usuario}@{grados.DOMINIO}"


def _colegio(db: Any, *, aplicar: bool) -> tuple[Optional[Any], str]:
    from app.db.models import School

    org = db.query(School).filter(School.slug == SLUG).first()
    if org is not None:
        return org, "ya existe (no se toca)"
    if not aplicar:
        return None, "crear"
    org = School(name=COLEGIO, slug=SLUG, tipo="colegio", license_active=True, city="Bogotá", country="CO")
    db.add(org)
    db.flush()
    return org, "crear"


def _todas() -> List[str]:
    return [_email(u) for u, *_ in STAFF] + [_email(ESTUDIANTE.usuario)]


def _de_la_agencia() -> List[str]:
    """Las que ven datos REALES (admin, comercial, asesor). Las del colegio de
    prueba solo ven ese colegio: pueden quedarse para que la clienta las use."""
    return [_email(u) for u, _, _, en_colegio in STAFF if not en_colegio]


def sembrar(db: Any, *, aplicar: bool, desactivar: bool = False, solo_agencia: bool = False) -> List[Dict[str, str]]:
    from app.api.v1.auth import get_password_hash
    from app.db.models import ParentRelationship, School, User, UserRole

    informe: List[Dict[str, str]] = []

    if desactivar:
        for email in (_de_la_agencia() if solo_agencia else _todas()):
            u = db.query(User).filter(User.email == email).first()
            informe.append({"quien": email, "accion": "desactivar" if u else "no existe", "descripcion": ""})
            if aplicar and u is not None:
                u.is_active = False
        org = db.query(School).filter(School.slug == SLUG).first()
        if aplicar and org is not None and not solo_agencia:
            org.license_active = False
        if aplicar:
            db.commit()
        return informe

    org, accion = _colegio(db, aplicar=aplicar)
    informe.append({"quien": COLEGIO, "accion": accion, "descripcion": "organización tipo colegio"})

    # El estudiante del colegio (el acudiente se liga a él).
    est = db.query(User).filter(User.email == _email(ESTUDIANTE.usuario)).first()
    fila = {"quien": _email(ESTUDIANTE.usuario), "accion": "ya existe (no se toca)", "descripcion": ESTUDIANTE.descripcion}
    if est is None:
        fila["accion"] = "crear"
        if aplicar:
            clave = grados._clave_nueva()
            est = User(email=_email(ESTUDIANTE.usuario), hashed_password=get_password_hash(clave),
                       role=UserRole.STUDENT, school_id=org.id)
            grados._aplicar_estado(est, ESTUDIANTE)
            db.add(est)
            db.flush()
            grados._asegurar_plan(db, est, ESTUDIANTE)
            fila["clave"] = clave
    informe.append(fila)

    for usuario, nombre, rol, en_colegio in STAFF:
        email = _email(usuario)
        u = db.query(User).filter(User.email == email).first()
        fila = {"quien": email, "accion": "ya existe (no se toca)", "descripcion": rol.lower()}
        if u is None:
            fila["accion"] = "crear"
            if aplicar:
                clave = grados._clave_nueva()
                u = User(email=email, name=nombre, hashed_password=get_password_hash(clave),
                         role=getattr(UserRole, rol), school_id=org.id if en_colegio else None)
                # Tratamiento de datos sí (sin él la app no deja pasar); CRM y
                # comunicaciones no, como en las demás cuentas de prueba.
                u.consent_data_processing_at = datetime.utcnow()
                u.consent_data_processing_version = "prueba"
                db.add(u)
                db.flush()
                fila["clave"] = clave
                if rol == "PARENT" and est is not None:
                    db.add(ParentRelationship(parent_user_id=u.id, student_user_id=est.id,
                                              relationship_type="madre", is_active=True))
        informe.append(fila)

    if aplicar:
        db.commit()
    return informe


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--aplicar", action="store_true", help="escribir en la base (si no, solo muestra)")
    parser.add_argument("--desactivar", action="store_true", help="apagar todas las cuentas y la licencia del colegio")
    parser.add_argument("--solo-agencia", action="store_true",
                        help="con --desactivar: apagar solo admin, comercial y asesor (ven datos reales)")
    args = parser.parse_args()

    from app.db.database import SessionLocal

    db = SessionLocal()
    try:
        informe = sembrar(db, aplicar=args.aplicar, desactivar=args.desactivar, solo_agencia=args.solo_agencia)
    finally:
        db.close()

    modo = "APLICADO" if args.aplicar else "SIMULACIÓN (nada se escribió · usa --aplicar)"
    print(f"\nStaff de prueba · {modo}\n")
    for fila in informe:
        print(f"  {fila['accion']:<24} {fila['quien']:<46} {fila['descripcion']}")
        if fila.get("clave"):
            print(f"  {'':<24} clave: {fila['clave']}")
    if any(f.get("clave") for f in informe):
        print("\n  ⚠️ Las claves se muestran solo esta vez. Guárdalas por fuera; no las pongas en el repo.\n")


if __name__ == "__main__":
    main()
