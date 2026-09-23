"""
Pruebas unitarias para el compilador ATS (HU-05).
Valida preparación de contexto, saneamiento de nombres y generación sin headless real.
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
        "personal_info": {"name": "Jairo Julián Ochoa"},
        "education": [
            {
                "degree_es": "Maestría en Estadística",
                "institution": "UNAL",
                "year": "2018",
            }
        ],
        "certifications": [],
        "technical_skills": {},
        "experience": [
            {
                "company_id": "freelance_consulting",
                "company": "Consultoría",
                "title_formula_a": "Senior Consultant",
                "location": "Remoto",
                "period_es": "2023 - Presente",
                "period_en": "2023 - Present",
                "bullets": [
                    {
                        "id": "exp_cons_b1",
                        "text_es": "Viñeta en español",
                        "text_en": "English bullet",
                    }
                ],
            }
        ],
    }
    context = prepare_cv_context(dummy_job, dummy_master)
    assert context["language"] == "es"
    assert context["tailored_headline"] == "Científico de Datos Senior"
    assert context["experience"][0]["selected_bullets"][0] == "Viñeta en español"
