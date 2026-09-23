"""
Módulo de Evaluación Semántica y Matching.
HU-04 / Actividad 4.1: Prefiltro booleano por reglas duras locales (costo $0).
- Normalización Unicode (soporte bilingüe ES/EN).
- Descarte estricto de roles de desarrollo de software puro (Python Dev, Backend Dev).
- Enfoque específico en Data Science, Analytics, Machine Learning y Estadística.
"""

import re
import unicodedata
from typing import Tuple
from src.logger import logger
from src.database import get_db_connection


def strip_accents(text: str) -> str:
    """Elimina tildes y diacríticos para hacer el matching insensible a acentos."""
    nfkd_form = unicodedata.normalize('NFKD', text)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])


# Términos obligatorios del núcleo profesional (Data, ML, Estadística, Analytics)
CORE_POSITIVE_PATTERNS = [
    r"\bdata\s+(&|and|y)?\s*analytics\b",
    r"\b(data\s+scientist|cientific[ao]\s+de\s+datos)\b",
    r"\b(data\s+analyst|analista\s+de\s+datos)\b",
    r"\b(data\s+engineer|ingenier[ao]\s+de\s+datos)\b",
    r"\b(analytics|analitica)\b",
    r"\bmachine\s+learning\b",
    r"\b(aprendizaje\s+automatico|modelos\s+predictivos)\b",
    r"\b(ai|ia)\s+(engineer|developer|consultant)\b",
    r"\bapplied\s+ai\b",
    r"\b(llm|nlp|vision\s+artificial|computer\s+vision)\b",
    r"\b(deep\s+learning|pytorch|scikit-learn|xgboost|lightgbm)\b",
    r"\b(estadistic[ao]|statistic(s|ian)?)\b",
    r"\b(databricks|pyspark|delta\s+lake|microsoft\s+fabric)\b",
    r"\bpower\s*bi\b",
    r"\bbusiness\s+intelligence\b"
]

# Términos antagónicos que provocan descarte inmediato (desarrollo puro, soporte, QA)
DISQUALIFYING_PATTERNS = [
    # Desarrollo de software backend / web (incluso en Python)
    r"\b(lead|senior|junior|staff)?\s*python\s+(developer|engineer|software\s+engineer|backend)\b",
    r"\b(java|dotnet|\.net|c#|golang|rust)\s+(developer|backend|engineer)\b",
    r"\bphp(\s+developer)?\b",
    r"\bfrontend\s+(developer|engineer|react|angular|vue)\b",
    r"\bfullstack\s+(developer|engineer)\b",
    r"\bsoftware\s+engineer\b",
    r"\bqa\s+(automation|tester|manual)\b",
    r"\b(scrum\s+master|product\s+owner)\b",
    r"\b(televentas|call\s+center|asistente\s+administrativo)\b"
]


def apply_boolean_prefilter(title: str, description: str) -> Tuple[bool, str]:
    """
    Evalúa si una vacante supera las reglas duras locales sin invocar LLM.
    Descarta roles de desarrollo de software para enfocarse en datos/estadística.
    """
    raw_title = title.lower()
    raw_corpus = f"{title}\n{description}".lower()
    clean_title = strip_accents(raw_title)
    text_corpus = strip_accents(raw_corpus)

    # 1. Comprobar términos descalificantes prioritariamente en el título
    for neg_pattern in DISQUALIFYING_PATTERNS:
        match_title = re.search(neg_pattern, clean_title)
        if match_title:
            return False, f"Descartada por rol de ingeniería de software/antagónico en título: '{match_title.group(0)}'"

    # 2. Comprobar términos antagónicos en la descripción general
    for neg_pattern in DISQUALIFYING_PATTERNS:
        match_desc = re.search(neg_pattern, text_corpus)
        if match_desc and not any(re.search(p, clean_title) for p in CORE_POSITIVE_PATTERNS):
            return False, f"Descartada por término antagónico detectado: '{match_desc.group(0)}'"

    # 3. Comprobar presencia de términos del núcleo profesional de datos/analítica
    matched_positives = []
    for pos_pattern in CORE_POSITIVE_PATTERNS:
        match = re.search(pos_pattern, text_corpus)
        if match:
            matched_positives.append(match.group(0))

    if not matched_positives:
        return False, "Descartada: no contiene términos del núcleo de ciencia de datos/analítica."

    return True, f"Aprobada para LLM. Términos detectados: {', '.join(set(matched_positives))}"


def run_heuristic_filter_batch() -> int:
    """
    Escanea las vacantes en estado 'SCRAPED' en SQLite.
    Las que no superen el prefiltro pasan a 'FILTERED_OUT' con match_score 0.
    Retorna el conteo de vacantes descartadas.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT job_hash, title, company, description FROM job_applications WHERE status = 'SCRAPED';"
        )
        pending_jobs = [dict(row) for row in cursor.fetchall()]

    if not pending_jobs:
        logger.info("No hay vacantes pendientes en estado 'SCRAPED' para evaluar.")
        return 0

    logger.info(f"Aplicando prefiltro booleano a {len(pending_jobs)} vacantes...")
    filtered_out_count = 0
    approved_count = 0

    for job in pending_jobs:
        passes, reason = apply_boolean_prefilter(job["title"], job["description"])

        if not passes:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE job_applications
                    SET status = 'FILTERED_OUT',
                        match_score = 0,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE job_hash = ?;
                    """,
                    (job["job_hash"],),
                )
            logger.info(f"🚫 [{job['company']} - {job['title']}] -> {reason}")
            filtered_out_count += 1
        else:
            logger.info(f"✅ [{job['company']} - {job['title']}] -> {reason}")
            approved_count += 1

    logger.info(
        f"Prefiltro completado: {approved_count} vacantes listas para Gemini, "
        f"{filtered_out_count} descartadas a costo $0."
    )
    return filtered_out_count
