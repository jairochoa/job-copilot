"""Pruebas unitarias para el extractor taxonómico (src/extractor.py)."""

from src.extractor import detect_job_language


def test_detect_job_language_spanish_description():
    desc = """
    En Liberty Latin America (LLA) buscamos un Senior Data Scientist Remoto con más de 4 años de experiencia.
    ¿Qué proyectos liderarás y desarrollarás?
    - Optimización de CVM y Recomendación: Diseño y despliegue de modelos de recomendación.
    - Dominio avanzado de Python y SQL.
    """
    # Incluso si el LLM devuelve 'en', el detector determinista debe identificar español ('es')
    lang = detect_job_language(desc, llm_language="en")
    assert lang == "es"


def test_detect_job_language_english_description():
    desc = """
    We are looking for a Senior Data Scientist in Remote US.
    Requirements:
    - 4+ years of hands-on Machine Learning experience
    - Proficiency in Python, PySpark, and SQL
    """
    lang = detect_job_language(desc, llm_language="en")
    assert lang == "en"
