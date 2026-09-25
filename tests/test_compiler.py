"""Pruebas unitarias para el compilador ATS (src/compiler.py).

Valida sanitización de nombres, carga del esquema y regla de no-vacío de
viñetas.
"""

from src.compiler import (
    ATSResumeCompiler,
    determine_country_profile,
    sanitize_filename,
)


def test_determine_country_profile_rules():
    """Valida la asignación del perfil según ubicación geográfica."""
    # 1. Venezuela -> Perfil VE
    assert determine_country_profile(location="Mérida, Venezuela") == "VE"
    assert determine_country_profile(location="Caracas", country_detected="Venezuela") == "VE"
    assert determine_country_profile(target_profile="VE") == "VE"

    # 2. Colombia -> Perfil CO
    assert determine_country_profile(location="Bogotá, Colombia") == "CO"
    assert determine_country_profile(location="Envigado", country_detected="Colombia") == "CO"

    # 3. Fuera de Colombia (US, Remote, Worldwide) -> Perfil CO
    assert determine_country_profile(location="Remote, US") == "CO"
    assert determine_country_profile(location="Madrid, España") == "CO"
    assert determine_country_profile(location="Worldwide Remote") == "CO"


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


def test_compiler_tailored_summary_and_skills():
    """Valida que la inyección de JobRequirements personalice el resumen y el ranking de habilidades técnicas."""
    compiler = ATSResumeCompiler()

    class DummyReqs:
        mandatory_hard_skills = ["PySpark", "Databricks", "Delta Lake"]
        nice_to_have_skills = ["MLflow"]
        language = "en"

    reqs = DummyReqs()

    # 1. Resumen adaptado
    summary = compiler._build_tailored_summary("Lead Data Engineer", reqs, "en", "Base summary")
    assert "Lead Data Engineer" in summary
    assert "PySpark" in summary or "Databricks" in summary

    # 2. Habilidades técnicas adaptadas y reordenadas
    skills_lines = compiler._build_tailored_skills_section(reqs)
    assert len(skills_lines) > 0
    # La categoría Big Data / Cloud Data Engineering debe ser la primera debido al score más alto de coincidencia
    first_line = skills_lines[0].lower()
    assert "big data" in first_line or "databricks" in first_line or "pyspark" in first_line