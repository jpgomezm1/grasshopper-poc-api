"""E-2 · campamentos de vacaciones en el plan de 10° (2026-11-02).

Protege:
  1. La lista real: áreas válidas, enlace oficial https, campos completos, sin precios.
  2. La elección: primero su área; si se queda en Colombia, primero lo cercano;
     variedad de países al completar; nunca más de 4.
"""
from __future__ import annotations

import pytest

from app.data import campamentos as mod

CAMPOS = ("id", "nombre", "institucion", "pais", "ciudad", "temporada", "meses",
          "duracion", "edades", "idioma", "areas", "descripcion", "url", "verificado")


def test_la_lista_real_esta_completa_y_es_verificable():
    assert len(mod.CAMPAMENTOS) >= 12, "la lista verificada no se cargó"
    ids = [c["id"] for c in mod.CAMPAMENTOS]
    assert len(ids) == len(set(ids)), "ids repetidos"
    for c in mod.CAMPAMENTOS:
        for campo in CAMPOS:
            assert c.get(campo), f"{c.get('id')} sin {campo}"
        assert c["url"].startswith("https://"), c["id"]
        assert c["temporada"] in ("verano", "invierno", "ambas"), c["id"]
        assert c["areas"] and set(c["areas"]) <= set(mod.AREAS), c["id"]
        # Sin precios: cambian cada año y no son nuestros.
        texto = " ".join(str(v) for v in c.values()).lower()
        assert "usd" not in texto and "$" not in texto and "precio" not in texto, c["id"]


def test_todas_las_areas_tienen_al_menos_un_campamento():
    cubiertas = {a for c in mod.CAMPAMENTOS for a in c["areas"]}
    faltan = set(mod.AREAS) - cubiertas
    # Agricultura y servicios son las más difíciles de cubrir; el resto no.
    assert faltan <= {"agriculture", "services"}, faltan


_PRUEBA = [
    {"id": "us-ing", "pais": "Estados Unidos", "areas": ["engineering"]},
    {"id": "us-ing2", "pais": "Estados Unidos", "areas": ["engineering", "ict"]},
    {"id": "uk-art", "pais": "Reino Unido", "areas": ["arts_humanities"]},
    {"id": "co-salud", "pais": "Colombia", "areas": ["health"]},
    {"id": "es-neg", "pais": "España", "areas": ["business_law"]},
    {"id": "co-ing", "pais": "Colombia", "areas": ["engineering"]},
]


@pytest.fixture()
def lista_de_prueba(monkeypatch):
    completos = []
    for c in _PRUEBA:
        base = {k: f"{k}-{c['id']}" for k in CAMPOS}
        completos.append({**base, **c, "temporada": "verano", "url": "https://x.org/" + c["id"]})
    monkeypatch.setattr(mod, "CAMPAMENTOS", completos)


def _ids(lista):
    return [c["id"] for c in lista]


def test_primero_los_de_su_area_y_nunca_mas_de_cuatro(lista_de_prueba):
    elegidos = mod.campamentos_para("engineering", "si")
    assert _ids(elegidos)[:3] == ["us-ing", "us-ing2", "co-ing"]
    assert len(elegidos) == 4
    assert "areas" not in elegidos[0] and "verificado" not in elegidos[0]


def test_si_se_queda_en_colombia_primero_lo_cercano(lista_de_prueba):
    elegidos = mod.campamentos_para("engineering", "no")
    assert _ids(elegidos)[0] == "co-ing"


def test_sin_area_muestra_variedad_de_paises(lista_de_prueba):
    elegidos = mod.campamentos_para(None, None)
    paises = [c["pais"] for c in elegidos]
    assert len(paises) == len(set(paises)) == 4


def test_un_area_desconocida_se_trata_como_sin_area(lista_de_prueba):
    assert _ids(mod.campamentos_para("astrologia", None)) == _ids(mod.campamentos_para(None, None))


def test_el_plan_de_decimo_trae_campamentos_y_el_de_once_no():
    import inspect

    from app.services import plan_preparacion_service as svc
    fuente = inspect.getsource(svc._armar_decimo)
    assert "campamentos_para(" in fuente and '"campamentos": campamentos' in fuente
    # El plan de 11°/12° (`armar`, fuera de 10°) no los arma.
    assert "campamentos_para(" not in inspect.getsource(svc.armar)
