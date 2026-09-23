"""
Tests unitarios para la clasificación de ATS y lógica de scraping.
"""

from src.scraper import classify_ats, detect_target_profile


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
    # Caso Venezuela
    pais_ve, perfil_ve = detect_target_profile("Mérida, Venezuela", "Vacante presencial de analítica")
    assert perfil_ve == "VE"
    assert pais_ve == "Venezuela"

    # Caso Colombia / Remoto
    pais_co, perfil_co = detect_target_profile("Medellín, Colombia", "Python, SQL, Databricks")
    assert perfil_co == "CO"
    assert pais_co == "Colombia"
