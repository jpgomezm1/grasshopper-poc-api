"""La trampa de la escala del GPA · `admission_fit_service`.

## Por qué existe este archivo

`classify()` comparaba el promedio del estudiante con el del programa **en
crudo**. Un 4.2 sobre 5.0 (Colombia) traducido es 84 % y está POR DEBAJO de un
3.8 sobre 4.0 (EE. UU., 95 %) — pero comparados como números sueltos, 4.2 > 3.8.
La clasificación salía **al revés**: "safety" donde debía decir "reach", en la
pantalla que más pesa de 11°.

Era inofensivo sólo porque nadie le pasaba nunca el GPA del estudiante. Dejaba
de serlo el día que se cargara el Excel de admisión de la clienta — es decir, en
el momento en que el badge empezara a servir para algo.

## Lo que fijan estos tests

 1. ⭐ **El caso que estaba mal**, con sus números reales. Si alguien vuelve a
    comparar crudo, este test dice exactamente qué se rompió.
 2. ⭐ **Sin escala no se compara.** Falta la del programa, la del estudiante o
    las dos → la señal de GPA no entra, pero las otras (SAT, tasa de admisión)
    siguen valiendo. Preferir una señal menos a una señal falsa.
 3. **Escalas iguales siguen funcionando** — el arreglo no cambia el caso que ya
    estaba bien.
 4. **Nada de esto altera el comportamiento de hoy**: sin datos de admisión en
    el catálogo, `classify()` sigue devolviendo `None`.

Sin base de datos: `classify()` sólo lee atributos, así que un objeto tonto
basta y el test no depende de que haya catálogo.
"""
from __future__ import annotations

import inspect

import pytest

from app.services import admission_fit_service as fit


class ProgramaFalso:
    """Lo mínimo que `classify()` mira · nada de ORM."""

    def __init__(self, **kwargs):
        self.acceptance_rate = kwargs.get("acceptance_rate")
        self.avg_admitted_gpa = kwargs.get("avg_admitted_gpa")
        self.avg_admitted_gpa_scale = kwargs.get("avg_admitted_gpa_scale")
        self.min_sat = kwargs.get("min_sat")
        self.avg_sat = kwargs.get("avg_sat")


# ---------------------------------------------------------------------------
# 1 · el caso que estaba mal
# ---------------------------------------------------------------------------

def test_un_promedio_colombiano_no_gana_a_uno_gringo_por_ser_mas_grande():
    """⭐ 4.2/5.0 (84 %) contra 3.8/4.0 (95 %) es REACH, no safety.

    Comparados crudos, 4.2 > 3.8 + 0.3 y salía "safety": le habríamos dicho a
    un estudiante que una universidad le queda holgada cuando está once puntos
    porcentuales por debajo del promedio de admitidos.
    """
    programa = ProgramaFalso(avg_admitted_gpa=3.8, avg_admitted_gpa_scale=4.0)

    veredicto = fit.classify(programa, student_gpa=4.2, student_gpa_scale=5.0)

    assert veredicto == "reach"


def test_el_caso_inverso_tambien_se_traduce():
    """Un 4.8/5.0 (96 %) contra un 3.0/4.0 (75 %) sí es holgado."""
    programa = ProgramaFalso(
        avg_admitted_gpa=3.0, avg_admitted_gpa_scale=4.0, acceptance_rate=70.0
    )

    veredicto = fit.classify(programa, student_gpa=4.8, student_gpa_scale=5.0)

    assert veredicto == "safety"


# ---------------------------------------------------------------------------
# 2 · sin escala no se compara
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "escala_programa, escala_estudiante",
    [
        (None, 5.0),   # el catálogo viejo · 2.562 filas así
        (4.0, None),   # un estudiante que no declaró sobre cuánto
        (None, None),
    ],
)
def test_sin_alguna_escala_la_senal_de_gpa_no_entra(escala_programa, escala_estudiante):
    """⭐ Falta una escala → esa señal se omite, no se adivina.

    El programa es muy selectivo (8 % de admisión), así que la respuesta debe
    salir de ahí y no de una comparación de promedios que no se puede hacer.
    """
    programa = ProgramaFalso(
        avg_admitted_gpa=3.8,
        avg_admitted_gpa_scale=escala_programa,
        acceptance_rate=8.0,
    )

    veredicto = fit.classify(
        programa, student_gpa=4.9, student_gpa_scale=escala_estudiante
    )

    # Con el GPA crudo, un 4.9 contra un 3.8 habría empujado a "safety".
    assert veredicto == "reach"


def test_sin_escalas_y_sin_otras_senales_no_clasifica():
    """Si lo único que hay es un GPA que no se puede traducir, no hay badge."""
    programa = ProgramaFalso(avg_admitted_gpa=3.8, avg_admitted_gpa_scale=None)

    assert fit.classify(programa, student_gpa=4.2, student_gpa_scale=5.0) is None


def test_una_escala_absurda_no_revienta_ni_clasifica():
    """Escala 0 o negativa · dato corrupto, no excepción."""
    programa = ProgramaFalso(avg_admitted_gpa=3.8, avg_admitted_gpa_scale=0)

    assert fit.classify(programa, student_gpa=4.2, student_gpa_scale=5.0) is None


def test_un_promedio_fuera_de_su_escala_se_ignora():
    """Un 9.9 sobre 5.0 no puede ser · se descarta esa señal en vez de creerla."""
    programa = ProgramaFalso(
        avg_admitted_gpa=3.8, avg_admitted_gpa_scale=4.0, acceptance_rate=8.0
    )

    assert fit.classify(programa, student_gpa=9.9, student_gpa_scale=5.0) == "reach"


# ---------------------------------------------------------------------------
# 3 · el caso que ya estaba bien sigue estándolo
# ---------------------------------------------------------------------------

def test_dos_promedios_en_la_misma_escala_se_comparan_como_siempre():
    programa = ProgramaFalso(avg_admitted_gpa=3.8, avg_admitted_gpa_scale=4.0)

    assert fit.classify(programa, student_gpa=3.2, student_gpa_scale=4.0) == "reach"


def test_un_promedio_parecido_cae_en_match():
    """Dentro del margen · ni por encima ni por debajo con holgura."""
    programa = ProgramaFalso(avg_admitted_gpa=3.8, avg_admitted_gpa_scale=4.0)

    assert fit.classify(programa, student_gpa=3.8, student_gpa_scale=4.0) == "match"


# ---------------------------------------------------------------------------
# 4 · el comportamiento de hoy no se movió
# ---------------------------------------------------------------------------

def test_el_catalogo_de_hoy_sigue_sin_badge():
    """Los 2.562 programas reales están vacíos · nada debe aparecer."""
    vacio = ProgramaFalso()

    assert fit.classify(vacio) is None
    assert fit.classify(vacio, student_gpa=4.2, student_gpa_scale=5.0) is None


def test_sin_gpa_del_estudiante_manda_la_tasa_de_admision():
    """El único llamador de hoy (`ofertas.py`) llama sin métricas."""
    selectivo = ProgramaFalso(acceptance_rate=8.0)
    accesible = ProgramaFalso(acceptance_rate=75.0)

    assert fit.classify(selectivo) == "reach"
    assert fit.classify(accesible) == "safety"


def test_acceptance_rate_en_escala_0_1_se_sigue_normalizando():
    """La defensa que ya existía no se tocó."""
    assert fit.classify(ProgramaFalso(acceptance_rate=0.08)) == "reach"


# ---------------------------------------------------------------------------
# 5 · quién puede guardar un promedio sin escala, y quién no
# ---------------------------------------------------------------------------
#
# La distinción es sutil y por eso está fijada aquí:
#
#   * `ProgramCreate` — al crear NO hay fila previa, así que un promedio sin
#     escala nace ya inservible → se rechaza.
#   * `ProgramUpdate` — es un PATCH parcial. Tocar sólo el promedio sobre una
#     fila que YA tiene su escala es legítimo, y exigir reenviarla sería pedir
#     que se repita un dato que no cambió.
#
# La defensa que de verdad protege al estudiante no es ninguna de las dos: es
# que `classify()` no compare sin las dos escalas. Esto es el cinturón.

def test_crear_un_programa_con_promedio_pero_sin_escala_se_rechaza():
    import pydantic

    from app.schemas.program import ProgramCreate

    with pytest.raises(pydantic.ValidationError):
        ProgramCreate(
            program_id="P1", name="Uno", slug="uno", country="UK",
            institution="X", type="pregrado", duration_months=48,
            cost_total=1000, currency="USD", budget_tier="medio",
            alliance_type="directa", avg_admitted_gpa=3.8,
        )


def test_actualizar_solo_el_promedio_si_se_permite():
    """La fila puede tener ya su escala · no se le pide repetirla."""
    from app.schemas.program import ProgramUpdate

    m = ProgramUpdate(avg_admitted_gpa=3.7)

    assert m.avg_admitted_gpa == 3.7
    assert m.avg_admitted_gpa_scale is None


def test_una_escala_que_no_manejamos_se_rechaza_siempre():
    """6.0 no está en la lista · y la lista se lee de la ficha del estudiante,
    para que no haya dos que se desincronicen."""
    import pydantic

    from app.schemas.program import ProgramUpdate

    with pytest.raises(pydantic.ValidationError):
        ProgramUpdate(avg_admitted_gpa=3.8, avg_admitted_gpa_scale=6.0)


def test_un_promedio_que_no_cabe_en_su_escala_se_rechaza():
    import pydantic

    from app.schemas.program import ProgramUpdate

    with pytest.raises(pydantic.ValidationError):
        ProgramUpdate(avg_admitted_gpa=4.5, avg_admitted_gpa_scale=4.0)


def test_la_lista_de_escalas_es_la_MISMA_que_la_del_estudiante():
    """Si alguien añade una escala en un sitio y no en el otro, un programa y
    un estudiante podrían declarar sistemas distintos y no comparar nunca."""
    from app.schemas import program as schema_programa
    from app.services.academic_profile_service import ESCALAS_VALIDAS

    fuente = inspect.getsource(schema_programa)
    assert "from app.services.academic_profile_service import ESCALAS_VALIDAS" in fuente
    assert 5.0 in ESCALAS_VALIDAS and 4.0 in ESCALAS_VALIDAS
