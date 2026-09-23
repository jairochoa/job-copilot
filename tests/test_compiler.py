"""
Pruebas unitarias para el compilador ATS (HU-05).
Valida preparación de contexto, resolución bilingüe y saneamiento de nombres.
"""

from src.compiler import prepare_cv_context, sanitize_filename


def test_sanitize_filename():
    raw_name = "Bancolombia S.A.S. / Tech: Data Lead"
    cleaned = sanitize_filename(raw_name)
    assert "/" not in cleaned
    assert ":" not in cleaned
    assert "Bancolombia" in cleaned


def test_prepare_cv_context_bilingual_selection():
    dummy_job = {
        "language": "es",
        "tailored_headline": "Científico de Datos Senior",
        "tailored_summary": "Especialista en IA...",
        "selected_bullet_ids": '{"freelance_consulting": ["exp_cons_b1"]}',
    }
    dummy_master = {
        "profiles": {
            "CO": {
                "full_name": "Jairo Julián Ochoa",
                "location": "Envigado, Colombia",
                "phone": "+57 350 764 3501",
                "email": "jairoochoa@gmail.com",
                "linkedin": "https://linkedin.com/in/jjochoa",
                "github": "https://github.com/jairochoa",
                "professional_title": {
                    "es": "Estadístico Senior",
                    "en": "Senior Statistician",
                },
            }
        },
        "education": [
            {
                "degree": {
                    "es": "Maestría en Estadística",
                    "en": "Master in Statistics",
                },
                "institution": "UNAL",
                "period": {"es": "2018", "en": "2018"},
            }
        ],
        "certifications": [],
        "skills": {"soft_skills": ["Liderazgo técnico", "Pensamiento crítico"]},
        "languages": [
            {
                "name": {"es": "Español", "en": "Spanish"},
                "proficiency": {"es": "Nativo", "en": "Native"},
            },
            {
                "name": {"es": "Inglés", "en": "English"},
                "proficiency": {"es": "Profesional", "en": "Professional"},
            },
        ],
        "experience_bullets_pool": [
            {
                "id": "exp_cons_b1",
                "company": "Consultoría",
                "standard_role": {"es": "Consultor Senior", "en": "Senior Consultant"},
                "period": "Ene 2023 - Actualidad",
                "text": {"es": "Viñeta en español", "en": "English bullet"},
            }
        ],
    }
    context = prepare_cv_context(dummy_job, dummy_master)
    assert context["language"] == "es"
    assert context["personal"]["full_name"] == "Jairo Julián Ochoa"
    assert context["tailored_headline"] == "Científico de Datos Senior"
    assert context["experience"][0]["bullets"][0] == "Viñeta en español"
    assert len(context["languages_spoken"]) == 2
    assert "Liderazgo & Metodologías" in context["skills"]
