"""F-003 etapa 1 · scholarships_for_latam · unit tests.

Tests ligeros sobre el modelo + schema. El smoke E2E real corre via
``TestClient`` en QA local.
"""
from __future__ import annotations


def test_program_model_has_scholarships_for_latam_column():
    from app.db.models import Program

    assert hasattr(Program, "scholarships_for_latam")
    col = Program.__table__.c.scholarships_for_latam
    assert col.nullable is True


def test_program_response_includes_scholarships_for_latam():
    from app.schemas.program import ProgramBase

    fields = ProgramBase.model_fields
    assert "scholarships_for_latam" in fields
    f = fields["scholarships_for_latam"]
    assert f.default is None
    # bool | None
    annotation_str = str(f.annotation)
    assert "bool" in annotation_str.lower()


def test_program_update_accepts_scholarships_for_latam():
    from app.schemas.program import ProgramUpdate

    m = ProgramUpdate(scholarships_for_latam=True)
    assert m.scholarships_for_latam is True
    m2 = ProgramUpdate(scholarships_for_latam=False)
    assert m2.scholarships_for_latam is False
    m3 = ProgramUpdate(scholarships_for_latam=None)
    assert m3.scholarships_for_latam is None
