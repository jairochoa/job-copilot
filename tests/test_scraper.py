"""
Tests unitarios para la clasificación de ATS y lógica de scraping.
"""

from src.scraper import classify_ats, detect_target_profile, resolve_sites_for_location


def test_classify_ats_modern_agile():
    """Valida reconocimiento de ATS ágiles con requires_login = 0."""
    url_greenhouse = "https://boards.greenhouse.io/databricks/jobs/123456"
    ats, req_login = classify_ats(url_greenhouse)
    assert ats == "GREENHOUSE"
    assert req_login == 0

    url_lever = "https://jobs.lever.co/anthropic/abcdef"
    ats_lev, req_login_lev = classify_ats(url_lever)
    assert ats_lev == "LEVER"
    assert req_login_lev == 0


def test_classify_ats_corporate_heavy():
    """Valida reconocimiento de ATS pesados con requires_login = 1."""
    url_workday = "https://bancolombia.wd3.myworkdayjobs.com/Bancolombia/job/Senior-DS"
    ats, req_login = classify_ats(url_workday)
    assert ats == "WORKDAY"
    assert req_login == 1


def test_detect_target_profile():
    """Valida la asignación automática del perfil CO o VE."""
    pais_ve, perfil_ve = detect_target_profile(
        "Mérida, Venezuela", "Vacante presencial de analítica"
    )
    assert perfil_ve == "VE"
    assert pais_ve == "Venezuela"

    pais_co, perfil_co = detect_target_profile(
        "Medellín, Colombia", "Python, SQL, Databricks"
    )
    assert perfil_co == "CO"
    assert pais_co == "Colombia"


def test_resolve_sites_filtering():
    """Valida que Glassdoor y ZipRecruiter no se invoquen para regiones no soportadas."""
    sites_co = resolve_sites_for_location("Colombia")
    assert "linkedin" in sites_co
    assert "indeed" in sites_co
    assert "glassdoor" not in sites_co
    assert "zip_recruiter" not in sites_co

    sites_us = resolve_sites_for_location("United States")
    assert "glassdoor" in sites_us
    assert "zip_recruiter" in sites_us
