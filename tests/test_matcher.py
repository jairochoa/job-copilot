"""
Tests unitarios para el prefiltro booleano y evaluación con Gemini (HU-04).
"""

from unittest.mock import MagicMock, patch

from src.matcher import (
    JobMatchEvaluation,
    apply_boolean_prefilter,
    evaluate_single_job,
)


def test_prefilter_accepts_data_science_core():
    title = "Senior Data Scientist"
    desc = "Buscamos experto en Python, Machine Learning y Databricks."
    passes, reason = apply_boolean_prefilter(title, desc)
    assert passes is True
    assert "Aprobada" in reason


def test_prefilter_accepts_spanish_with_accents():
    title = "Científico de Datos – Analítica"
    desc = "Construcción de modelos predictivos y analítica avanzada para el sector asegurador."
    passes, reason = apply_boolean_prefilter(title, desc)
    assert passes is True
    assert "Aprobada" in reason


def test_prefilter_rejects_pure_python_developer():
    title = "Lead Python Developer"
    desc = "Diseño de APIs con FastAPI, arquitectura de microservicios y SQL."
    passes, reason = apply_boolean_prefilter(title, desc)
    assert passes is False
    assert "antagónico" in reason.lower() or "software" in reason.lower()


def test_job_match_evaluation_schema():
    """Valida que el esquema Pydantic acepte datos válidos sin diccionarios no tipados."""
    valid_data = {
        "match_score": 88,
        "language_detected": "es",
        "hard_skills_matched": ["Python", "Databricks", "Machine Learning"],
        "missing_skills_gaps": ["Snowflake"],
        "tailored_headline": "Senior Data Scientist | Applied AI & MLOps",
        "tailored_summary": "Especialista con más de 10 años de experiencia...",
        "selected_bullets": [{"company_id": "experiencia_1", "bullet_ids": ["b1", "b2"]}],
        "strategic_fit_rationale": "Sólido encaje en modelado predictivo.",
    }
    model = JobMatchEvaluation(**valid_data)
    assert model.match_score == 88
    assert model.language_detected == "es"


@patch("src.matcher.genai.Client")
def test_evaluate_single_job_mock(mock_client_class):
    """Verifica que evaluate_single_job procese la respuesta simulada."""
    mock_instance = MagicMock()
    mock_client_class.return_value = mock_instance

    mock_response = MagicMock()
    mock_response.text = (
        '{"match_score": 92, "language_detected": "es", '
        '"hard_skills_matched": ["Python"], "missing_skills_gaps": [], '
        '"tailored_headline": "Data Scientist Senior", '
        '"tailored_summary": "Resumen técnico...", '
        '"selected_bullets": [{"company_id": "exp_1", "bullet_ids": ["b1"]}], '
        '"strategic_fit_rationale": "Ajuste ideal."}'
    )
    mock_instance.models.generate_content.return_value = mock_response

    sample_job = {
        "job_hash": "dummy_hash_123",
        "title": "Data Scientist",
        "company": "Tech Corp",
        "description": "Python, Machine Learning y Estadística.",
    }

    result = evaluate_single_job(sample_job, api_key="test_key")
    assert result is not None
    assert result.match_score == 92
    assert result.language_detected == "es"
