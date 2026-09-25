"""Pruebas unitarias para el compilador ATS (src/compiler.py).

Valida sanitización de nombres, carga del esquema y regla de no-vacío de
viñetas.
"""

from src.compiler import ATSResumeCompiler, sanitize_filename


def test_sanitize_filename():
    raw = 'Senior Data Scientist: Remote / LatAm? <Yes> *Test* "AI"'
    cleaned = sanitize_filename(raw)
    for char in [":", "/", "<", ">", '"', "*", "?"]:
        assert char not in cleaned


def test_compiler_initialization_and_context():
    compiler = ATSResumeCompiler()
    assert compiler.cv_data is not None
    assert "profiles" in compiler.cv_data
    assert "metadata" in compiler.cv_data
    assert "CO" in compiler.cv_data["profiles"]
    assert "experience_bullets_pool" in compiler.cv_data
    assert len(compiler.cv_data["experience_bullets_pool"]) > 0


def test_compiler_no_empty_roles_rule():
    compiler = ATSResumeCompiler()
    pool = compiler.cv_data.get("experience_bullets_pool", [])

    companies = list({b.get("company") for b in pool if b.get("company")})
    assert len(companies) > 0

    for company in companies:
        bullets = compiler._select_bullets_for_role(
            company=company, selected_ids=[], max_bullets=3
        )
        # Regla de no-vacío: debe devolver al menos una viñeta para la empresa
        assert len(bullets) >= 1

        # Verificar ordenamiento ascendente por default_priority
        priorities = [b.get("default_priority", 99) for b in bullets]
        assert priorities == sorted(priorities)