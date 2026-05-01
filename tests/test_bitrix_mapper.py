"""Unit tests · bitrix_mapper (GH-S10-BE-02).

Pure-function tests · no DB, no network.
"""
from __future__ import annotations

from app.services.bitrix_mapper import (
    MAPPER_VERSION,
    StudentSyncBundle,
    map_advisor_lead_comment,
    map_recommendations_to_deal_fields,
    map_user_to_contact_fields,
    map_user_to_lead_fields,
    normalize_inbound_status,
)


def _bundle(**overrides):
    base = dict(
        user_id="u-123",
        email="ana@example.com",
        name="Ana Maria Lopez",
        phone="+57 300 1234567",
        school_name="Colegio Andino",
        school_id="s-1",
        profile_summary="Estudiante curiosa con orientación a la ingeniería.",
        profile_strengths=["pensamiento crítico", "diseño"],
        profile_career_paths=["Ingeniería de software", "Diseño industrial"],
        profile_hash="abc123",
        vocational_summary=[
            {"test_id": "mbti", "personality": "INTJ"},
            {"test_id": "holland", "top": ["I", "A", "R"]},
        ],
        english_cefr="B2",
        recommended_programs=[
            {
                "program_id": "p-1",
                "name": "BSc Computer Science",
                "country": "Estados Unidos",
                "cost_total": 60000,
            },
            {
                "program_id": "p-2",
                "name": "BA Industrial Design",
                "country": "Canadá",
                "cost_total": 45000,
            },
        ],
        budget_band="medio",
        budget_max_usd=70000,
        preferred_countries=["Estados Unidos", "Canadá"],
    )
    base.update(overrides)
    return StudentSyncBundle(**base)


def test_lead_fields_split_name():
    fields = map_user_to_lead_fields(_bundle())
    assert fields["NAME"] == "Ana"
    assert fields["LAST_NAME"] == "Maria Lopez"


def test_lead_fields_email_phone_shape():
    fields = map_user_to_lead_fields(_bundle())
    assert fields["EMAIL"][0]["VALUE"] == "ana@example.com"
    assert fields["EMAIL"][0]["VALUE_TYPE"] == "WORK"
    assert fields["PHONE"][0]["VALUE_TYPE"] == "MOBILE"


def test_lead_fields_carry_uf_metadata():
    fields = map_user_to_lead_fields(_bundle())
    assert fields["UF_CRM_GH_USER_ID"] == "u-123"
    assert fields["UF_CRM_GH_SCHOOL_ID"] == "s-1"
    assert fields["UF_CRM_GH_PROFILE_HASH"] == "abc123"
    assert fields["UF_CRM_GH_MAPPER_VERSION"] == MAPPER_VERSION
    assert fields["UF_CRM_GH_BUDGET_BAND"] == "medio"
    assert fields["UF_CRM_GH_BUDGET_USD"] == 70000
    assert fields["UF_CRM_GH_CEFR"] == "B2"
    assert "Estados Unidos" in fields["UF_CRM_GH_COUNTRIES"]


def test_lead_fields_status_id_changes_on_advisor_request():
    f1 = map_user_to_lead_fields(_bundle(advisor_requested=False))
    f2 = map_user_to_lead_fields(_bundle(advisor_requested=True))
    assert f1["STATUS_ID"] == "NEW"
    assert f2["STATUS_ID"] == "PROCESSED"


def test_lead_comments_compose_brief():
    fields = map_user_to_lead_fields(_bundle())
    comments = fields["COMMENTS"]
    assert "Perfil consolidado" in comments
    assert "Fortalezas" in comments
    assert "Programas recomendados" in comments
    assert "BSc Computer Science" in comments
    assert "B2" in comments
    assert len(comments) <= 4000


def test_lead_handles_missing_optional_fields():
    bundle = _bundle(
        phone=None,
        recommended_programs=None,
        profile_strengths=None,
        profile_career_paths=None,
    )
    fields = map_user_to_lead_fields(bundle)
    assert "PHONE" not in fields
    assert "Programas recomendados" not in fields["COMMENTS"]


def test_contact_fields_basic():
    fields = map_user_to_contact_fields(_bundle())
    assert fields["NAME"] == "Ana"
    assert fields["TYPE_ID"] == "CLIENT"
    assert fields["EMAIL"][0]["VALUE"] == "ana@example.com"


def test_deal_fields_average_cost():
    fields = map_recommendations_to_deal_fields(_bundle(), lead_id="L-1")
    assert fields["LEAD_ID"] == "L-1"
    assert fields["CURRENCY_ID"] == "USD"
    assert fields["OPPORTUNITY"] == 52500  # avg(60000, 45000)
    assert fields["UF_CRM_GH_PROGRAMS_COUNT"] == 2
    assert "BSc Computer Science" in fields["UF_CRM_GH_PROGRAMS"]


def test_deal_fields_no_programs():
    bundle = _bundle(recommended_programs=[])
    fields = map_recommendations_to_deal_fields(bundle)
    assert fields["OPPORTUNITY"] == 0
    assert fields["UF_CRM_GH_PROGRAMS_COUNT"] == 0


def test_advisor_lead_comment_includes_phone_email():
    comment = map_advisor_lead_comment(_bundle(advisor_brief="Quiere ingeniería con beca."))
    assert "ana@example.com" in comment
    assert "+57 300 1234567" in comment
    assert "ingeniería" in comment


def test_advisor_lead_comment_handles_missing_brief():
    comment = map_advisor_lead_comment(_bundle(advisor_brief=None, phone=None))
    assert "no provisto" in comment
    assert "sin brief" in comment


def test_normalize_inbound_status_known_values():
    assert normalize_inbound_status("NEW") == "new"
    assert normalize_inbound_status("PROCESSED") == "qualified"
    assert normalize_inbound_status("CONVERTED") == "contacted"
    assert normalize_inbound_status("JUNK") == "lost"


def test_normalize_inbound_status_unknown_lowercased():
    assert normalize_inbound_status("CUSTOM_X") == "custom_x"
    assert normalize_inbound_status(None) is None


def test_brief_truncated_at_4000_chars():
    huge = "x" * 10000
    bundle = _bundle(profile_summary=huge)
    fields = map_user_to_lead_fields(bundle)
    assert len(fields["COMMENTS"]) <= 4000
