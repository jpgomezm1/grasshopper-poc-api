# -*- coding: utf-8 -*-
"""El lector de logros · lo que NO puede inventarse.

AH, 2026-08-28: *"soy el capitán del equipo de fútbol... en modo conversacional
o subiendo el PDF o la imagen del diploma"*.

## Por qué estos tests y no otros

Lo que este módulo produce va a aparecerle al estudiante **ya escrito** en un
formulario. Que lo revise antes de guardar no es una red de seguridad: es lo
contrario, porque un campo prellenado se confirma sin leerlo. Y lo que se
guarde acaba en el perfil consolidado, en el Statement of Purpose y en la hoja
de vida que manda a una universidad.

Así que lo que se prueba aquí es sobre todo **qué se descarta**:

 1. Una fecha a medias ("2024") NO se convierte en 2024-01-01.
 2. Una categoría inventada cae a "other" en vez de romper el filtro de la UI.
 3. Sin nombre no hay ficha — vale más decir "no encontré nada".
 4. El archivo NO se guarda en ningún sitio.

Se mockea la FRONTERA (`document_ai`, que habla con el SDK), no el lector.
"""
from __future__ import annotations

import json

import pytest

from app.services import document_ai, logros_reader


def _responde(monkeypatch, payload, *, capturar=None):
    """Hace que el modelo devuelva exactamente `payload`."""
    texto = payload if isinstance(payload, str) else json.dumps(payload)

    def _fake_text(prompt):
        if capturar is not None:
            capturar["prompt"] = prompt
            capturar["via"] = "texto"
        return texto, {"model": "m", "tokens_input": 10, "tokens_output": 5, "latency_ms": 1}

    def _fake_vision(prompt, image_bytes, mime):
        if capturar is not None:
            capturar["prompt"] = prompt
            capturar["via"] = "vision"
            capturar["bytes"] = image_bytes
            capturar["mime"] = mime
        return texto, {"model": "m", "tokens_input": 10, "tokens_output": 5, "latency_ms": 1}

    monkeypatch.setattr(document_ai, "call_claude_text", _fake_text)
    monkeypatch.setattr(document_ai, "call_claude_vision", _fake_vision)


CAPITAN = {
    "encontrado": True,
    "categoria": "sport",
    "nombre": "Equipo de fútbol del colegio",
    "rol": "Capitán",
    "horas_semana": 6,
    "fecha_inicio": "2024-02-01",
    "fecha_fin": None,
    "descripcion": "Capitán del equipo desde décimo.",
    "logros": ["Subcampeón intercolegiado 2024"],
    "confianza": 0.9,
    "falta": ["¿hasta cuándo?"],
}


# ---------------------------------------------------------------------------
# 1 · el caso que pidió AH, literal
# ---------------------------------------------------------------------------


def test_lee_el_capitan_del_equipo_de_futbol(monkeypatch):
    _responde(monkeypatch, CAPITAN)
    f = logros_reader.leer_de_texto("soy el capitán del equipo de fútbol del colegio")

    assert f.encontrado is True
    assert f.categoria == "sport"
    assert f.nombre == "Equipo de fútbol del colegio"
    assert f.rol == "Capitán"
    assert f.logros == ["Subcampeón intercolegiado 2024"]
    assert f.falta == ["¿hasta cuándo?"]


def test_el_texto_de_la_persona_llega_al_prompt(monkeypatch):
    """Suena obvio · es el error #1 documentado de este repo (un campo que se
    escribe y nadie lee, o al revés)."""
    cap = {}
    _responde(monkeypatch, CAPITAN, capturar=cap)
    logros_reader.leer_de_texto("soy el capitán del equipo de fútbol")

    assert "capitán del equipo de fútbol" in cap["prompt"]


# ---------------------------------------------------------------------------
# 2 · lo que se descarta
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fecha", ["2024", "2024-05", "el año pasado", "", None, 2024])
def test_una_fecha_a_medias_no_se_completa(monkeypatch, fecha):
    """⭐ Un diploma que dice "2024" NO es 2024-01-01.

    Completarla daría un dato inventado con apariencia de dato exacto, que es
    justo por lo que este proyecto ya recibió un reclamo del cliente.
    """
    _responde(monkeypatch, {**CAPITAN, "fecha_inicio": fecha})
    f = logros_reader.leer_de_texto("gané algo en 2024 en el colegio")

    assert f.fecha_inicio is None


def test_una_fecha_completa_si_pasa(monkeypatch):
    """El otro lado · si no, "siempre None" pasaría el test de arriba."""
    _responde(monkeypatch, {**CAPITAN, "fecha_inicio": "2024-02-01"})
    assert logros_reader.leer_de_texto("algo del colegio").fecha_inicio == "2024-02-01"


def test_una_categoria_inventada_cae_en_other(monkeypatch):
    """La lista es abierta en la base, pero una categoría fantasma deja la
    actividad fuera de todos los filtros de la UI."""
    _responde(monkeypatch, {**CAPITAN, "categoria": "deportes_extremos"})
    assert logros_reader.leer_de_texto("hago algo raro en el colegio").categoria == "other"


def test_sin_nombre_no_hay_ficha(monkeypatch):
    """Prellenar un formulario al que le falta lo esencial es peor que decir
    que no se encontró nada."""
    _responde(monkeypatch, {**CAPITAN, "nombre": "   "})
    assert logros_reader.leer_de_texto("algo que no se entiende bien").encontrado is False


def test_horas_imposibles_se_descartan(monkeypatch):
    _responde(monkeypatch, {**CAPITAN, "horas_semana": 900})
    assert logros_reader.leer_de_texto("entreno muchísimo").horas_semana is None


def test_cuando_no_hay_actividad_lo_dice(monkeypatch):
    _responde(monkeypatch, {"encontrado": False, "confianza": 0.0})
    f = logros_reader.leer_de_texto("hola, ¿cómo funciona esto?")
    assert f.encontrado is False
    assert f.nombre is None


# ---------------------------------------------------------------------------
# 3 · el modelo no siempre devuelve JSON pelado
# ---------------------------------------------------------------------------


def test_aguanta_el_json_envuelto_en_backticks(monkeypatch):
    """Se le pide JSON pelado y casi siempre lo hace · tirar una respuesta
    buena por tres backticks sería absurdo."""
    _responde(monkeypatch, "```json\n" + json.dumps(CAPITAN) + "\n```")
    assert logros_reader.leer_de_texto("soy capitán del equipo").nombre


def test_una_respuesta_ilegible_da_un_error_para_la_persona(monkeypatch):
    _responde(monkeypatch, "no tengo ni idea de qué me estás hablando")
    with pytest.raises(logros_reader.LectorError):
        logros_reader.leer_de_texto("soy capitán del equipo de fútbol")


def test_un_texto_de_dos_palabras_no_gasta_una_llamada(monkeypatch):
    llamado = {"n": 0}

    def _no_deberia(*a, **k):
        llamado["n"] += 1
        return "{}", {}

    monkeypatch.setattr(document_ai, "call_claude_text", _no_deberia)
    with pytest.raises(logros_reader.LectorError):
        logros_reader.leer_de_texto("hola")
    assert llamado["n"] == 0


# ---------------------------------------------------------------------------
# 4 · el archivo
# ---------------------------------------------------------------------------


def test_un_pdf_con_texto_va_por_la_via_barata(monkeypatch):
    """Sin capa de texto habría que gastar visión · con ella, no."""
    cap = {}
    _responde(monkeypatch, CAPITAN, capturar=cap)
    monkeypatch.setattr(
        logros_reader, "extract_text_from_upload",
        lambda b, c, f: ("CONSTANCIA: capitán del equipo de fútbol 2024", {}),
    )

    f = logros_reader.leer_de_archivo(
        file_bytes=b"%PDF-falso", content_type="application/pdf", filename="d.pdf"
    )
    assert f.encontrado is True
    assert cap["via"] == "texto"
    assert "capitán del equipo" in cap["prompt"]


def test_una_foto_va_por_vision_con_sus_bytes(monkeypatch):
    cap = {}
    _responde(monkeypatch, CAPITAN, capturar=cap)
    monkeypatch.setattr(logros_reader, "extract_text_from_upload", lambda b, c, f: ("", {}))

    crudo = b"\x89PNG-falso"
    logros_reader.leer_de_archivo(
        file_bytes=crudo, content_type="image/png", filename="diploma.png"
    )
    assert cap["via"] == "vision"
    assert cap["bytes"] == crudo
    assert cap["mime"] == "image/png"


def test_un_pdf_escaneado_sin_texto_lo_dice_en_vez_de_fallar_raro(monkeypatch):
    _responde(monkeypatch, CAPITAN)
    monkeypatch.setattr(logros_reader, "extract_text_from_upload", lambda b, c, f: ("", {}))

    with pytest.raises(logros_reader.LectorError) as e:
        logros_reader.leer_de_archivo(
            file_bytes=b"%PDF", content_type="application/pdf", filename="escaneado.pdf"
        )
    assert "foto" in str(e.value)


def test_leer_un_archivo_no_lo_guarda_en_ningun_lado(monkeypatch):
    """⭐ Decisión de AH: se lee y se descarta.

    `STORAGE_BACKEND` está en `stub` en producción y el stub guarda los blobs
    en memoria del proceso — prometer que el diploma queda archivado y perderlo
    en el siguiente reinicio del dyno sería peor que no ofrecerlo.

    Si alguien conecta el almacenamiento aquí sin activar Supabase, este test
    lo caza.
    """
    from app.services import storage_service

    guardados = []
    monkeypatch.setattr(
        storage_service, "upload_file",
        lambda **k: guardados.append(k) or storage_service.StorageObject(
            bucket="b", path="p", content_type="c", size_bytes=0
        ),
    )
    _responde(monkeypatch, CAPITAN)
    monkeypatch.setattr(
        logros_reader, "extract_text_from_upload", lambda b, c, f: ("capitán de algo", {})
    )

    logros_reader.leer_de_archivo(
        file_bytes=b"%PDF", content_type="application/pdf", filename="d.pdf"
    )
    assert guardados == [], "el lector NO debe escribir el archivo en storage"
