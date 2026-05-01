"""Bitrix payload mappers · GH-S10-BE-02.

Pure functions that turn our domain objects into Bitrix REST `fields`
dictionaries. They do NOT call the Bitrix API · they only shape data.

Why pure:
    - Trivial to unit test (no DB, no httpx).
    - Reusable from sync_service for both create and update flows.
    - Versioned via `MAPPER_VERSION` so we can replay old payloads.

Mapping spec (see docs/RUNBOOK_BITRIX.md for the full table):

    User              → Lead (NAME / LAST_NAME / EMAIL / PHONE / SOURCE_ID / TITLE)
                      → Contact (when promoted to qualified)
    ConsolidatedProfile → Lead.COMMENTS + UF_CRM_GH_PROFILE_*
    RecommendedPrograms → Deal (TITLE / OPPORTUNITY / CURRENCY_ID / UF_CRM_GH_PROGRAMS)
    AdvisorLead         → Lead.COMMENTS (auto-brief) + STATUS_ID = "PROCESS"
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional


MAPPER_VERSION = "s10-v1"


# -----------------------------------------------------------------------------
# Source-of-truth domain bundle for the mappers (avoids DB coupling)
# -----------------------------------------------------------------------------


@dataclass
class StudentSyncBundle:
    """Snapshot consumed by the mappers.

    The sync_service builds this from the DB so the mappers stay pure.
    """

    user_id: str
    email: str
    name: Optional[str] = None
    phone: Optional[str] = None
    school_name: Optional[str] = None
    school_id: Optional[str] = None
    role: Optional[str] = None  # "student" mostly · we still tag it for Bitrix

    # Consolidated profile (from S6)
    profile_summary: Optional[str] = None
    profile_strengths: Optional[List[str]] = None
    profile_career_paths: Optional[List[str]] = None
    profile_hash: Optional[str] = None

    # Vocational tests · just a list of (test_id, top_codes/level/personality)
    vocational_summary: Optional[List[Dict[str, Any]]] = None

    # English level (CEFR)
    english_cefr: Optional[str] = None

    # Recommended programs (from S6) · enough fields to build a Deal opportunity
    recommended_programs: Optional[List[Dict[str, Any]]] = None
    budget_band: Optional[str] = None
    budget_max_usd: Optional[int] = None
    preferred_countries: Optional[List[str]] = None

    # AdvisorLead (S1 POC · brief + flag)
    advisor_brief: Optional[str] = None
    advisor_requested: bool = False

    # Cross-reference fields
    bitrix_lead_id: Optional[str] = None
    bitrix_contact_id: Optional[str] = None
    bitrix_deal_id: Optional[str] = None


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _split_name(name: Optional[str]) -> tuple[str, str]:
    if not name:
        return ("", "")
    parts = name.strip().split()
    if len(parts) == 1:
        return (parts[0], "")
    return (parts[0], " ".join(parts[1:]))


def _format_brief(bundle: StudentSyncBundle) -> str:
    """Build a single-text brief for Bitrix.COMMENTS.

    Combines the consolidated-profile summary, strengths, top recs,
    advisor brief if present. Truncated at 4_000 chars (Bitrix-safe).
    """
    parts: List[str] = []

    if bundle.advisor_brief:
        parts.append("# Brief asesor\n" + bundle.advisor_brief.strip())

    if bundle.profile_summary:
        parts.append("# Perfil consolidado\n" + bundle.profile_summary.strip())

    if bundle.profile_strengths:
        parts.append(
            "# Fortalezas\n- " + "\n- ".join(s.strip() for s in bundle.profile_strengths)
        )

    if bundle.profile_career_paths:
        parts.append(
            "# Rutas sugeridas\n- "
            + "\n- ".join(p.strip() for p in bundle.profile_career_paths)
        )

    if bundle.vocational_summary:
        rows: List[str] = []
        for row in bundle.vocational_summary:
            test_id = row.get("test_id", "?")
            top = row.get("top") or row.get("level") or row.get("personality")
            rows.append(f"- {test_id}: {top}")
        if rows:
            parts.append("# Tests psicométricos\n" + "\n".join(rows))

    if bundle.english_cefr:
        parts.append(f"# Inglés CEFR\n{bundle.english_cefr}")

    if bundle.recommended_programs:
        rec_rows: List[str] = []
        for prog in bundle.recommended_programs[:6]:
            name = prog.get("name") or prog.get("program_id") or "?"
            country = prog.get("country") or "?"
            cost = prog.get("cost_total")
            cost_str = f" · USD {cost:,}" if isinstance(cost, int) else ""
            rec_rows.append(f"- {name} · {country}{cost_str}")
        if rec_rows:
            parts.append("# Programas recomendados\n" + "\n".join(rec_rows))

    if bundle.preferred_countries:
        parts.append("# Países preferidos\n" + ", ".join(bundle.preferred_countries))

    if bundle.budget_band:
        suffix = (
            f" (≤ USD {bundle.budget_max_usd:,})"
            if bundle.budget_max_usd
            else ""
        )
        parts.append(f"# Presupuesto\n{bundle.budget_band}{suffix}")

    text = "\n\n".join(parts).strip()
    return text[:4000]


def _avg_program_cost(programs: Iterable[Dict[str, Any]]) -> Optional[int]:
    costs = [
        int(p["cost_total"])
        for p in programs
        if isinstance(p.get("cost_total"), (int, float))
    ]
    if not costs:
        return None
    return int(sum(costs) / len(costs))


# -----------------------------------------------------------------------------
# Public mappers
# -----------------------------------------------------------------------------


def map_user_to_lead_fields(bundle: StudentSyncBundle) -> Dict[str, Any]:
    """Map the student bundle to Bitrix `crm.lead.add/update` fields."""
    first_name, last_name = _split_name(bundle.name)
    title_bits: List[str] = []
    if bundle.school_name:
        title_bits.append(bundle.school_name)
    title_bits.append("Grasshopper · estudiante")
    title = " · ".join(title_bits)

    fields: Dict[str, Any] = {
        "TITLE": title,
        "NAME": first_name,
        "LAST_NAME": last_name,
        "EMAIL": [{"VALUE": bundle.email, "VALUE_TYPE": "WORK"}],
        "SOURCE_ID": "WEB",
        "SOURCE_DESCRIPTION": "Grasshopper plataforma",
        "OPENED": "Y",
        "STATUS_ID": "PROCESSED" if bundle.advisor_requested else "NEW",
        "COMMENTS": _format_brief(bundle),
        # Custom fields (UF_CRM_*) · school_id + plataforma · client may rename.
        "UF_CRM_GH_USER_ID": bundle.user_id,
        "UF_CRM_GH_SCHOOL_ID": bundle.school_id or "",
        "UF_CRM_GH_PROFILE_HASH": bundle.profile_hash or "",
        "UF_CRM_GH_MAPPER_VERSION": MAPPER_VERSION,
    }

    if bundle.phone:
        fields["PHONE"] = [{"VALUE": bundle.phone, "VALUE_TYPE": "MOBILE"}]

    if bundle.preferred_countries:
        fields["UF_CRM_GH_COUNTRIES"] = ", ".join(bundle.preferred_countries)
    if bundle.budget_band:
        fields["UF_CRM_GH_BUDGET_BAND"] = bundle.budget_band
    if bundle.budget_max_usd:
        fields["UF_CRM_GH_BUDGET_USD"] = bundle.budget_max_usd
    if bundle.english_cefr:
        fields["UF_CRM_GH_CEFR"] = bundle.english_cefr

    return fields


def map_user_to_contact_fields(bundle: StudentSyncBundle) -> Dict[str, Any]:
    """Map the student bundle to Bitrix `crm.contact.add/update` fields.

    Used when a lead is qualified · we keep the same UF mapping for cross-ref.
    """
    first_name, last_name = _split_name(bundle.name)
    fields: Dict[str, Any] = {
        "NAME": first_name,
        "LAST_NAME": last_name,
        "EMAIL": [{"VALUE": bundle.email, "VALUE_TYPE": "WORK"}],
        "OPENED": "Y",
        "TYPE_ID": "CLIENT",
        "SOURCE_ID": "WEB",
        "UF_CRM_GH_USER_ID": bundle.user_id,
        "UF_CRM_GH_SCHOOL_ID": bundle.school_id or "",
        "UF_CRM_GH_MAPPER_VERSION": MAPPER_VERSION,
    }
    if bundle.phone:
        fields["PHONE"] = [{"VALUE": bundle.phone, "VALUE_TYPE": "MOBILE"}]
    return fields


def map_recommendations_to_deal_fields(
    bundle: StudentSyncBundle,
    *,
    contact_id: Optional[str] = None,
    lead_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Map the recommended programs to a Bitrix Deal."""
    programs = bundle.recommended_programs or []
    program_titles = [p.get("name") or p.get("program_id") or "?" for p in programs]
    title = "Plan vocacional · " + (bundle.name or bundle.email or bundle.user_id)

    avg = _avg_program_cost(programs)

    fields: Dict[str, Any] = {
        "TITLE": title[:240],
        "OPPORTUNITY": avg or 0,
        "CURRENCY_ID": "USD",
        "OPENED": "Y",
        "STAGE_ID": "NEW",
        "SOURCE_ID": "WEB",
        "COMMENTS": _format_brief(bundle),
        "UF_CRM_GH_USER_ID": bundle.user_id,
        "UF_CRM_GH_SCHOOL_ID": bundle.school_id or "",
        "UF_CRM_GH_PROGRAMS": ", ".join(program_titles[:10])[:1000],
        "UF_CRM_GH_PROGRAMS_COUNT": len(programs),
        "UF_CRM_GH_MAPPER_VERSION": MAPPER_VERSION,
    }
    if contact_id:
        fields["CONTACT_ID"] = contact_id
    if lead_id:
        fields["LEAD_ID"] = lead_id
    return fields


def map_advisor_lead_comment(bundle: StudentSyncBundle) -> str:
    """Comment posted to the timeline when an AdvisorLead is created."""
    summary = bundle.advisor_brief or "Solicitud de asesor sin brief auto-generado."
    return (
        "Estudiante solicitó asesor humano desde Grasshopper.\n\n"
        f"Email: {bundle.email}\n"
        f"Teléfono: {bundle.phone or '(no provisto)'}\n\n"
        f"Brief:\n{summary[:2000]}"
    )


# -----------------------------------------------------------------------------
# Inverse: inbound webhook payload → User update fields
# -----------------------------------------------------------------------------


# Bitrix `STATUS_ID` (canonical) → our `bitrix_lead_status` simplified vocabulary.
# The `*` wildcard catches anything not explicitly mapped.
_INBOUND_STATUS_MAP = {
    "NEW": "new",
    "IN_PROCESS": "qualified",
    "PROCESSED": "qualified",
    "PROCESS": "qualified",
    "ASSIGNED": "qualified",
    "CONTACTED": "contacted",
    "CONVERTED": "contacted",
    "JUNK": "lost",
    "LOST": "lost",
    "DECLINED": "lost",
}


def normalize_inbound_status(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    return _INBOUND_STATUS_MAP.get(raw.upper(), raw.lower()[:40])


__all__ = [
    "StudentSyncBundle",
    "MAPPER_VERSION",
    "map_user_to_lead_fields",
    "map_user_to_contact_fields",
    "map_recommendations_to_deal_fields",
    "map_advisor_lead_comment",
    "normalize_inbound_status",
]
