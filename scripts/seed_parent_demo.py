"""Seed demo data for the parent.test fixture · GH-PARENT-EXPERIENCE · 2026-05-05.

Populates the Cumbres school with the artifacts the parent panel exercises:
    - 2 ParentRelationship rows linking `parent.test@grasshopper.dev` to two
      seeded students (alumno9.cumbr · onboarding completed · alumno1.cumbr ·
      onboarding not_started).
    - 2 SchoolLegalDocument rows (parental_consent + privacy) · neither signed.
    - 2 SchoolMassMessage rows targeting parents (recent + old).
    - 3 SchoolEvent rows audience IN ('parents','both') · past · today · future.

Idempotent: re-running this script does NOT duplicate rows. Existing rows are
left intact except for harmless updates (e.g. relationship_type clamp).

Usage:
    ./venv/bin/python scripts/seed_parent_demo.py            # seed
    ./venv/bin/python scripts/seed_parent_demo.py --clean    # remove demo rows
    ./venv/bin/python scripts/seed_parent_demo.py --verify   # only print counts
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
DB_URL = os.environ["DATABASE_URL"]


PARENT_EMAIL = "parent.test@grasshopper.dev"
SCHOOL_SLUG = "seed-cumbres"
CHILD_EMAILS = (
    "alumno9.cumbr@grasshopper.dev",  # onboarding completed in seed_test_data.py
    "alumno1.cumbr@grasshopper.dev",  # onboarding not_started in seed_test_data.py
)

# Sentinels used to identify rows created by this script (so --clean is safe).
LEGAL_VERSION_TAG = "demo-2026-05-05"
MASS_MESSAGE_SUBJECTS = (
    "Bienvenida al programa de orientación · Cumbres",
    "Reunión informativa de cierre de ciclo (recordatorio)",
)
EVENT_TITLE_TAG = "[seed-parent-demo]"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fetchone_id(cur, query, params):
    cur.execute(query, params)
    row = cur.fetchone()
    return row[0] if row else None


def _resolve_ids(cur):
    parent_id = _fetchone_id(
        cur, "SELECT id FROM users WHERE email = %s AND role = 'PARENT'", (PARENT_EMAIL,)
    )
    school_id = _fetchone_id(
        cur, "SELECT id FROM schools WHERE slug = %s", (SCHOOL_SLUG,)
    )
    if not parent_id:
        raise SystemExit(
            f"  ! parent.test no existe ({PARENT_EMAIL}) · corre seed_test_data.py primero"
        )
    if not school_id:
        raise SystemExit(
            f"  ! school no existe ({SCHOOL_SLUG}) · corre seed_test_data.py primero"
        )
    cur.execute(
        "SELECT email, id FROM users WHERE email = ANY(%s)",
        (list(CHILD_EMAILS),),
    )
    children = dict(cur.fetchall())
    missing = [e for e in CHILD_EMAILS if e not in children]
    if missing:
        raise SystemExit(
            f"  ! students missing: {missing} · corre seed_test_data.py primero"
        )
    return parent_id, school_id, children


# ---------------------------------------------------------------------------
# Seed steps · all idempotent
# ---------------------------------------------------------------------------


def _ensure_relationships(cur, parent_id, children):
    inserted = 0
    for email, student_id in children.items():
        existing = _fetchone_id(
            cur,
            """
            SELECT id FROM parent_relationships
            WHERE parent_user_id = %s AND student_user_id = %s
            """,
            (parent_id, student_id),
        )
        rel_type = "father"  # demo default
        if existing:
            cur.execute(
                """
                UPDATE parent_relationships
                SET is_active = TRUE, relationship = %s
                WHERE id = %s
                """,
                (rel_type, existing),
            )
            continue
        cur.execute(
            """
            INSERT INTO parent_relationships (id, parent_user_id, student_user_id, relationship,
                                              is_active, created_at)
            VALUES (%s, %s, %s, %s, TRUE, NOW())
            """,
            (str(uuid.uuid4()), parent_id, student_id, rel_type),
        )
        inserted += 1
    return inserted


def _ensure_legal_documents(cur, school_id):
    """Two unsigned docs: parental_consent + privacy. Tagged with version sentinel."""
    plans = [
        (
            "parental_consent",
            f"v1.0-{LEGAL_VERSION_TAG}",
            (
                "CONSENTIMIENTO PARENTAL · Colegio Cumbres\n\n"
                "Por la presente autorizo a Grasshopper a procesar los datos de mi "
                "hijo/a con fines de orientación vocacional, conforme a la Ley 1581 "
                "de 2012. Esta autorización es revocable en cualquier momento desde "
                "el panel familiar."
            ),
        ),
        (
            "privacy",
            f"v1.0-{LEGAL_VERSION_TAG}",
            (
                "POLÍTICA DE PRIVACIDAD · Colegio Cumbres (versión familias)\n\n"
                "Detalle del tratamiento de datos personales del alumno y de los "
                "padres/tutores. Para consultas sobre derechos ARCO, escribir a "
                "habeasdata@grasshopper.app."
            ),
        ),
    ]
    inserted = 0
    for doc_type, version, content in plans:
        existing = _fetchone_id(
            cur,
            """
            SELECT id FROM school_legal_documents
            WHERE school_id = %s AND type = %s AND version = %s
            """,
            (school_id, doc_type, version),
        )
        if existing:
            continue
        cur.execute(
            """
            INSERT INTO school_legal_documents (id, school_id, type, version, content,
                                                effective_at, created_at)
            VALUES (%s, %s, %s, %s, %s, NOW() - INTERVAL '7 days', NOW() - INTERVAL '7 days')
            """,
            (str(uuid.uuid4()), school_id, doc_type, version, content),
        )
        inserted += 1
    return inserted


def _ensure_mass_messages(cur, school_id):
    """Two messages: one recent (1 day) and one older (20 days). Audience parents."""
    recent_subject, old_subject = MASS_MESSAGE_SUBJECTS
    plans = [
        (
            recent_subject,
            (
                "Estimadas familias,\n\nEsta semana iniciamos el programa de "
                "orientación vocacional. Encontrarán en el panel los hitos de su "
                "hijo/a y el calendario de actividades."
            ),
            "1 day",
        ),
        (
            old_subject,
            (
                "Recordatorio · La reunión informativa de cierre de ciclo está "
                "programada para el último viernes del mes. Por favor confirmen "
                "asistencia desde la sección Eventos."
            ),
            "20 days",
        ),
    ]
    inserted = 0
    for subject, body, age in plans:
        existing = _fetchone_id(
            cur,
            """
            SELECT id FROM school_mass_messages
            WHERE school_id = %s AND subject = %s AND audience = 'parents'
            """,
            (school_id, subject),
        )
        if existing:
            continue
        cur.execute(
            f"""
            INSERT INTO school_mass_messages (id, school_id, author_user_id, subject, body,
                                              audience, sent_at, sent_count, opened_count)
            VALUES (%s, %s, NULL, %s, %s, 'parents',
                    NOW() - INTERVAL '{age}', 1, 0)
            """,
            (str(uuid.uuid4()), school_id, subject, body),
        )
        inserted += 1
    return inserted


def _ensure_notifications(cur, parent_id):
    """Seed 2 in-app notifications for parent.test · idempotent by title prefix."""
    notifications = [
        (
            "legal_document_pending",
            "Documento pendiente · Consentimiento parental",
            "El colegio publicó 'Consentimiento parental' versión v1.0. Te pedimos firmar.",
            '{"navigate_to": "/parent/legal"}',
        ),
        (
            "mass_message_received",
            "Mensaje del colegio · Bienvenida al programa de orientación",
            "Esta semana iniciamos el programa de orientación vocacional…",
            '{"navigate_to": "/parent/messages"}',
        ),
    ]
    inserted = 0
    for ntype, title, body, data_json in notifications:
        existing = _fetchone_id(
            cur,
            "SELECT id FROM notifications WHERE user_id = %s AND type = %s AND title = %s",
            (parent_id, ntype, title),
        )
        if existing:
            continue
        cur.execute(
            """
            INSERT INTO notifications (id, user_id, type, title, body, data, created_at)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, NOW() - INTERVAL '1 hour')
            """,
            (str(uuid.uuid4()), parent_id, ntype, title, body, data_json),
        )
        inserted += 1
    return inserted


def _ensure_events(cur, school_id):
    """Past · today · future · audience parents/both."""
    today = datetime.utcnow().replace(hour=18, minute=0, second=0, microsecond=0)
    plans = [
        (
            f"{EVENT_TITLE_TAG} Charla informativa para padres",
            "Sesión cerrada · feedback de la jornada anterior. Ver acta en el panel.",
            today - timedelta(days=14),
            "Auditorio Cumbres",
            "parents",
        ),
        (
            f"{EVENT_TITLE_TAG} Reunión virtual de hoy",
            "Encuentro corto con el psicólogo del programa para resolver preguntas.",
            today,
            "Zoom (link enviado por email)",
            "both",
        ),
        (
            f"{EVENT_TITLE_TAG} Feria de universidades 2026",
            "Universidades aliadas presentan sus programas internacionales.",
            today + timedelta(days=21),
            "Centro de Convenciones · Bogotá",
            "parents",
        ),
    ]
    inserted = 0
    for title, description, starts_at, location, audience in plans:
        existing = _fetchone_id(
            cur,
            "SELECT id FROM school_events WHERE school_id = %s AND title = %s",
            (school_id, title),
        )
        if existing:
            continue
        ends_at = starts_at + timedelta(hours=2)
        cur.execute(
            """
            INSERT INTO school_events (id, school_id, title, description, starts_at, ends_at,
                                       location, audience, created_by, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NULL, NOW())
            """,
            (
                str(uuid.uuid4()),
                school_id,
                title,
                description,
                starts_at,
                ends_at,
                location,
                audience,
            ),
        )
        inserted += 1
    return inserted


# ---------------------------------------------------------------------------
# Verify / clean
# ---------------------------------------------------------------------------


def _print_counts(cur, parent_id, school_id):
    rels = _fetchone_id(
        cur,
        "SELECT COUNT(*) FROM parent_relationships WHERE parent_user_id = %s AND is_active",
        (parent_id,),
    )
    docs = _fetchone_id(
        cur,
        "SELECT COUNT(*) FROM school_legal_documents WHERE school_id = %s",
        (school_id,),
    )
    msgs = _fetchone_id(
        cur,
        "SELECT COUNT(*) FROM school_mass_messages WHERE school_id = %s AND audience = 'parents'",
        (school_id,),
    )
    events = _fetchone_id(
        cur,
        """
        SELECT COUNT(*) FROM school_events
        WHERE school_id = %s AND audience IN ('parents','both') AND archived_at IS NULL
        """,
        (school_id,),
    )
    print("  ParentRelationship (active)    :", rels)
    print("  SchoolLegalDocument (Cumbres)  :", docs)
    print("  SchoolMassMessage parents      :", msgs)
    print("  SchoolEvent parents+both       :", events)


def seed():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    print("=" * 60)
    print("PARENT DEMO SEED · 2026-05-05")
    print("=" * 60)
    parent_id, school_id, children = _resolve_ids(cur)
    print(f"  parent_id = {parent_id} · school_id = {school_id}")
    rel_n = _ensure_relationships(cur, parent_id, children)
    docs_n = _ensure_legal_documents(cur, school_id)
    msgs_n = _ensure_mass_messages(cur, school_id)
    events_n = _ensure_events(cur, school_id)
    conn.commit()
    print("  inserted: rels=%s · docs=%s · msgs=%s · events=%s"
          % (rel_n, docs_n, msgs_n, events_n))
    print("\nFinal counts:")
    _print_counts(cur, parent_id, school_id)
    cur.close()
    conn.close()
    print("\n" + "=" * 60)
    print("✓ PARENT DEMO SEED OK")
    print("=" * 60)


def verify():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    parent_id, school_id, _ = _resolve_ids(cur)
    print("PARENT DEMO VERIFICATION · counts only")
    _print_counts(cur, parent_id, school_id)
    cur.close()
    conn.close()


def clean():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    print("PARENT DEMO · CLEAN")
    parent_id, school_id, children = _resolve_ids(cur)
    cur.execute(
        "DELETE FROM school_legal_signatures WHERE signer_user_id = %s",
        (parent_id,),
    )
    cur.execute(
        "DELETE FROM school_legal_documents WHERE school_id = %s AND version LIKE %s",
        (school_id, f"%{LEGAL_VERSION_TAG}%"),
    )
    print(f"  ✓ legal docs removed: {cur.rowcount}")
    cur.execute(
        """
        DELETE FROM school_mass_messages
        WHERE school_id = %s AND audience = 'parents' AND subject = ANY(%s)
        """,
        (school_id, list(MASS_MESSAGE_SUBJECTS)),
    )
    print(f"  ✓ mass messages removed: {cur.rowcount}")
    cur.execute(
        "DELETE FROM school_events WHERE school_id = %s AND title LIKE %s",
        (school_id, f"{EVENT_TITLE_TAG}%"),
    )
    print(f"  ✓ events removed: {cur.rowcount}")
    cur.execute(
        """
        DELETE FROM parent_relationships
        WHERE parent_user_id = %s AND student_user_id = ANY(%s)
        """,
        (parent_id, list(children.values())),
    )
    print(f"  ✓ relationships removed: {cur.rowcount}")
    conn.commit()
    cur.close()
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--clean", action="store_true", help="Remove demo rows")
    parser.add_argument("--verify", action="store_true", help="Print counts and exit")
    args = parser.parse_args()
    if args.clean:
        clean()
    elif args.verify:
        verify()
    else:
        seed()
