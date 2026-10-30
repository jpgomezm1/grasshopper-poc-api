"""Cuentas de prueba por grado · K-1, Sprint 4 (2026-10-29).

Verónica, feedback de Sprint 4: *"ESTUVE REVISANDO TODOS LOS LOGINS O USUARIOS
REALMENTE SE VEN MUY CHEVERES PERO ME PARECE DIFICIL EVALUARLOS YA QUE NO SE
TIENEN MUCHOS USUARIOS DE UN COLEGIO Y NO SE COMO HACER PARA CREAR NUEVOS"*.

Las cuentas sembradas hasta hoy (`seed_test_data.py`) no tienen grado, así que
no sirven para revisar lo que cambia entre 9°, 10°, 11°, 12° y profesional, que
es justo lo que pide este sprint. Este script crea un juego fijo:

- **Una por ruta, con el onboarding hecho** (grado, etapa y lo obligatorio):
  entra directo a la plataforma de ese grado.
- **Tres "nuevas"**, sin onboarding, para recorrer el registro desde cero.

## Lo que NO hace, a propósito

- **No las sincroniza con Bitrix ni les manda correos**: `consent_crm_sync_at`
  y `consent_communications_at` quedan vacíos. Son cuentas de prueba y no
  deben aparecer en el CRM de la agencia ni recibir el acompañamiento periódico.
- **No inventa tests ni resultados**: el onboarding sí, porque sin él no se
  puede entrar a la ruta del grado; los tests los hace quien prueba.
- **No toca cuentas que no sean suyas**: todas son `prueba.*@grasshopper.dev`.
  Si una ya existe, la deja como está (no le borra lo que ya hicieron con ella),
  salvo con `--reiniciar`.

## Cuando existan los planes (D-1)

Hay que agregar la variante por plan (gratis / pago / VIP). Hoy no existe el
concepto de plan por usuario, así que sembrarlo sería inventar un campo.

## Uso

    ./venv/Scripts/python scripts/sembrar_cuentas_por_grado.py             # muestra qué haría
    ./venv/Scripts/python scripts/sembrar_cuentas_por_grado.py --aplicar   # las crea
    ./venv/Scripts/python scripts/sembrar_cuentas_por_grado.py --aplicar --reiniciar
        # además devuelve las existentes a su estado inicial

⚠️ `DATABASE_URL` del `.env` local es la base de PRODUCCIÓN. `--aplicar`
escribe ahí.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Consola de Windows en cp1252 · ver el mismo arreglo en `seed_test_data.py`.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CLAVE = "Prueba2026!"
DOMINIO = "grasshopper.dev"


@dataclass(frozen=True)
class Cuenta:
    usuario: str
    nombre: str
    descripcion: str
    # `None` = cuenta nueva, sin onboarding.
    respuestas: Optional[Dict[str, Any]] = None
    anio_nacimiento: Optional[int] = None
    grado: Optional[int] = field(default=None)

    @property
    def email(self) -> str:
        return f"prueba.{self.usuario}@{DOMINIO}"


def _onboarding(life_stage: str, **extra: Any) -> Dict[str, Any]:
    """Lo obligatorio del onboarding (`OBLIGATORIOS`) + lo propio de la ruta."""
    base = {
        "life_stage": life_stage,
        "voice_passion": "Me gusta entender cómo funcionan las cosas y explicárselas a otros.",
        "voice_strengths": "Soy organizada, curiosa y me va bien trabajando en equipo.",
        "main_goal": "discover",
        "timeline": "1_year",
    }
    base.update({k: v for k, v in extra.items() if v is not None})
    return base


# El año de nacimiento sale del grado con la edad típica en Colombia a fines de
# 2026 (9° ≈ 14 años). Son menores: por eso el script marca el consentimiento
# parental, si no la cuenta quedaría detenida en la pantalla de permiso.
def _colegio(life_stage: str, grado: int, ultimo: int, anio: int) -> Dict[str, Any]:
    # `birthdate` también va en las respuestas, con el formato que guarda el
    # onboarding (`YYYY-12-31`): para colegio es obligatorio, y sin él la app
    # la devuelve a terminar el registro.
    return _onboarding(
        life_stage, grade=str(grado), school_last_grade=str(ultimo), birthdate=f"{anio}-12-31",
    )


# Lo obligatorio del perfil profesional (`OBLIGATORIO_SI_PERFIL`): satisfacción,
# puesto ideal y el texto de LinkedIn.
_CARRERA = {
    "career_job_satisfaction_score": 3,
    "career_target_role": "Analista de datos en una empresa de tecnología",
    "career_linkedin_profile_text": (
        "Administrador de empresas con 6 años de experiencia en operaciones y "
        "reportes. Manejo Excel avanzado y SQL básico. Quiero moverme a analítica."
    ),
}

CUENTAS: List[Cuenta] = [
    Cuenta("grado9", "Prueba Grado 9", "Colegio · 9° · onboarding hecho",
           _colegio("high_school_early", 9, 11, 2012), 2012, 9),
    Cuenta("grado10", "Prueba Grado 10", "Colegio · 10° · onboarding hecho",
           _colegio("high_school_early", 10, 11, 2011), 2011, 10),
    Cuenta("grado11", "Prueba Grado 11", "Colegio · 11° (el colegio llega a 12°) · onboarding hecho",
           _colegio("high_school", 11, 12, 2010), 2010, 11),
    Cuenta("grado12", "Prueba Grado 12", "Colegio · 12° · onboarding hecho",
           _colegio("high_school", 12, 12, 2009), 2009, 12),
    Cuenta("universitario", "Prueba Universitario", "Universidad · onboarding hecho",
           _onboarding("university", **_CARRERA), 2005),
    Cuenta("profesional", "Prueba Profesional", "Trabajando · onboarding hecho",
           _onboarding("working", budget="5k_15k", **_CARRERA), 1994),
    Cuenta("nuevo1", "Prueba Nueva 1", "Sin onboarding · para recorrer el registro desde cero"),
    Cuenta("nuevo2", "Prueba Nueva 2", "Sin onboarding · para recorrer el registro desde cero"),
    Cuenta("nuevo3", "Prueba Nueva 3", "Sin onboarding · para recorrer el registro desde cero"),
]


def _aplicar_estado(u: Any, c: Cuenta) -> None:
    """Deja la cuenta en su estado inicial (onboarding, grado, consentimientos)."""
    from app.db.models import OnboardingStatus

    ahora = datetime.utcnow()
    u.name = c.nombre
    u.onboarding_answers = dict(c.respuestas or {})
    u.onboarding_status = (
        OnboardingStatus.COMPLETED if c.respuestas else OnboardingStatus.NOT_STARTED
    )
    u.grade = c.grado
    if c.respuestas and c.respuestas.get("school_last_grade"):
        u.school_reported_last_grade = int(c.respuestas["school_last_grade"])
    # Se guarda como 31 de diciembre, igual que lo hace el onboarding.
    u.birthdate = date(c.anio_nacimiento, 12, 31) if c.anio_nacimiento else None
    # Tratamiento de datos sí (sin él la app no deja pasar del registro) y el
    # parental para los menores. CRM y comunicaciones NO: ver el docstring.
    u.consent_data_processing_at = ahora
    u.consent_data_processing_version = "prueba"
    u.consent_parental_at = ahora if c.grado else None


def sembrar(db: Any, *, aplicar: bool, reiniciar: bool = False) -> List[Dict[str, str]]:
    """Crea las que falten · devuelve qué pasó con cada una."""
    from app.api.v1.auth import get_password_hash
    from app.db.models import User, UserRole

    informe = []
    clave_hash = None
    for c in CUENTAS:
        u = db.query(User).filter(User.email == c.email).first()
        if u is None:
            accion = "crear"
            if aplicar:
                clave_hash = clave_hash or get_password_hash(CLAVE)
                u = User(email=c.email, hashed_password=clave_hash, role=UserRole.STUDENT)
                _aplicar_estado(u, c)
                db.add(u)
        elif reiniciar:
            accion = "reiniciar"
            if aplicar:
                _aplicar_estado(u, c)
        else:
            accion = "ya existe (no se toca)"
        informe.append({"email": c.email, "accion": accion, "descripcion": c.descripcion})
    if aplicar:
        db.commit()
    return informe


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--aplicar", action="store_true", help="escribir en la base (si no, solo muestra)")
    parser.add_argument("--reiniciar", action="store_true", help="devolver las existentes a su estado inicial")
    args = parser.parse_args()

    from app.db.database import SessionLocal

    db = SessionLocal()
    try:
        informe = sembrar(db, aplicar=args.aplicar, reiniciar=args.reiniciar)
    finally:
        db.close()

    modo = "APLICADO" if args.aplicar else "SIMULACIÓN (nada se escribió · usa --aplicar)"
    print(f"\nCuentas de prueba por grado · {modo}\n")
    for fila in informe:
        print(f"  {fila['accion']:<24} {fila['email']:<36} {fila['descripcion']}")
    print(f"\n  Contraseña de todas: {CLAVE}\n")


if __name__ == "__main__":
    main()
