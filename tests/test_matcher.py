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
    assert "Match Score:" in rationale
    assert "Mandatory:" in rationale
    assert "Nice:" in rationale


def test_empty_skills_disqualification():
    """Valida que una vacante sin habilidades técnicas quede descalificada con score 0.0."""
    reqs = JobRequirementsSchema(
        is_remote_or_eligible=True,
        language="es",
        role_category="Data Science",
        min_years_experience=0,
        mandatory_hard_skills=[],
        nice_to_have_skills=[],
        soft_skills_context=[],
    )
    score, hard, soft, rationale, bullets = evaluate_job_match(reqs)
    assert score == 0.0
    assert hard == 0.0
    assert soft == 0.0
    assert bullets == []
    assert "Skills analizadas: 0" in rationale
    assert "Descalificada" in rationale


def test_multidimensional_scoring_boosters():
    """Valida que los boosters de Educación, Idiomas e Industria otorguen scores altos (>= 85%)."""
    reqs = JobRequirementsSchema(
        is_remote_or_eligible=True,
        language="en",
        role_category="Data Science",
        min_years_experience=4,
        mandatory_hard_skills=[
            "Python",
            "M.Sc. in Statistics",
            "English B2",
            "Experiencia en Banca",
            "PyTorch",
            "SQL",
        ],
        nice_to_have_skills=["DataCamp certification"],
        soft_skills_context=["Strong problem-solving skills", "Managing ambiguity"],
    )
    score, hard, soft, rationale, bullets = evaluate_job_match(reqs)
    assert score >= 85.0
    assert hard >= 85.0
    assert soft >= 85.0
    assert len(bullets) > 0
    assert "Match Score:" in rationale


def test_unrelated_vacancies_disqualification():
    """Valida que vacantes totalmente ajenas (Abogado, Chef) queden categóricamente descalificadas (< 20%)."""
    # 1. Vacante Legal / Abogado
    legal_reqs = JobRequirementsSchema(
        is_remote_or_eligible=True,
        language="es",
        role_category="Legal",
        min_years_experience=5,
        mandatory_hard_skills=[
            "Derecho Laboral",
            "Litigio en tribunales",
            "Redacción de demandas y tutelas",
            "Contratos mercantiles",
            "Tarjeta profesional de abogado vigente",
            "Derecho procesal civil",
        ],
        nice_to_have_skills=["Derecho tributario", "Propiedad intelectual"],
        soft_skills_context=["Negociación con sindicatos", "Persuasión en audiencias judiciales"],
    )
    score_legal, hard_legal, _, _, _ = evaluate_job_match(legal_reqs)
    assert score_legal < 20.0
    assert hard_legal == 0.0

    # 2. Vacante Gastronómica / Chef
    chef_reqs = JobRequirementsSchema(
        is_remote_or_eligible=True,
        language="es",
        role_category="Other",
        min_years_experience=4,
        mandatory_hard_skills=[
            "Cocina mediterránea",
            "Manejo de BPM (Buenas Prácticas de Manufactura en alimentos)",
            "Control de costos y mermas en cocina",
            "Pastelería profesional",
            "Técnicas de corte culinario y mise en place",
        ],
        nice_to_have_skills=["Sommelier / Maridaje de vinos"],
        soft_skills_context=["Liderazgo de brigada de cocina", "Trabajo bajo presión en servicio"],
    )
    score_chef, hard_chef, _, _, _ = evaluate_job_match(chef_reqs)
    assert score_chef < 20.0
    assert hard_chef < 10.0