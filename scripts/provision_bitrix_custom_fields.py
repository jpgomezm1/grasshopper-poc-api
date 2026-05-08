"""Provision Bitrix24 custom fields (UF_CRM_GH_*) on the client portal.

Run this ONCE after credentials are configured (BITRIX_WEBHOOK_URL set).
The bitrix_mapper.py module emits these custom fields on every sync; if
they don't exist on the Bitrix portal Bitrix silently drops the values.

Idempotent: checks `crm.<entity>.userfield.list` before adding. Re-running
is a no-op when fields already exist.

Usage:
    ./venv/bin/python scripts/provision_bitrix_custom_fields.py        # apply
    ./venv/bin/python scripts/provision_bitrix_custom_fields.py --dry-run

Required env (read from .env):
    BITRIX_WEBHOOK_URL    https://<portal>.bitrix24.com/rest/<user>/<token>/
    BITRIX_USER_TOKEN     (legacy compatibility)

Custom fields provisioned (one per ENTITY_LEAD + ENTITY_DEAL):

    UF_CRM_GH_USER_ID         · string · UUID of student in our DB (match key)
    UF_CRM_GH_SCHOOL_ID       · string · UUID of school (or empty for B2C)
    UF_CRM_GH_PROFILE_HASH    · string · audit hash of consolidated profile
    UF_CRM_GH_MAPPER_VERSION  · string · mapper version tag (s10-v1 etc.)
    UF_CRM_GH_COUNTRIES       · string · comma-separated preferred countries
    UF_CRM_GH_BUDGET_BAND     · string · low/medium/high
    UF_CRM_GH_BUDGET_USD      · integer · max usd budget
    UF_CRM_GH_CEFR            · string · A1..C2 English level
    UF_CRM_GH_PROGRAMS        · string · top recommended program titles (CSV)
    UF_CRM_GH_PROGRAMS_COUNT  · integer · count of recommendations
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Dict, List

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

WEBHOOK_URL = os.environ.get("BITRIX_WEBHOOK_URL", "").rstrip("/")

# field_name → (USER_TYPE_ID, label, required, multiple)
FIELDS: Dict[str, Dict[str, str | bool]] = {
    "UF_CRM_GH_USER_ID":        {"type": "string", "label": "Grasshopper · User ID"},
    "UF_CRM_GH_SCHOOL_ID":      {"type": "string", "label": "Grasshopper · School ID"},
    "UF_CRM_GH_PROFILE_HASH":   {"type": "string", "label": "Grasshopper · Profile Hash"},
    "UF_CRM_GH_MAPPER_VERSION": {"type": "string", "label": "Grasshopper · Mapper Version"},
    "UF_CRM_GH_COUNTRIES":      {"type": "string", "label": "Grasshopper · Países preferidos"},
    "UF_CRM_GH_BUDGET_BAND":    {"type": "string", "label": "Grasshopper · Budget band"},
    "UF_CRM_GH_BUDGET_USD":     {"type": "integer", "label": "Grasshopper · Budget USD"},
    "UF_CRM_GH_CEFR":           {"type": "string", "label": "Grasshopper · CEFR (English)"},
    "UF_CRM_GH_PROGRAMS":       {"type": "string", "label": "Grasshopper · Programas (top)"},
    "UF_CRM_GH_PROGRAMS_COUNT": {"type": "integer", "label": "Grasshopper · Programas (count)"},
}

# Bitrix entities we sync to · we provision the same fields on both
ENTITIES = (
    ("crm.lead.userfield", "Lead"),
    ("crm.deal.userfield", "Deal"),
)


def _call(method: str, params: dict) -> dict:
    if not WEBHOOK_URL:
        raise SystemExit(
            "BITRIX_WEBHOOK_URL not set · cannot provision against stub backend."
        )
    url = f"{WEBHOOK_URL}/{method}.json"
    r = httpx.post(url, json=params, timeout=30.0)
    r.raise_for_status()
    body = r.json()
    if "error" in body:
        raise RuntimeError(f"Bitrix error · {body.get('error')}: {body.get('error_description')}")
    return body


def list_existing(method_prefix: str) -> List[str]:
    """Return the set of FIELD_NAME already defined on this entity."""
    out: List[str] = []
    start = 0
    while True:
        resp = _call(f"{method_prefix}.list", {"start": start, "order": {"SORT": "ASC"}})
        items = resp.get("result", []) or []
        for f in items:
            name = f.get("FIELD_NAME")
            if name:
                out.append(name)
        next_start = resp.get("next")
        if next_start is None:
            break
        start = next_start
    return out


def provision(method_prefix: str, label_prefix: str, dry_run: bool = False) -> None:
    print(f"\n=== {label_prefix} ({method_prefix}) ===")
    existing = set(list_existing(method_prefix))
    to_create = [f for f in FIELDS.keys() if f not in existing]
    if not to_create:
        print(f"  ✓ All {len(FIELDS)} fields already exist · nothing to do.")
        return
    print(f"  Will create {len(to_create)} field(s): {', '.join(to_create)}")
    if dry_run:
        print("  --dry-run · skipping actual creation.")
        return
    for field_name in to_create:
        spec = FIELDS[field_name]
        fields_payload = {
            "FIELD_NAME": field_name,
            "USER_TYPE_ID": spec["type"],
            "EDIT_FORM_LABEL": {"es": spec["label"], "en": spec["label"]},
            "LIST_COLUMN_LABEL": {"es": spec["label"], "en": spec["label"]},
            "LIST_FILTER_LABEL": {"es": spec["label"], "en": spec["label"]},
            "MANDATORY": "N",
            "MULTIPLE": "N",
            "SHOW_FILTER": "Y",
            "SHOW_IN_LIST": "Y",
            "SETTINGS": {},
        }
        try:
            resp = _call(f"{method_prefix}.add", {"fields": fields_payload})
            new_id = resp.get("result")
            print(f"  ✓ Created {field_name} · id={new_id}")
        except Exception as exc:
            print(f"  ✗ FAILED to create {field_name}: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision Bitrix24 custom fields for Grasshopper.")
    parser.add_argument("--dry-run", action="store_true", help="List what would change · do not create.")
    args = parser.parse_args()

    if not WEBHOOK_URL:
        print("ERROR: BITRIX_WEBHOOK_URL is empty · stub mode active.", file=sys.stderr)
        print("Set BITRIX_WEBHOOK_URL in .env before running this script.", file=sys.stderr)
        return 1

    print("=" * 60)
    print("Bitrix24 Custom Fields Provisioning · Grasshopper")
    print("=" * 60)
    print(f"Portal: {WEBHOOK_URL.split('/rest/')[0]}")
    print(f"Mode: {'DRY-RUN' if args.dry_run else 'APPLY'}")

    for method_prefix, label in ENTITIES:
        provision(method_prefix, label, dry_run=args.dry_run)

    print("\n" + "=" * 60)
    print("✓ DONE")
    print("=" * 60)
    if args.dry_run:
        print("Re-run without --dry-run to apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
