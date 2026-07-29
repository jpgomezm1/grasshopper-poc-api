"""P1-7 / A6 · El autoanálisis del estudiante después de cada test · Sprint 3.

Es el único punto que la clienta escribió EN MAYÚSCULAS:

    "ESTO NO ESTÁ FUNCIONANDO: una vez realizo un test de orientación, no me
     pregunta: según el conocimiento que adquieres de ti mismo con el último test
     realizado, ¿qué carreras profesionales piensas que se acomodan a tus valores,
     habilidades e intereses? Escribe 3 opciones, siendo 1 la que más se acomoda.
     Porque con ese autoanálisis el sistema debería ofrecerle opciones según su
     top-3 y/o según lo que la IA considera del test."

La segunda mitad de esa frase es la que importa y la que es fácil de incumplir:
no basta con preguntar. Si el top-3 se guarda pero no llega al motor que arma las
recomendaciones, el formulario es decorativo y el reclamo sigue vivo. Estos tests
fijan justamente eso: que lo declarado ENTRE al perfil consolidado, que el ORDEN
sobreviva, y que responderlo invalide la caché.
"""
from __future__ import annotations

from app.services import consolidation_service as cs


def _test_row(test_id="holland", scores=None, self_assessment=None):
    return {
        "test_id": test_id,
        "source": "internal",
        "scores": scores or {"A": 80, "S": 60},
        "completed_at": "2026-07-29T10:00:00",
        "self_assessment": self_assessment,
    }


# ---------------------------------------------------------------------------
# Lo declarado llega al modelo
# ---------------------------------------------------------------------------


def test_el_top3_declarado_llega_al_prompt():
    """Sin esto, la persona escribe tres carreras y el sistema nunca las ve."""
    bloque = cs._format_tests_block(
        [_test_row(self_assessment=["Diseño industrial", "Arquitectura", "Publicidad"])]
    )
    assert "Diseño industrial" in bloque
    assert "Arquitectura" in bloque
    assert "Publicidad" in bloque


def test_se_conserva_el_orden_de_preferencia():
    """"Siendo 1 la que más se acomoda": si el orden se pierde, se pierde el dato."""
    bloque = cs._format_tests_block(
        [_test_row(self_assessment=["Medicina", "Enfermería", "Biología"])]
    )
    assert "1. Medicina" in bloque
    assert "2. Enfermería" in bloque
    assert "3. Biología" in bloque
    assert bloque.index("1. Medicina") < bloque.index("3. Biología")


def test_un_test_sin_autoanalisis_no_agrega_ruido():
    """Quien todavía no respondió no debe generar una línea vacía en el prompt."""
    bloque = cs._format_tests_block([_test_row(self_assessment=None)])
    assert "carreras que el estudiante cree" not in bloque
    assert "scores:" in bloque  # el resto del bloque sigue intacto


def test_lista_vacia_se_trata_como_sin_responder():
    bloque = cs._format_tests_block([_test_row(self_assessment=[])])
    assert "carreras que el estudiante cree" not in bloque


def test_cada_test_lleva_su_propio_autoanalisis():
    """Se guarda POR test porque ella dice "con el ÚLTIMO test realizado": la
    autopercepción cambia y el modelo tiene que poder ver esa evolución."""
    bloque = cs._format_tests_block(
        [
            _test_row("holland", self_assessment=["Derecho"]),
            _test_row("bigfive", self_assessment=["Psicología"]),
        ]
    )
    # Cada carrera aparece en el bloque de SU test, no mezcladas.
    pos_holland = bloque.index("### holland")
    pos_bigfive = bloque.index("### bigfive")
    assert pos_holland < bloque.index("Derecho") < pos_bigfive
    assert bloque.index("Psicología") > pos_bigfive


# ---------------------------------------------------------------------------
# El prompt le dice al modelo qué hacer con eso
# ---------------------------------------------------------------------------


def test_el_prompt_ordena_contrastar_lo_declarado_con_lo_medido():
    """Ella pidió opciones "según su top-3 Y/O según lo que la IA considera del
    test". O sea: contrastar, no elegir uno de los dos."""
    plantilla = cs.load_prompt("consolidate_profile")
    assert "autoanálisis" in plantilla.lower()
    # Y que no lo descarte cuando choque con los scores.
    assert "tensión" in plantilla.lower() or "choca" in plantilla.lower()


def test_las_carreras_sugeridas_deben_conectar_con_la_primera_opcion():
    plantilla = cs.load_prompt("consolidate_profile")
    bloque = plantilla[plantilla.index("suggested_career_paths"):]
    bloque = bloque[: bloque.index("\n- `tests_used`")]
    assert "primera opción" in bloque


# ---------------------------------------------------------------------------
# Responder invalida la caché
# ---------------------------------------------------------------------------


def test_declarar_carreras_cambia_el_hash_de_inputs():
    """Si el hash no cambia, el perfil consolidado se sigue sirviendo de caché y
    la persona ve recomendaciones que ignoran lo que acaba de escribir."""
    base = {
        "user_id": "u1",
        "demographic": {},
        "journey_answers": {},
        "onboarding": {},
        "tests": [_test_row(self_assessment=None)],
    }
    con_top3 = dict(base, tests=[_test_row(self_assessment=["Diseño industrial"])])
    assert cs.hash_inputs(base) != cs.hash_inputs(con_top3)


def test_cambiar_el_orden_del_top3_cambia_el_hash():
    """Reordenar es un cambio real de preferencia, no un no-op."""
    a = {
        "user_id": "u1", "demographic": {}, "journey_answers": {}, "onboarding": {},
        "tests": [_test_row(self_assessment=["Medicina", "Biología"])],
    }
    b = {
        "user_id": "u1", "demographic": {}, "journey_answers": {}, "onboarding": {},
        "tests": [_test_row(self_assessment=["Biología", "Medicina"])],
    }
    assert cs.hash_inputs(a) != cs.hash_inputs(b)
