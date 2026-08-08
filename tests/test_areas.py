"""El vocabulario de áreas · la pieza de la que cuelga la recomendación.

El catálogo extraído trae `area` en texto libre: **280 valores** para 15.483
programas. `app/services/areas.py` los lleva a 21 áreas y las cruza con los
códigos RIASEC del test vocacional.

Antes de esto, el cruce con RIASEC se hacía contra el **tipo** de programa
(`carrera_completa`, `curso_idiomas`…), no contra el campo de estudio — o sea que
un curso de idiomas se consideraba "Social" por durar poco, no por su contenido.
"""
from __future__ import annotations

import pytest

from app.services import areas


# ---------------------------------------------------------------------------
# El mapa desde el texto libre
# ---------------------------------------------------------------------------


def test_todas_las_areas_del_catalogo_real_estan_mapeadas():
    """El más importante: si un valor del catálogo no mapea, esos programas
    desaparecen del filtro y nadie se entera. Se comprueba contra el archivo
    real, no contra una lista inventada aquí."""
    import csv
    import os

    ruta = os.path.join(os.path.dirname(__file__), "..", "data", "catalogo",
                        "programas_con_pais.csv")
    if not os.path.exists(ruta):
        pytest.skip("el catálogo consolidado no está en este checkout")

    with open(ruta, encoding="utf-8") as fh:
        crudas = {f["area"] for f in csv.DictReader(fh)}

    sin_mapear = sorted(a for a in crudas if areas.normalizar(a) is None)
    assert not sin_mapear, f"{len(sin_mapear)} áreas sin mapear: {sin_mapear[:10]}"


def test_las_tildes_no_parten_un_area_en_dos():
    """El catálogo escribe la misma área con y sin tilde según el lote."""
    assert areas.normalizar("Tecnología") == areas.normalizar("Tecnologia")
    assert areas.normalizar("Educación") == areas.normalizar("Educacion")
    assert areas.normalizar("Psicología") == areas.normalizar("Psicologia")


def test_el_punto_medio_de_los_idiomas_no_rompe_el_mapeo():
    """El catálogo escribe "Idiomas · Inglés" con punto medio (U+00B7), que al
    pasar a ASCII desaparece. Con un guion guardado en la clave, las dos formas
    dejaban de coincidir y 116 filas de idiomas se quedaban fuera."""
    for crudo in ("Idiomas · Inglés", "Idiomas - Ingles", "Idiomas – Inglés"):
        assert areas.normalizar(crudo) == areas.IDIOMAS, crudo


def test_ciencias_sociales_no_cae_en_ciencias():
    """Una regla por palabra clave ("si dice ciencias → Ciencias") se traga tres
    áreas distintas. Este test es el que se da cuenta si alguien la introduce."""
    assert areas.normalizar("Ciencias") == areas.CIENCIAS
    assert areas.normalizar("Ciencias Sociales") == areas.SOCIALES
    assert areas.normalizar("Ciencias del Deporte") == areas.DEPORTE
    assert areas.normalizar("Ciencias de la Salud") == areas.SALUD
    assert areas.normalizar("Ciencias Ambientales") == areas.AMBIENTE


def test_diseno_de_videojuegos_es_tecnologia_y_no_diseno():
    """Mismo motivo que el anterior, por el otro lado."""
    assert areas.normalizar("Diseño de Videojuegos") == areas.TECNOLOGIA
    assert areas.normalizar("Diseño de Interiores") == areas.DISENO


def test_lo_desconocido_devuelve_None_y_no_un_cajon_de_sastre():
    """Un área que caiga en "Otros" desaparece del filtro sin que nadie note que
    faltaba. Devolver None obliga a quien llama a contarlo."""
    assert areas.normalizar("Vuelo espacial tripulado") is None
    assert areas.normalizar("") is None
    assert areas.normalizar(None) is None


def test_toda_area_normalizada_pertenece_al_vocabulario():
    for crudo in ("Negocios", "Enfermería", "Idiomas · Chino", "Oficios"):
        assert areas.normalizar(crudo) in areas.AREAS


# ---------------------------------------------------------------------------
# El cruce con RIASEC
# ---------------------------------------------------------------------------


def test_todas_las_areas_riasec_existen_en_el_vocabulario():
    """Si el mapa RIASEC nombra un área que no existe, ese código deja de
    recomendar en silencio — que es el bug exacto que tenía el mapeo anterior
    contra categorías inexistentes."""
    for codigo, lista in areas.RIASEC_AREAS.items():
        for a in lista:
            assert a in areas.AREAS, f"{codigo} apunta a un área inexistente: {a}"


def test_los_seis_codigos_holland_estan_cubiertos():
    assert set(areas.RIASEC_AREAS) == set("RIASEC")


def test_un_perfil_artistico_ve_artes_primero():
    """El desempate no puede caer en el orden del vocabulario: para un perfil
    puramente Artístico salía Comunicación antes que Artes."""
    assert areas.areas_para_riasec(["A"])[0] == areas.ARTES


def test_el_area_que_respaldan_los_dos_codigos_gana():
    """Un código Holland de dos letras significa que interesa el cruce. Con una
    caída brusca de peso, a un perfil I-S le salía Educación —que es sólo
    Social— antes que Salud y Medicina, arquetipo de esa combinación."""
    ranking = areas.areas_para_riasec(["I", "S"])
    assert ranking[0] == areas.SALUD
    assert ranking.index(areas.SALUD) < ranking.index(areas.EDUCACION)
    assert ranking.index(areas.SALUD) < ranking.index(areas.CIENCIAS)


def test_la_afinidad_premia_la_centralidad():
    """Dentro de un mismo código, lo que está a la cabeza de la lista vale más."""
    assert areas.afinidad(areas.ARTES, ["A"]) > areas.afinidad(areas.IDIOMAS, ["A"])


def test_un_area_ajena_al_perfil_no_puntua():
    assert areas.afinidad(areas.BELLEZA, ["I"]) == 0.0
    assert areas.BELLEZA not in areas.areas_para_riasec(["I"])


def test_sin_codigos_no_hay_ranking():
    """Quien no ha hecho el test no recibe un orden inventado."""
    assert areas.areas_para_riasec([]) == []
    assert areas.areas_para_riasec(None) == []


def test_los_codigos_llegan_como_vengan():
    """`holland_codes` viene de varios sitios y no siempre normalizado."""
    assert areas.areas_para_riasec(["a"]) == areas.areas_para_riasec(["A"])
    assert areas.areas_para_riasec([" I "]) == areas.areas_para_riasec(["I"])
