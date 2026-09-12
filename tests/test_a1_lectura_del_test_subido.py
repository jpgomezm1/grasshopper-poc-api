"""A1 · versión subida · el modelo dejó de escribir a ciegas los tests en PDF.

El doc "SPRINT 3: HOPPER" pedía que cada test le diera más información al
estudiante y su familia. Se resolvió para los tests hechos aquí, y la auditoría
del 29-07 corrigió los 4 internos donde "la IA escribía sin ver el resultado".

Reapareció por la puerta de las subidas: `format_scores_block` filtraba a valores
numéricos y salía temprano, y los reportes oficiales (iStartStrong, MBTI Career
Report) no publican ninguno. Al modelo le llegaba, literal, "(sin puntajes
numéricos)" · ni el código Holland, ni el tipo, ni el orden de preferencia.
"""
from app.services.test_interpretation_service import format_scores_block

ISTRONG_SUBIDO = {
    "holland_code": "ECR",
    "_meta": {
        "source": "external_upload",
        "test_type": "istrong",
        "has_numeric_scores": False,
        "theme_ranking": ["E", "C", "R", "I", "S", "A"],
        "top_basic_interests": ["Ventas", "Finanzas e inversiones"],
        "suggested_careers": ["Gerente de ventas"],
    },
}

MBTI_SUBIDO = {
    "type_code": "ISTP",
    "_meta": {
        "source": "external_upload",
        "test_type": "mbti",
        "has_numeric_scores": False,
        "pci": {"EI": 10, "SN": 12, "TF": 5, "JP": 13},
        "strengths": ["Se mantiene en calma en una crisis"],
        "suggested_careers": ["Mecánico de aeronaves"],
    },
}

# Lo que quedó guardado en producción antes del normalizador: payload plano.
ISTRONG_LEGADO = {
    "holland_code": "EC",
    "realistic": None,
    "top_basic_interests": ["Ventas", "Gestión"],
    "suggested_careers": ["Gerente de ventas"],
}


class TestElModeloYaVeElResultado:
    def test_istrong_subido_deja_de_ser_una_pantalla_en_blanco(self):
        bloque = format_scores_block("istrong", ISTRONG_SUBIDO)
        assert bloque != "(sin puntajes numéricos)"
        assert "Emprendedor" in bloque
        assert "Convencional" in bloque

    def test_el_orden_de_preferencia_completo_llega_al_prompt(self):
        bloque = format_scores_block("istrong", ISTRONG_SUBIDO)
        assert "1º Emprendedor" in bloque
        assert "6º Artístico" in bloque

    def test_se_le_advierte_al_modelo_que_no_invente_porcentajes(self):
        bloque = format_scores_block("istrong", ISTRONG_SUBIDO)
        assert "No inventes porcentajes" in bloque

    def test_los_intereses_y_carreras_del_reporte_llegan(self):
        bloque = format_scores_block("istrong", ISTRONG_SUBIDO)
        assert "Ventas" in bloque
        assert "Gerente de ventas" in bloque

    def test_mbti_subido_trae_el_tipo_y_la_claridad_no_un_porcentaje(self):
        bloque = format_scores_block("mbti", MBTI_SUBIDO)
        assert "TIPO: ISTP" in bloque
        # El pci es 0-30 · presentarlo como "10%" sería otra escala.
        assert "claridad 10 de 30" in bloque
        assert "10%" not in bloque

    def test_mbti_apunta_al_polo_correcto_del_tipo(self):
        bloque = format_scores_block("mbti", MBTI_SUBIDO)
        # ISTP → I, S, T, P · no E, N, F, J.
        assert "se inclina a «I»" in bloque
        assert "se inclina a «P»" in bloque

    def test_una_subida_vieja_sin_meta_tampoco_sale_a_ciegas(self):
        bloque = format_scores_block("istrong", ISTRONG_LEGADO)
        assert bloque != "(sin puntajes numéricos)"
        assert "Emprendedor" in bloque
        assert "Gerente de ventas" in bloque


class TestSinRegresionEnLosTestsInternos:
    def test_un_test_interno_numerico_sigue_igual(self):
        bloque = format_scores_block(
            "holland", {"E": 90, "C": 82, "I": 78, "R": 32, "A": 20, "S": 15}
        )
        assert bloque.startswith("- Emprendedor: 90")
        assert "Convencional: 82" in bloque

    def test_el_resultado_interpretado_interno_sigue_llegando(self):
        bloque = format_scores_block(
            "istrong",
            {
                "E": 88,
                "C": 74,
                "_extras": {"primary_got": "E", "secondary_got": "C", "top_bis": []},
            },
        )
        assert "ÁREAS DOMINANTES" in bloque
        assert "Emprendedor: 88" in bloque

    def test_un_test_de_verdad_vacio_sigue_diciendo_que_no_hay_nada(self):
        assert format_scores_block("holland", {}) == "(sin puntajes numéricos)"

    def test_las_claves_internas_no_se_grafican_como_dimensiones(self):
        # `_meta` y `_extras` no son dimensiones · no deben salir como puntajes.
        bloque = format_scores_block("istrong", ISTRONG_SUBIDO)
        assert "_meta" not in bloque
