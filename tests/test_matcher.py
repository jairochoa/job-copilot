"""Pruebas unitarias para el motor de matching semántico RAG local."""

from src.extractor import JobRequirementsSchema
from src.matcher import evaluate_job_match


def test_territorial_gatekeeper_disqualification():
    reqs = JobRequirementsSchema(
        is_remote_or_eligible=False,
        ineligibility_reason="Requires active US Security Clearance and on-site presence.",
        language="en",
        role_category="Data Science",
        min_years_experience=3,
        mandatory_hard_skills=["Python", "SQL"],
        nice_to_have_skills=[],
        soft_skills_context=[],
    )
    score, hard, soft, rationale, bullets = evaluate_job_match(reqs)
    assert score == 0.0
    assert hard == 0.0
    assert soft == 0.0
    assert "Excluida territorialmente" in rationale
    assert bullets == []


def test_hybrid_matching_scoring_logic():
    reqs = JobRequirementsSchema(
        is_remote_or_eligible=True,
        language="es",
        role_category="Data Science",
        min_years_experience=4,
        mandatory_hard_skills=["Python", "Machine Learning", "Estadística"],
        nice_to_have_skills=["PySpark"],
        soft_skills_context=["Liderazgo técnico", "Comunicación"],
    )
    score, hard, soft, rationale, bullets = evaluate_job_match(reqs)
    assert 0.0 <= score <= 100.0
    assert 0.0 <= hard <= 100.0
    assert 0.0 <= soft <= 100.0
    assert len(bullets) > 0
    assert "Match Score:" in rationale
    assert "Mandatory:" in rationale
    assert "Nice:" in rationale