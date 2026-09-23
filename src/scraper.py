"""
Módulo de Ingesta Automatizada y Clasificación de Portales ATS (JobSpy).
- Parámetros dinámicos y desacoplados sin valores fijos en el código fuente.
- Detección de portales compatibles según región geográfica.
- Clasificación de ATS y cálculo de huella digital única (SHA-256).
- Persistencia tolerante a fallos en SQLite en modo WAL.
"""

import re
from typing import Any

import pandas as pd
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

# Regiones donde Glassdoor y ZipRecruiter operan nativamente
NORTH_AMERICA_EUROPE = {
    "united states", "usa", "us", "united kingdom", "uk",
    "canada", "australia", "germany", "france", "netherlands"
}


def classify_ats(url: str) -> tuple[str, int]:
    """Identifica el tipo de ATS examinando el dominio de la URL."""
    if not url:
        return "UNKNOWN", 0

    lower_url = url.lower()
    for ats_name, (pattern, req_login) in ATS_PATTERNS.items():
        if re.search(pattern, lower_url):
            return ats_name.upper(), 1 if req_login else 0

    return "GENERIC_PORTAL", 0


def detect_target_profile(location: str, description: str) -> tuple[str, str]:
    """Determina si la oferta corresponde a target local VE o CO/Global."""
    text_corpus = f"{location} {description}".lower()

    if re.search(r"\b(venezuela|merida|caracas|maracaibo|valencia)\b", text_corpus):
        return "Venezuela", "VE"

    if re.search(r"\b(colombia|medellin|bogota|cali|antioquia|envigado)\b", text_corpus):
        return "Colombia", "CO"

    return "Global / Remote", "CO"


def resolve_redirect_url(raw_url: str, timeout: int = 5) -> str:
    """Resuelve redirecciones HTTP en URLs para obtener el ATS real."""
    if not raw_url:
        return raw_url

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        }
        response = requests.head(
            raw_url, allow_redirects=True, timeout=timeout, headers=headers
        )
        return response.url
    except requests.RequestException as e:
        logger.debug(f"No se pudo resolver redirección para {raw_url}: {e}")
        return raw_url


def resolve_sites_for_location(
    location: str, requested_sites: list[str] | None = None
) -> list[str]:
    """Filtra y devuelve sitios compatibles según la región geográfica."""
    default_sites = requested_sites or [
        "linkedin", "indeed", "glassdoor", "zip_recruiter", "google",
    ]
    loc_lower = location.lower().strip()
    is_na_eu = any(c in loc_lower for c in NORTH_AMERICA_EUROPE)

    resolved = []
    for site in default_sites:
        site_name = site.lower().strip()
        if site_name in ("glassdoor", "zip_recruiter") and not is_na_eu:
            logger.debug(
                f"Excluyendo {site_name}: no cuenta con soporte regional para '{location}'."
            )
            continue
        resolved.append(site_name)

    return resolved


def run_job_search(
    search_term: str,
    location: str,
    results_wanted: int = 15,
    hours_old: int = 72,
    country_indeed: str | None = None,
    sites: list[str] | None = None,
    is_remote: bool = False,
) -> list[dict[str, Any]]:
    """Ejecuta el scraping dinámico y persiste los resultados en SQLite."""
    logger.info(f"Iniciando búsqueda de empleos: '{search_term}' en '{location}'...")

    active_sites = resolve_sites_for_location(
        location=location, requested_sites=sites
    )
    logger.info(f"Portales habilitados para la consulta: {active_sites}")

    collected_dfs = []
    for site in active_sites:
        try:
            logger.info(f"Consultando portal: {site}...")
            scrape_kwargs: dict[str, Any] = {
                "site_name": [site],
                "search_term": search_term,
                "location": location,
                "results_wanted": results_wanted,
                "hours_old": hours_old,
                "is_remote": is_remote,
            }
            if country_indeed:
                scrape_kwargs["country_indeed"] = country_indeed

            df = scrape_jobs(**scrape_kwargs)
            if df is not None and not df.empty:
                collected_dfs.append(df)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Error consultando portal {site}: {e}")

    if not collected_dfs:
        logger.warning(f"No se obtuvieron resultados para '{search_term}' en '{location}'.")
        return []

    jobs_df = pd.concat(collected_dfs, ignore_index=True)
    logger.info(f"JobSpy recuperó {len(jobs_df)} ofertas en total. Procesando y deduplicando...")

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

        resolved_url = resolve_redirect_url(job_url)
        ats_type, requires_login = classify_ats(resolved_url)
        country_detected, target_profile = detect_target_profile(
            raw_location, description
        )

        job_hash = compute_job_hash(
            company=company,
            title=title,
            description_snippet=description[:250],
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
            "status": "SCRAPED",
        }

        if insert_job(job_record):
            saved_jobs.append(job_record)

    logger.info(
        f"Proceso finalizado: {len(saved_jobs)} ofertas nuevas registradas en la base de datos."
    )
    return saved_jobs
