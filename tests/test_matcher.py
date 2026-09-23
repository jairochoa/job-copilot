"""
Tests unitarios para el prefiltro booleano de vacantes (Actividad 4.1).
"""

from src.matcher import apply_boolean_prefilter


def test_prefilter_accepts_data_science_core():
    """Valida que ofertas en inglés con el stack de datos sean aprobadas."""
    title = "Senior Data Scientist"
    desc = "Buscamos experto en Python, Machine Learning y Databricks."
    passes, reason = apply_boolean_prefilter(title, desc)
    assert passes is True
    assert "Aprobada" in reason


def test_prefilter_accepts_spanish_with_accents():
    """Valida que ofertas en español con tildes sean reconocidas correctamente."""
    title = "Científico de Datos – Analítica"
    desc = "Construcción de modelos predictivos y analítica avanzada para el sector asegurador."
    passes, reason = apply_boolean_prefilter(title, desc)
    assert passes is True
    assert "Aprobada" in reason


def test_prefilter_rejects_pure_python_developer():
    """Valida el descarte de roles de desarrollo puro de software en Python."""
    title = "Lead Python Developer"
    desc = "Diseño de APIs con FastAPI, arquitectura de microservicios y SQL."
    passes, reason = apply_boolean_prefilter(title, desc)
    assert passes is False
    assert "software" in reason.lower() or "antagónico" in reason.lower()


def test_prefilter_rejects_antagonistic_roles():
    """Valida descarte de Java u otras tecnologías no deseadas."""
    title = "Java Backend Developer"
    desc = "Desarrollo de microservicios con Spring Boot y SQL."
    passes, reason = apply_boolean_prefilter(title, desc)
    assert passes is False
    assert "antagónico" in reason.lower()
