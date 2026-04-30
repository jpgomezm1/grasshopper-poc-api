"""Seed the initial Grasshopper super_admin user.

GH-S2-DB-04 · run once after migrations 003 + 004 + 005 are applied.

Reads credentials from environment:
    SUPER_ADMIN_EMAIL     · default 'admin@grasshopper.local'
    SUPER_ADMIN_PASSWORD  · REQUIRED · refuses to run with default in non-dev
    SUPER_ADMIN_NAME      · default 'Grasshopper Admin'

Idempotent: if a user with that email already exists, ensures it has
role=super_admin (no password change). Safe to run multiple times.

Usage:
    cd backend
    source venv/bin/activate
    SUPER_ADMIN_EMAIL=admin@grasshopper.com SUPER_ADMIN_PASSWORD=Grass2026! python scripts/seed_super_admin.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure backend/ is on sys.path so `app.*` imports resolve
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.api.v1.auth import get_password_hash  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import OnboardingStatus, User, UserRole  # noqa: E402


DEFAULT_EMAIL = "admin@grasshopper.local"
DEFAULT_NAME = "Grasshopper Admin"


def main() -> int:
    settings = get_settings()
    email = os.getenv("SUPER_ADMIN_EMAIL", DEFAULT_EMAIL).lower()
    password = os.getenv("SUPER_ADMIN_PASSWORD")
    name = os.getenv("SUPER_ADMIN_NAME", DEFAULT_NAME)

    if not password:
        print("ERROR · SUPER_ADMIN_PASSWORD env var is required.", file=sys.stderr)
        return 2

    # Refuse weak default password in production-ish environments
    if password.lower() in {"admin", "password", "changeme", "1234", "grasshopper"}:
        print("ERROR · SUPER_ADMIN_PASSWORD is too weak.", file=sys.stderr)
        return 2

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            updated = False
            if existing.role != UserRole.SUPER_ADMIN:
                existing.role = UserRole.SUPER_ADMIN
                updated = True
            if existing.school_id is not None:
                existing.school_id = None  # super_admin should not be tied to a school
                updated = True
            if not existing.is_active:
                existing.is_active = True
                updated = True
            if updated:
                db.commit()
                print(f"[seed_super_admin] updated existing user {email} -> role=super_admin")
            else:
                print(f"[seed_super_admin] user {email} already a super_admin · noop")
            return 0

        user = User(
            email=email,
            hashed_password=get_password_hash(password),
            name=name,
            role=UserRole.SUPER_ADMIN,
            school_id=None,
            onboarding_status=OnboardingStatus.COMPLETED,
            is_active=True,
        )
        db.add(user)
        db.commit()
        print(f"[seed_super_admin] created super_admin {email} (env={settings.environment})")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
