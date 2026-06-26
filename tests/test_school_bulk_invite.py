"""bulk_invite_students · pre-carga sin N+1 + dedup correcto.

Antes hacía 2 queries por fila (User + Invitation) → N+1 en lotes grandes.
Ahora pre-carga usuarios existentes e invitaciones PENDING en 2 queries y
deduplica dentro del lote con un set. Este test fija el comportamiento:
salta usuarios ya existentes, invitaciones pendientes y duplicados del lote;
crea solo los emails realmente nuevos.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1 import school_admin as sa
from app.schemas.school_admin import BulkInviteRequest


@pytest.fixture()
def db(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    from app.db.models import Base
    Base.metadata.create_all(bind=engine)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _school(db):
    from app.db.models import School
    sc = School(name="Colegio Test", slug="colegio-test")
    db.add(sc)
    db.commit()
    return sc


def _user(db, email):
    from app.db.models import User
    u = User(email=email, hashed_password="x", name="U")
    db.add(u)
    db.commit()
    return u


def _pending_invite(db, school, email):
    from app.db.models import Invitation, InvitationStatus
    inv = Invitation(
        school_id=school.id, email=email, role="student", token=f"tok-{email}",
        status=InvitationStatus.PENDING.value,
        expires_at=datetime.utcnow() + timedelta(days=14),
    )
    db.add(inv)
    db.commit()
    return inv


def test_bulk_invite_skips_existing_pending_and_dupes(db, monkeypatch):
    school = _school(db)
    admin = _user(db, "admin@x.com")
    _user(db, "exists@x.com")              # ya es usuario → skip
    _pending_invite(db, school, "pending@x.com")  # invitación pendiente → skip

    created_emails: list = []
    monkeypatch.setattr(
        sa, "create_invitation",
        lambda **kw: created_emails.append(kw.get("email")),
    )
    monkeypatch.setattr(sa, "log_action", lambda *a, **k: None)

    payload = BulkInviteRequest(rows=[
        {"email": "exists@x.com"},
        {"email": "pending@x.com"},
        {"email": "new1@x.com"},
        {"email": "new2@x.com"},
        {"email": "new1@x.com"},  # duplicado dentro del lote → skip
    ])

    out = sa.bulk_invite_students(payload=payload, bundle=(school, admin), db=db)

    assert out["created"] == 2
    assert out["skipped"] == 3
    assert out["errors"] == []
    # create_invitation se llamó solo para los nuevos únicos
    assert created_emails == ["new1@x.com", "new2@x.com"]


def test_bulk_invite_all_new(db, monkeypatch):
    school = _school(db)
    admin = _user(db, "admin@x.com")
    monkeypatch.setattr(sa, "create_invitation", lambda **kw: None)
    monkeypatch.setattr(sa, "log_action", lambda *a, **k: None)

    payload = BulkInviteRequest(rows=[{"email": f"n{i}@x.com"} for i in range(5)])
    out = sa.bulk_invite_students(payload=payload, bundle=(school, admin), db=db)

    assert out["created"] == 5
    assert out["skipped"] == 0
