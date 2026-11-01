"""Diagnóstico de la carga de reportes externos · H-3, Sprint 4. SOLO LECTURA.

Verónica: *"cuando le subo reportes de exámenes se demora mucho"*. Medido en local,
la lectura con IA de un reporte de 11 páginas tarda ~10 s, así que la demora que
ella vio está en otra parte. Este script mira las cargas reales para saber dónde:

- cuánto pasa entre la subida y el final de la lectura (`uploaded_at` → `parsed_at`);
- cuántas se quedaron "processing" o "pending" (la pantalla se rinde a los 3 min);
- cuántas fallaron y por qué;
- tipo de archivo (PDF con texto, PDF escaneado, imagen) y tamaño;
- la latencia de la IA registrada en `ai_usage_log`.

No escribe nada. Se corre en producción con:

    heroku run -a grasshopper-api python scripts/medir_cargas_externas.py
"""
from __future__ import annotations

import os
import statistics
import sys
from collections import Counter
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> None:
    from app.db.database import SessionLocal
    from app.db.models import AIUsageLog, ExternalTestUpload

    db = SessionLocal()
    try:
        cargas = db.query(ExternalTestUpload).order_by(ExternalTestUpload.uploaded_at.desc()).limit(200).all()
        print(f"Cargas revisadas: {len(cargas)}\n")
        if not cargas:
            return

        print("Estados:", dict(Counter(c.parsing_status for c in cargas)))
        print("Tipos de archivo:", dict(Counter((c.content_type or "?") for c in cargas)))
        tamanos = [c.size_bytes for c in cargas if c.size_bytes]
        if tamanos:
            print(f"Tamaño: mediana {statistics.median(tamanos) // 1024} KB · máx {max(tamanos) // 1024} KB")

        duraciones = [
            ((c.parsed_at - c.uploaded_at).total_seconds(), c)
            for c in cargas if c.parsed_at and c.uploaded_at
        ]
        if duraciones:
            segs = sorted(d for d, _ in duraciones)
            p90 = segs[int(len(segs) * 0.9) - 1] if len(segs) >= 10 else segs[-1]
            print(f"\nSubida → lectura terminada: mediana {statistics.median(segs):.0f}s · p90 {p90:.0f}s · máx {segs[-1]:.0f}s")
            print("Las 10 más lentas:")
            for d, c in sorted(duraciones, key=lambda x: -x[0])[:10]:
                print(f"  {d:6.0f}s · {c.parsing_status:10} · {c.test_type:8} · {c.content_type} · "
                      f"{(c.size_bytes or 0) // 1024} KB · {(c.error_message or '')[:70]}")

        atascadas = [c for c in cargas if c.parsing_status in ("pending", "processing")
                     and c.uploaded_at < datetime.utcnow() - timedelta(minutes=5)]
        print(f"\nQuedaron sin terminar (más de 5 min en pending/processing): {len(atascadas)}")
        fallas = Counter((c.error_message or "")[:80] for c in cargas if c.parsing_status == "failed")
        if fallas:
            print("Fallas más comunes:")
            for msg, n in fallas.most_common(6):
                print(f"  {n} × {msg}")

        ia = (db.query(AIUsageLog).filter(AIUsageLog.feature == "external_test_parse")
              .order_by(AIUsageLog.created_at.desc()).limit(200).all())
        lat = sorted(x.latency_ms for x in ia if x.latency_ms)
        if lat:
            print(f"\nLatencia de la IA ({len(lat)} llamadas): mediana {statistics.median(lat) / 1000:.1f}s · "
                  f"máx {lat[-1] / 1000:.1f}s · modelos {dict(Counter(x.model for x in ia))}")
            entrada = [x.tokens_input for x in ia if x.tokens_input]
            if entrada:
                print(f"Tokens de entrada: mediana {statistics.median(entrada):.0f} · máx {max(entrada)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
