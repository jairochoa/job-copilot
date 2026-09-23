"""
Módulo de Ingesta Automatizada y Clasificación de Portales ATS (JobSpy).
- Extrae ofertas de LinkedIn, Indeed, Glassdoor y ZipRecruiter.
- Clasifica el tipo de ATS (Greenhouse, Lever, Workday, Taleo, etc.).
- Identifica nivel de fricción (requires_login) y asigna perfil dual (CO/VE).
- Deduplica y persiste en SQLite en modo WAL.
"""

import re
from typing import Any

import requests
from jobspy import scrape_jobs

from src.database import compute_job_hash, insert_job
from src.logger import logger

# Firmas de ATS reconocidos y su nivel de fricción
ATS_PATTERNS = {
    # Ágiles / ATS modernos (baja fricción, sin login forzado obligatorio)
    "greenhouse": (r"boards\.greenhouse\.io|job-boards\.greenhouse\.io", False),
    "lever": (r"jobs\.lever\.co", False),
    "ashby": (r"jobs\.ashbyhq\.com", False),
    "smartrecruiters": (r"jobs\.smartrecruiters\.com|smartrecruiters\.com", False),
    "bamboohr": (r"bamboohr\.com/careers|bamboohr\.com/jobs", False),
    "breezy": (r"breezy\.hr", False),
    "workable": (r"apply\.workable\.com", False),

    # Corporativos pesados / Legacy (alta fricción, requieren registro previo)
    "workday": (r"myworkdayjobs\.com|wd\d+\.myworkdaysite\.com", True),
    "successfactors": (r"successfactors\.(eu|com)|jobs\.sap\.com", True),
    "taleo": (r"taleo\.net", True),
    "icims": (r"icims\.com", True),
    "oracle_cloud": (r"oraclecloud\.com.*job", True),
}


def classify_ats(url: str) -> tuple[str, int]:
    """
    Identifica el tipo de ATS examinando el dominio de la URL.
    Retorna una tupla: (nombre_ats, requires_login_0_o_1).
    """
    if not url:
        return "UNKNOWN", 0

    lower_url = url.lower()
    for ats_name, (pattern, req_login) in ATS_PATTERNS.items():
        if re.search(pattern, lower_url):
            return ats_name.upper(), 1 if req_login else 0

    return "GENERIC_PORTAL", 0


def detect_target_profile(location: str, description: str) -> tuple[str, str]:
    """
    Determina si la oferta corresponde a target local Venezuela (VE)
    o a Colombia / Remoto Internacional (CO).
    Retorna (pais_detectado, codigo_perfil).
    """
    text_corpus = f"{location} {description}".lower()

    if re.search(r"\b(venezuela|merida|caracas|maracaibo|valencia)\b", text_corpus):
        return "Venezuela", "VE"

    if re.search(r"\b(colombia|medellin|bogota|cali|antioquia|envigado)\b", text_corpus):
        return "Colombia", "CO"

    return "Global / Remote", "CO"


def resolve_redirect_url(raw_url: str, timeout: int = 5) -> str:
    """
    Resuelve redirecciones HTTP en URLs cortas o de seguimiento para
    revelar el dominio ATS real detrás de agregadores.
    """
    if not raw_url:
        return raw_url

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.head(raw_url, allow_redirects=True, timeout=timeout, headers=headers)
        return response.url
    except Exception as e:
        logger.debug(f"No se pudo resolver redirección para {raw_url}: {e}")
        return raw_url


def run_job_search(
    search_term: str = "Senior Data Scientist",
    location: str = "Colombia",
    results_wanted: int = 15,
    hours_old: int = 72,
    country_indeed: str = "colombia"
) -> list[dict[str, Any]]:
    """
    Ejecuta el scraping con python-jobspy, procesa metadatos y persiste en SQLite.
    """
    logger.info(f"Iniciando búsqueda de empleos: '{search_term}' en '{location}'...")

    try:
        jobs_df = scrape_jobs(
            site_name=["linkedin", "indeed", "glassdoor"],
            search_term=search_term,
            location=location,
            results_wanted=results_wanted,
            hours_old=hours_old,
            country_indeed=country_indeed,
            is_remote=False
        )
    except Exception as e:
        logger.error(f"Error durante la recolección con JobSpy: {e}", exc_info=True)
        return []

    if jobs_df is None or jobs_df.empty:
        logger.warning(f"No se encontraron ofertas para '{search_term}' en '{location}'.")
        return []

    logger.info(f"JobSpy recuperó {len(jobs_df)} ofertas en crudo. Procesando y clasificando...")

    saved_jobs = []
    for _, row in jobs_df.iterrows():
        title = str(row.get("title") or "").strip()
        company = str(row.get("company") or "").strip()
        raw_location = str(row.get("location") or location).strip()
        job_url = str(row.get("job_url") or row.get("job_url_direct") or "").strip()
        description = str(row.get("description") or "").strip()
        site_source = str(row.get("site") or "unknown").strip()

        if not title or not company or not job_url:
            continue

        # Resolver enlace final y clasificar ATS
        resolved_url = resolve_redirect_url(job_url)
        ats_type, requires_login = classify_ats(resolved_url)

        # Detectar geografía y perfil dual
        country_detected, target_profile = detect_target_profile(raw_location, description)

        # Calcular huella digital
        job_hash = compute_job_hash(
            company=company,
            title=title,
            description_snippet=description[:250]
        )

        job_record = {
            "job_hash": job_hash,
            "title": title,
            "company": company,
            "location": raw_location,
            "country_detected": country_detected,
            "target_profile": target_profile,
            "url": job_url,
            "resolved_url": resolved_url,
            "portal_source": site_source,
            "ats_type": ats_type,
            "requires_login": requires_login,
            "description": description,
            "status": "SCRAPED"
        }

        # Inserción con deduplicación
        if insert_job(job_record):
            saved_jobs.append(job_record)

    logger.info(f"Proceso de ingesta finalizado: {len(saved_jobs)} ofertas nuevas guardadas en la base de datos.")
    return saved_jobs
