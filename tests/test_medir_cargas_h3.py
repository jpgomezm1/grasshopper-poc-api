"""H-3 · el diagnóstico de cargas corre y dice lo que importa (sin escribir nada)."""
from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta
from pathlib import Path

from tests.test_bot_gratuito_b4 import app_db  # noqa: F401
from tests.test_planes_d1 import _usuario

_ruta = Path(__file__).resolve().parent.parent / "scripts" / "medir_cargas_externas.py"
_spec = importlib.util.spec_from_file_location("medir_cargas_externas", _ruta)
script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(script)


def test_resume_tiempos_atascadas_y_fallas(app_db, capsys):
    from app.db.models import AIUsageLog, ExternalTestUpload

    _, Sesion = app_db
    s = Sesion()
    u = _usuario(s, "carga@h3.dev")
    ahora = datetime.utcnow()
    base = dict(user_id=u.id, file_path="x", test_type="istrong", content_type="application/pdf", size_bytes=200_000)
    s.add(ExternalTestUpload(**base, parsing_status="done", uploaded_at=ahora - timedelta(minutes=30),
                             parsed_at=ahora - timedelta(minutes=29, seconds=50)))
    s.add(ExternalTestUpload(**base, parsing_status="processing", uploaded_at=ahora - timedelta(hours=2)))
    s.add(ExternalTestUpload(**base, parsing_status="failed", uploaded_at=ahora - timedelta(hours=3),
                             parsed_at=ahora - timedelta(hours=3), error_message="PDF has no text layer"))
    s.add(AIUsageLog(provider="anthropic", model="claude-haiku-5-5", feature="external_test_parse", latency_ms=8000))
    s.commit()
    antes = s.query(ExternalTestUpload).count()
    s.close()

    script.main()
    salida = capsys.readouterr().out
    assert "Cargas revisadas: 3" in salida
    assert "Quedaron sin terminar (más de 5 min en pending/processing): 1" in salida
    assert "PDF has no text layer" in salida
    assert "Latencia de la IA (1 llamadas): mediana 8.0s" in salida

    s = Sesion()
    assert s.query(ExternalTestUpload).count() == antes  # no escribe nada
    s.close()
