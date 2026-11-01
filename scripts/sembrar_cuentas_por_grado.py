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

## Los planes (D-6)

Todas llevan su plan propio, sin vencimiento: `pago` las que no dicen otro, y
`gratis` o `vip` las variantes, para ver la plataforma como la ve cada plan.
**El `pago` va explícito** (X-5): antes se confiaba en que la migración 081 las
subiera, pero la 081 solo ve las cuentas que existían al migrar; las creadas
después quedaban gratis. Necesitan que la tabla `user_plans` exista: correr
este script DESPUÉS de desplegar Sprint 4.

## Las claves (X-5 · revisión de seguridad)

**No hay clave fija en el repo.** Antes todas compartían una clave escrita aquí, y
con el repo en la mano cualquiera entraba a una cuenta con plan real. Ahora cada
cuenta nueva recibe una clave aleatoria que se imprime UNA vez, al crearla, para
pasarla por fuera a quien prueba. `--nuevas-claves` se las cambia a las que ya
existen (hay que correrlo una vez en producción, porque las primeras se crearon
con la clave pública).

- **La VIP no se crea por defecto** (`--incluir-vip`): es la que abre más cosas y
  una VIP de prueba en producción es lo primero que no debería existir.
- **`--desactivar`** las apaga a todas cuando termine la validación con la
  clienta. Desactivar, no borrar: lo que hicieron con ellas queda para revisar.

## Uso

    ./venv/Scripts/python scripts/sembrar_cuentas_por_grado.py             # muestra qué haría
    ./venv/Scripts/python scripts/sembrar_cuentas_por_grado.py --aplicar   # las crea
    ./venv/Scripts/python scripts/sembrar_cuentas_por_grado.py --aplicar --reiniciar
        # además devuelve las existentes a su estado inicial
    ./venv/Scripts/python scripts/sembrar_cuentas_por_grado.py --aplicar --nuevas-claves
        # les cambia la clave a las que ya existen e imprime las nuevas
    ./venv/Scripts/python scripts/sembrar_cuentas_por_grado.py --aplicar --desactivar
        # las apaga a todas

⚠️ `DATABASE_URL` del `.env` local es la base de PRODUCCIÓN. `--aplicar`
escribe ahí.
"""
from __future__ import annotations

import argparse
import secrets
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Consola de Windows en cp1252 · ver el mismo arreglo en `seed_test_data.py`.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))



def _clave_nueva() -> str:
    """Clave aleatoria de prueba · se imprime una vez y no queda en ningún lado."""
    return "Prueba-" + secrets.token_urlsafe(9)

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
    # D-6 · el plan propio de la cuenta (gratis · vip). `None` = el que le toque
    # por la regla: las que existían antes de Sprint 4 quedan `pago` por la
    # migración 081 (D9).
    plan: Optional[str] = None

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
    # D-6 · Sprint 4 · para ver la plataforma como la ve cada plan. Las de arriba
    # quedan como `pago`; estas llevan su plan explícito, así la migración no las
    # sube a pago y se ven los candados y el muro de pago.
    Cuenta("grado9.gratis", "Prueba Grado 9 Gratis", "Colegio · 9° · plan GRATIS (candados y muro de pago)",
           _colegio("high_school_early", 9, 11, 2012), 2012, 9, plan="gratis"),
    Cuenta("grado11.gratis", "Prueba Grado 11 Gratis", "Colegio · 11° · plan GRATIS (candados y muro de pago)",
           _colegio("high_school", 11, 12, 2010), 2010, 11, plan="gratis"),
    Cuenta("profesional.gratis", "Prueba Profesional Gratis", "Trabajando · plan GRATIS (candados y muro de pago)",
           _onboarding("working", budget="5k_15k", **_CARRERA), 1994, plan="gratis"),
    Cuenta("grado11.vip", "Prueba Grado 11 VIP", "Colegio · 11° · plan VIP (sesión 1:1 abierta)",
           _colegio("high_school", 11, 12, 2010), 2010, 11, plan="vip"),
]

METODO_PLAN_PRUEBA = "cuenta de prueba (K-1/D-6)"


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


def _asegurar_plan(db: Any, u: Any, c: Cuenta) -> None:
    """Le deja su plan de prueba sin vencimiento · una sola fila, no duplica."""
    from app.db.models import UserPlan

    plan = c.plan or "pago"
    ya = (
        db.query(UserPlan)
        .filter(UserPlan.user_id == u.id, UserPlan.metodo == METODO_PLAN_PRUEBA, UserPlan.plan == plan)
        .first()
    )
    if ya is None:
        ahora = datetime.utcnow()
        db.add(UserPlan(user_id=u.id, plan=plan, desde=ahora, metodo=METODO_PLAN_PRUEBA, creado_en=ahora))


def sembrar(
    db: Any,
    *,
    aplicar: bool,
    reiniciar: bool = False,
    incluir_vip: bool = False,
    nuevas_claves: bool = False,
    desactivar: bool = False,
) -> List[Dict[str, str]]:
    """Crea las que falten · devuelve qué pasó con cada una (y la clave, si la hay)."""
    from app.api.v1.auth import get_password_hash
    from app.db.models import User, UserRole

    informe = []
    for c in CUENTAS:
        if c.plan == "vip" and not incluir_vip:
            continue
        u = db.query(User).filter(User.email == c.email).first()
        clave = None
        if desactivar:
            accion = "desactivar" if u is not None else "no existe"
            if aplicar and u is not None:
                u.is_active = False
        elif u is None:
            accion = "crear"
            if aplicar:
                clave = _clave_nueva()
                u = User(email=c.email, hashed_password=get_password_hash(clave), role=UserRole.STUDENT)
                _aplicar_estado(u, c)
                db.add(u)
                db.flush()  # para tener `u.id` y colgarle el plan
                _asegurar_plan(db, u, c)
        else:
            accion = "ya existe (no se toca)"
            if reiniciar:
                accion = "reiniciar"
                if aplicar:
                    _aplicar_estado(u, c)
                    _asegurar_plan(db, u, c)
            if nuevas_claves:
                accion = f"{accion} · clave nueva" if reiniciar else "clave nueva"
                if aplicar:
                    clave = _clave_nueva()
                    u.hashed_password = get_password_hash(clave)
        fila = {"email": c.email, "accion": accion, "descripcion": c.descripcion}
        if clave:
            fila["clave"] = clave
        informe.append(fila)
    if aplicar:
        db.commit()
    return informe


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--aplicar", action="store_true", help="escribir en la base (si no, solo muestra)")
    parser.add_argument("--reiniciar", action="store_true", help="devolver las existentes a su estado inicial")
    parser.add_argument("--incluir-vip", action="store_true", help="crear también la cuenta VIP")
    parser.add_argument("--nuevas-claves", action="store_true", help="cambiar la clave de las que ya existen")
    parser.add_argument("--desactivar", action="store_true", help="apagar todas las cuentas de prueba")
    args = parser.parse_args()

    from app.db.database import SessionLocal

    db = SessionLocal()
    try:
        informe = sembrar(
            db,
            aplicar=args.aplicar,
            reiniciar=args.reiniciar,
            incluir_vip=args.incluir_vip,
            nuevas_claves=args.nuevas_claves,
            desactivar=args.desactivar,
        )
    finally:
        db.close()

    modo = "APLICADO" if args.aplicar else "SIMULACIÓN (nada se escribió · usa --aplicar)"
    print(f"\nCuentas de prueba por grado · {modo}\n")
    for fila in informe:
        print(f"  {fila['accion']:<28} {fila['email']:<40} {fila['descripcion']}")
        if fila.get("clave"):
            print(f"  {'':<28} clave: {fila['clave']}")
    if any(f.get("clave") for f in informe):
        print("\n  ⚠️ Las claves se muestran solo esta vez. Pásalas por fuera; no las guardes en el repo.\n")


if __name__ == "__main__":
    main()
