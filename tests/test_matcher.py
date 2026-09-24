"""
Pruebas unitarias para el módulo matcher.py (HU-04).
Valida prefiltro booleano ($0), anti-alucinación de viñetas,
calibración de experiencia y parseo Pydantic sin consumo de API.
"""

from unittest.mock import MagicMock, patch

from src.matcher import (
    CompanyBulletsSelection,
    JobMatchEvaluation,
    apply_boolean_prefilter,
    build_evaluation_prompt,
    strip_accents,
)


def test_strip_accents():
    text = "Científico de Datos & Analítica Avanzada"
    assert strip_accents(text) == "Cientifico de Datos & Analitica Avanzada"


def test_boolean_prefilter_accepts_valid_data_roles():
    title = "Senior Data Scientist"
    desc = "Buscamos un especialista con experiencia en Python, Machine Learning y PySpark."
    passes, reason = apply_boolean_prefilter(title, desc)
    assert passes is True
    assert "Aprobada" in reason


def test_boolean_prefilter_rejects_antagonistic_software_roles():
    title = "Lead Python Backend Developer"
    desc = (
        "Desarrollo de microservicios en Django, FastAPI y bases de datos relacionales."
    )
    passes, reason = apply_boolean_prefilter(title, desc)
    assert passes is False
    assert "Descartada por rol antagónico" in reason


def test_boolean_prefilter_rejects_disqualifying_titles():
    title = "Asistente Administrativo"
    desc = "Recepción de correspondencia y atención general."
    passes, reason = apply_boolean_prefilter(title, desc)
    assert passes is False
    assert "Descartada por rol antagónico" in reason


def test_boolean_prefilter_rejects_neutral_jobs_without_data_core():
    title = "Diseñador Gráfico Senior"
    desc = "Manejo de Adobe Photoshop, Illustrator y branding corporativo."
    passes, reason = apply_boolean_prefilter(title, desc)
    assert passes is False
    assert "no contiene términos del núcleo de datos" in reason


def test_pydantic_schema_validation():
    sample_data = {
        "match_score": 85,
        "language_detected": "en",
        "hard_skills_matched": ["Python", "Databricks", "MLflow"],
        "missing_skills_gaps": ["Snowflake"],
        "tailored_headline": "Senior Data Scientist | Machine Learning & Statistical Modeling",
        "tailored_summary": "Data Scientist with 8+ years of experience leading ML initiatives...",
        "selected_bullets": [
            CompanyBulletsSelection(
                company_id="comp_1", bullet_ids=["comp_1_b1", "comp_1_b2"]
            )
        ],
        "strategic_fit_rationale": "Strong fit for statistical modeling and cloud deployments.",
    }
    eval_model = JobMatchEvaluation(**sample_data)
    assert eval_model.match_score == 85
    assert eval_model.language_detected == "en"
    assert len(eval_model.selected_bullets) == 1
    assert eval_model.selected_bullets[0].company_id == "comp_1"


def test_build_evaluation_prompt_contains_anti_overqualification_rule():
    dummy_cv = {
        "personal_info": {"name": "Test Candidate"},
        "education": [],
        "certifications": [],
        "technical_skills": {},
        "experience": [],
    }
    prompt = build_evaluation_prompt(
        "Senior Data Scientist", "Tech Corp", "Data role", dummy_cv
    )

    assert 'NUNCA menciones "15+", "20+"' in prompt
    assert "8+ years" in prompt or "10+ years" in prompt


def test_evaluate_single_job_mock():
    """Test unitario mockeando requests.post y load_master_cv."""
    from src import matcher

    fake_master_cv = {
        "personal_info": {"name": "Test Candidate"},
        "education": [],
        "technical_skills": {},
        "experience": []
    }

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "candidates": [{
            "content": {
                "parts": [{
                    "text": '''{
                        "match_score": 85,
                        "language": "es",
                        "hard_skills_matched": ["Python", "SQL"],
                        "missing_skills_gaps": [],
                        "tailored_headline": "Senior Data Scientist",
                        "tailored_summary": "Magíster en Estadística con 8+ años de experiencia.",
                        "selected_bullets": [],
                        "strategic_fit_rationale": "Buen encaje técnico."
                    }'''
                }]
            }
        }]
    }

    with patch("src.matcher.load_master_cv", return_value=fake_master_cv), patch("requests.post", return_value=fake_response):
        job = {"title": "Data Scientist", "company": "Test Co", "description": "Python, SQL"}
        result = matcher.evaluate_single_job(job, api_key="fake_key")
        assert result is not None
        assert result.match_score == 85

