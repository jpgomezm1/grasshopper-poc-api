"""El mapeo RIASEC → áreas · lo que se corrigió el 2026-09-19 y no debe deshacerse.

Hallazgo: 80 de los 91 programas de veterinaria del catálogo quedaron en el área
"Agricultura y Veterinaria", que estaba **sólo** en la lista del código
Realista. Para una estudiante S-I-A —el arquetipo de quien quiere ser
veterinaria— esa área puntuaba 0.00 mientras "Salud y Medicina" puntuaba 1.70.
El refuerzo castigaba justo lo que esa persona debía ver.

Medido sobre el catálogo real (33.552 programas), en la lista de áreas que se le
ofrecen a esa estudiante:

    Agricultura y Veterinaria ... #20 → #9   (267 programas que estaban enterrados)

Ojo con lo que este cambio **no** hizo: el top-30 de su búsqueda por perfil no se
movió ni una posición, porque esos programas están etiquetados "Salud y
Medicina". La corrección se ve en la oferta de áreas, no en el ranking de
programas — y decirlo importa tanto como el arreglo.
"""
from __future__ import annotations

import pytest

from app.services.areas import (
    AGRO,
    AREAS,
    BELLEZA,
    PREPARACION,
    RIASEC_AREAS,
    SALUD,
    afinidad,
)


# ---------------------------------------------------------------------------
# Lo que se corrigió
# ---------------------------------------------------------------------------


def test_veterinaria_le_habla_a_un_perfil_social_investigativo():
    """El caso que originó el cambio · antes daba exactamente 0.00."""
    assert afinidad(AGRO, ["S", "I", "A"]) > 0


def test_veterinaria_sigue_siendo_sobre_todo_realista():
    """Se agregó a I y S, no se movió de R · un perfil manual y de campo sigue
    siendo el que más la reconoce, que es lo correcto."""
    assert afinidad(AGRO, ["R"]) > afinidad(AGRO, ["S"])
    assert afinidad(AGRO, ["R"]) > afinidad(AGRO, ["I"])


def test_la_medicina_humana_sigue_pesando_mas_que_la_animal_para_un_perfil_social():
    """No se trata de igualarlas. Cuidar personas sigue siendo más central al
    código Social que cuidar animales; lo que no puede ser es que una valga 0."""
    assert afinidad(SALUD, ["S", "I"]) > afinidad(AGRO, ["S", "I"]) > 0


def test_belleza_ya_no_es_invisible():
    """No estaba en NINGUNA lista, así que puntuaba 0 para todo el mundo. Es
    trabajo manual con criterio estético: R y A."""
    assert afinidad(BELLEZA, ["A"]) > 0
    assert afinidad(BELLEZA, ["R"]) > 0


# ---------------------------------------------------------------------------
# Lo que se deja fuera a propósito · un test, no un olvido
# ---------------------------------------------------------------------------


def test_preparacion_academica_no_tiene_codigo_y_es_deliberado():
    """No es un campo del saber, es un PASO hacia uno (pathway, foundation,
    pre-master). Reforzarla la pondría a competir con la carrera a la que la
    persona quiere llegar, que es lo contrario de lo que sirve.

    Si alguien la agrega algún día, que sea a sabiendas y borrando este test.
    """
    assert all(PREPARACION not in areas for areas in RIASEC_AREAS.values())
    for codigos in (["R"], ["I"], ["A"], ["S"], ["E"], ["C"]):
        assert afinidad(PREPARACION, codigos) == 0.0


def test_toda_area_vocacional_le_habla_a_algun_codigo():
    """La red que atrapó a "Belleza y Estética".

    Un área que no está en ninguna lista puntúa 0 para todos los perfiles: sus
    programas nunca reciben refuerzo y nadie se entera, porque siguen saliendo
    en la búsqueda, sólo que peor colocados. Es el mismo fallo silencioso que el
    `embedding IS NOT NULL` y que la veterinaria.
    """
    huerfanas = [
        a for a in AREAS
        if a != PREPARACION and not any(a in v for v in RIASEC_AREAS.values())
    ]
    assert not huerfanas, (
        f"estas áreas puntúan 0 para cualquier perfil: {huerfanas}. "
        "O se conectan a un código, o se documentan como PREPARACION."
    )


# ---------------------------------------------------------------------------
# La propiedad que hace seguro el cambio
# ---------------------------------------------------------------------------


#: El mapeo tal como estaba antes del 2026-09-19.
_ANTES = {
    "R": ["Oficios y Técnica", "Agricultura y Veterinaria", "Ingeniería",
          "Arquitectura y Construcción", "Deporte", "Medio Ambiente y Sostenibilidad"],
    "I": ["Ciencias", "Salud y Medicina", "Tecnología e Informática", "Ingeniería",
          "Medio Ambiente y Sostenibilidad", "Psicología y Trabajo Social"],
    "A": ["Artes", "Diseño y Moda", "Comunicación y Medios",
          "Arquitectura y Construcción", "Idiomas"],
    "S": ["Educación", "Psicología y Trabajo Social", "Salud y Medicina",
          "Ciencias Sociales y Humanidades", "Deporte",
          "Hospitalidad, Turismo y Gastronomía"],
    "E": ["Negocios y Administración", "Derecho y Justicia",
          "Hospitalidad, Turismo y Gastronomía", "Comunicación y Medios"],
    "C": ["Negocios y Administración", "Derecho y Justicia",
          "Tecnología e Informática", "Oficios y Técnica"],
}


def test_solo_se_agrego_nunca_se_quito_ni_se_reordeno():
    """La propiedad que hizo innecesario re-medir el catálogo entero.

    Con altas puras, la afinidad de cualquier (área, perfil) sólo puede subir o
    quedarse igual: el cambio no puede hundir nada que hoy funcione. Un
    reordenamiento sí habría exigido volver a calibrar `PESO_AFINIDAD` y correr
    el set de evaluación completo.
    """
    for codigo, antes in _ANTES.items():
        ahora = RIASEC_AREAS[codigo]
        assert antes == [a for a in ahora if a in antes], (
            f"el código {codigo} se reordenó o perdió áreas · eso ya no es una "
            "alta pura y obliga a re-medir"
        )


@pytest.mark.parametrize("perfil", [["S", "I", "A"], ["R", "I", "C"],
                                    ["A", "S", "E"], ["E", "C", "S"], ["I"]])
def test_ninguna_afinidad_bajo_para_ningun_perfil(perfil):
    """La comprobación numérica de lo mismo, área por área."""
    def afinidad_con(mapa, area, codigos):
        total = 0.0
        for c in codigos:
            lista = mapa.get(c, [])
            if area in lista:
                total += max(0.0, 1.0 - 0.1 * lista.index(area))
        return total

    for area in AREAS:
        assert afinidad(area, perfil) >= afinidad_con(_ANTES, area, perfil) - 1e-9, area
