"""Feedback de la clienta (2026-09-06) · la consejería sobre familias.

    "no sé cómo hacer una descripción y una consejería de las familias que
     serían más adecuadas para esta persona"

El perfil consolidado devolvía `suggested_career_paths`: 3-5 nombres sueltos.
Eso es un resultado, no una consejería. `career_families` obliga a que cada
familia venga con su porqué, su día a día, sus carreras concretas y la tensión
honesta. `ReporteIntermedioPdfLayout` ya tenía esta deuda anotada en su cabecera.
"""
import pytest
from pydantic import ValidationError

from app.schemas.consolidated_profile import CareerFamily, ConsolidatedProfile
from app.services.consolidation_service import PROMPT_VERSION, _is_cache_valid


FAMILIA_OK = {
    "name": "Gestión y negocios",
    "fit_level": "alto",
    "why_it_fits": (
        "Porque montaste la feria del club con 20 stands y tu orden de intereses "
        "pone Emprendedor de primero: esta familia vive de organizar y ejecutar."
    ),
    "what_its_like": "Coordinas equipos, analizas números y negocias con proveedores.",
    "careers": ["Administración de empresas", "Gerencia de ventas"],
    "watch_out": "Muchos programas arrancan con dos años de teoría antes de casos reales.",
}


def _perfil_minimo(**extra):
    base = {
        "summary_narrative": "n " * 130,
        "strengths": ["Liderazgo con ejecución", "Análisis frío", "Gestión de recursos"],
        "interests": ["Emprendimiento", "Finanzas", "Gestión"],
        "values": ["Autonomía"],
        "tests_used": ["istrong", "mbti"],
    }
    base.update(extra)
    return base


class TestContratoDeLaFamilia:
    def test_una_familia_completa_es_valida(self):
        f = CareerFamily.model_validate(FAMILIA_OK)
        assert f.name == "Gestión y negocios"
        assert f.fit_level == "alto"
        assert "20 stands" in f.why_it_fits

    def test_el_porque_es_obligatorio(self):
        # Una familia sin porqué es exactamente lo que había antes: una etiqueta.
        sin_porque = {k: v for k, v in FAMILIA_OK.items() if k != "why_it_fits"}
        with pytest.raises(ValidationError):
            CareerFamily.model_validate(sin_porque)

    def test_el_dia_a_dia_es_obligatorio(self):
        sin_dia = {k: v for k, v in FAMILIA_OK.items() if k != "what_its_like"}
        with pytest.raises(ValidationError):
            CareerFamily.model_validate(sin_dia)

    def test_la_tension_puede_faltar_pero_el_campo_existe(self):
        f = CareerFamily.model_validate(dict(FAMILIA_OK, watch_out=None))
        assert f.watch_out is None

    def test_el_calce_es_cualitativo_no_un_porcentaje(self):
        # Un número de calce se vería en pantalla igual que uno medido · no lo hay.
        with pytest.raises(ValidationError):
            CareerFamily.model_validate(dict(FAMILIA_OK, fit_level="85%"))
        with pytest.raises(ValidationError):
            CareerFamily.model_validate(dict(FAMILIA_OK, fit_level="medio"))


class TestPerfilConsolidado:
    def test_acepta_hasta_cinco_familias(self):
        p = ConsolidatedProfile.model_validate(
            _perfil_minimo(career_families=[FAMILIA_OK] * 5)
        )
        assert len(p.career_families) == 5

    def test_rechaza_mas_de_cinco(self):
        with pytest.raises(ValidationError):
            ConsolidatedProfile.model_validate(
                _perfil_minimo(career_families=[FAMILIA_OK] * 6)
            )

    def test_un_perfil_viejo_sin_familias_sigue_siendo_valido(self):
        # Los perfiles cacheados antes de consolidate_v2 no traen el campo · el
        # frontend cae a las etiquetas sueltas y nada debe romperse.
        p = ConsolidatedProfile.model_validate(
            _perfil_minimo(suggested_career_paths=["Gestión y negocios"])
        )
        assert p.career_families == []

    def test_holland_sin_puntaje_sigue_siendo_valido(self):
        p = ConsolidatedProfile.model_validate(
            _perfil_minimo(
                holland_codes=[{"code": "E", "label": "Emprendedor", "score": None}]
            )
        )
        assert p.holland_codes[0].score is None


class TestCacheYVersionDePrompt:
    """Sin esto, una mejora del análisis tardaba hasta 24h en verse."""

    class _Fila:
        def __init__(self, version):
            from datetime import datetime

            self.invalidated_at = None
            self.profile_hash = "abc"
            self.generated_at = datetime.utcnow()
            self.prompt_version = version

    def test_la_cache_del_prompt_viejo_se_descarta(self):
        assert _is_cache_valid(self._Fila("consolidate_v1"), "abc") is False

    def test_la_cache_del_prompt_actual_se_conserva(self):
        assert _is_cache_valid(self._Fila(PROMPT_VERSION), "abc") is True
