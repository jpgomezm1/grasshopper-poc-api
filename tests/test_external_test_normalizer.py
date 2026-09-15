"""Feedback del cliente (2026-09-06) · "no sube bien los datos de los reportes".

La extracción sí funcionaba. Lo que fallaba era el puente entre el vocabulario del
parser y el del resto de la plataforma: un test subido se guardaba tal cual salía
del PDF, y por eso (a) el snapshot imprimía `type_code · NaN%` y (b)
`holland_top_codes` devolvía [] · el test se confirmaba y no contaba para nada.

Estos tests fijan ese puente.
"""
from app.schemas.external_tests import ParsedIStrong, ParsedMBTI
from app.services.external_test_normalizer import normalizar_scores
from app.services.psychometrics_service import holland_top_codes


# Lo que el parser devuelve hoy para el iStartStrong real de una estudiante.
ISTRONG_PARSEADO = {
    "holland_code": "ECR",
    "theme_ranking": ["E", "C", "R", "I", "S", "A"],
    "realistic": None,
    "investigative": None,
    "artistic": None,
    "social": None,
    "enterprising": None,
    "conventional": None,
    "top_basic_interests": ["Sales", "Finance and Investing", "Management"],
    "suggested_careers": ["Sales Manager", "Financial Advisor"],
}

MBTI_PARSEADO = {
    "type_code": "ISTP",
    "identity": None,
    "e_score": None,
    "s_score": None,
    "t_score": None,
    "j_score": None,
    "pci_ei": 10.0,
    "pci_sn": 12.0,
    "pci_tf": 5.0,
    "pci_jp": 13.0,
    "strengths": ["Se mantiene en calma en una crisis"],
    "suggested_careers": ["Mecánico de aeronaves"],
}


class TestCodigoHollandDeTresLetras:
    """El iStartStrong destaca 2 temas top · la 3ª letra está en el ranking."""

    def test_completa_el_codigo_de_dos_letras_con_el_ranking(self):
        p = ParsedIStrong.model_validate(
            {"holland_code": "EC", "theme_ranking": ["E", "C", "R", "I", "S", "A"]}
        )
        assert p.holland_code == "ECR"

    def test_respeta_un_codigo_que_ya_venia_completo(self):
        p = ParsedIStrong.model_validate({"holland_code": "IER"})
        assert p.holland_code == "IER"

    def test_traduce_nombres_de_tema_en_vez_de_leerlos_letra_a_letra(self):
        # "Enterprising" leído carácter a carácter da "ERI", otro código válido.
        p = ParsedIStrong.model_validate(
            {"holland_code": "Enterprising", "theme_ranking": "ECRISA"}
        )
        assert p.holland_code == "ECR"

    def test_acepta_nombres_en_espanol_con_tilde(self):
        p = ParsedIStrong.model_validate(
            {
                "holland_code": "Emprendedor",
                "theme_ranking": [
                    "Emprendedor", "Convencional", "Realista",
                    "Investigador", "Social", "Artístico",
                ],
            }
        )
        assert p.holland_code == "ECR"
        assert p.theme_ranking == ["E", "C", "R", "I", "S", "A"]


class TestNormalizacionAFormaCanonica:
    def test_istrong_sin_puntajes_no_inventa_numeros(self):
        scores = normalizar_scores("istrong", ISTRONG_PARSEADO)
        numericos = [v for k, v in scores.items() if isinstance(v, (int, float))]
        assert numericos == []
        assert scores["_meta"]["has_numeric_scores"] is False

    def test_istrong_conserva_codigo_ranking_y_lo_cualitativo(self):
        scores = normalizar_scores("istrong", ISTRONG_PARSEADO)
        assert scores["holland_code"] == "ECR"
        assert scores["_meta"]["theme_ranking"] == ["E", "C", "R", "I", "S", "A"]
        assert "Sales" in scores["_meta"]["top_basic_interests"]
        assert "Sales Manager" in scores["_meta"]["suggested_careers"]

    def test_istrong_con_puntajes_usa_las_claves_cortas_del_frontend(self):
        payload = dict(ISTRONG_PARSEADO, enterprising=88.0, conventional=74.0)
        scores = normalizar_scores("istrong", payload)
        assert scores["E"] == 88.0
        assert scores["C"] == 74.0
        assert scores["_meta"]["has_numeric_scores"] is True

    def test_mbti_guarda_el_pci_aparte_y_no_como_porcentaje(self):
        scores = normalizar_scores("mbti", MBTI_PARSEADO)
        assert scores["type_code"] == "ISTP"
        # El pci es escala 0-30 · no puede terminar en la raíz como si fuera %.
        assert "EI" not in scores
        assert scores["_meta"]["pci"] == {"EI": 10.0, "SN": 12.0, "TF": 5.0, "JP": 13.0}

    def test_mbti_con_porcentajes_reales_si_sube_a_la_raiz(self):
        payload = dict(MBTI_PARSEADO, e_score=72.0, j_score=64.0)
        scores = normalizar_scores("mbti", payload)
        assert scores["EI"] == 72.0
        assert scores["JP"] == 64.0

    def test_lo_no_reconocido_se_guarda_en_vez_de_perderse(self):
        scores = normalizar_scores("istrong", dict(ISTRONG_PARSEADO, campo_raro="x"))
        assert scores["_meta"]["extras"] == {"campo_raro": "x"}

    def test_es_idempotente_porque_el_usuario_puede_reconfirmar(self):
        una = normalizar_scores("istrong", ISTRONG_PARSEADO)
        assert normalizar_scores("istrong", una) == una

    def test_ningun_valor_de_la_raiz_es_una_lista(self):
        # La raíz es lo que el frontend grafica · una lista ahí daba "NaN%".
        for tipo, payload in (("istrong", ISTRONG_PARSEADO), ("mbti", MBTI_PARSEADO)):
            scores = normalizar_scores(tipo, payload)
            for clave, valor in scores.items():
                if clave == "_meta":
                    continue
                assert isinstance(valor, (int, float, str)), (tipo, clave)


class TestElTestSubidoSiAlimentaElPerfil:
    """Antes devolvía [] · el test se confirmaba y no contaba para nada."""

    def test_lee_las_letras_desde_el_ranking(self):
        scores = normalizar_scores("istrong", ISTRONG_PARSEADO)
        assert holland_top_codes(scores, n=3) == ["E", "C", "R"]

    def test_lee_las_letras_desde_el_codigo_si_no_hay_ranking(self):
        scores = normalizar_scores("istrong", {"holland_code": "SAE"})
        assert holland_top_codes(scores, n=2) == ["S", "A"]

    def test_los_puntajes_numericos_siguen_teniendo_prioridad(self):
        assert holland_top_codes({"R": 80, "E": 90, "C": 70}, n=2) == ["E", "R"]

    def test_sin_datos_sigue_devolviendo_vacio(self):
        assert holland_top_codes({}, n=2) == []
