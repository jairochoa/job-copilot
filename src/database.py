"""
Módulo de Persistencia y Gestión Transaccional con SQLite.
- SQLite en modo WAL (Write-Ahead Logging) para concurrencia limpia.
- Algoritmo de deduplicación SHA-256 normalizado (compute_job_hash).
- Esquema relacional para control de estados del embudo de postulaciones.
"""

import hashlib
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from src.logger import logger

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "jobs.db"


def compute_job_hash(company: str, title: str, description_snippet: str) -> str:
    """
    Genera un hash SHA-256 normalizado para evitar postulaciones o ingestas duplicadas.
    Limpia sufijos legales, puntuación y espacios en blanco redundantes.
    """
    clean_company = re.sub(
        r"\b(sas|s\.a\.s|inc|corp|llc|ltd|gmbh)\b", "", company.lower()
    )
    clean_company = re.sub(r"[^\w\s]", "", clean_company).strip()
    clean_company = re.sub(r"\s+", " ", clean_company)

    clean_title = re.sub(r"[^\w\s]", "", title.lower()).strip()
    clean_title = re.sub(r"\s+", " ", clean_title)

    clean_desc = re.sub(r"\s+", " ", description_snippet.lower()).strip()[:250]

    raw_signature = f"{clean_company}|{clean_title}|{clean_desc}"
    return hashlib.sha256(raw_signature.encode("utf-8")).hexdigest()


@contextmanager
def get_db_connection():
    """Context manager para conexiones SQLite con modo WAL y manejo transaccional."""
    conn = sqlite3.connect(str(DB_PATH), timeout=20.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Error en transacción de base de datos: {e}", exc_info=True)
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Inicializa las tablas e índices relacionales si no existen."""
    ddl_table = """
    CREATE TABLE IF NOT EXISTS job_applications (
        job_hash TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        company TEXT NOT NULL,
        location TEXT,
        country_detected TEXT,
        target_profile TEXT DEFAULT 'CO', -- 'CO' o 'VE'
        url TEXT NOT NULL,
        resolved_url TEXT,
        portal_source TEXT,               -- 'linkedin', 'indeed', 'glassdoor', 'manual'
        ats_type TEXT DEFAULT 'UNKNOWN',  -- 'greenhouse', 'workday', 'lever', etc.
        requires_login INTEGER DEFAULT 0, -- 1 si exige login complejo, 0 si es ágil
        description TEXT,
        
        -- Métricas y evaluación
        status TEXT DEFAULT 'SCRAPED',    -- SCRAPED, FILTERED_OUT, SCORED, APPLIED, REJECTED, INTERVIEW
        match_score INTEGER DEFAULT 0,
        score_rationale TEXT,
        selected_bullet_ids TEXT,         -- JSON string con los IDs seleccionados
        tailored_summary TEXT,
        cover_letter TEXT,
        
        -- Salidas generadas
        pdf_path TEXT,
        docx_path TEXT,
        
        -- Auditoría
        scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        applied_at TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    indices = [
        "CREATE INDEX IF NOT EXISTS idx_jobs_status ON job_applications(status);",
        "CREATE INDEX IF NOT EXISTS idx_jobs_score ON job_applications(match_score);",
        "CREATE INDEX IF NOT EXISTS idx_jobs_ats ON job_applications(ats_type);",
    ]

    with get_db_connection() as conn:
        conn.execute(ddl_table)
        for idx in indices:
            conn.execute(idx)
        logger.info("Base de datos SQLite inicializada exitosamente en modo WAL.")


def insert_job(job_data: dict[str, Any]) -> bool:
    """
    Inserta una vacante si no existe por hash.
    Retorna True si fue insertada, False si ya existía (duplicada).
    """
    job_hash = job_data.get("job_hash") or compute_job_hash(
        company=job_data["company"],
        title=job_data["title"],
        description_snippet=job_data.get("description", "")[:250],
    )
    job_data["job_hash"] = job_hash

    query = """
    INSERT INTO job_applications (
        job_hash, title, company, location, url, portal_source,
        description, ats_type, requires_login, status
    ) VALUES (
        :job_hash, :title, :company, :location, :url, :portal_source,
        :description, :ats_type, :requires_login, :status
    ) ON CONFLICT(job_hash) DO NOTHING;
    """
    with get_db_connection() as conn:
        cursor = conn.execute(query, job_data)
        inserted = cursor.rowcount > 0
        if inserted:
            logger.debug(
                f"Vacante insertada: {job_data['title']} en {job_data['company']} ({job_hash[:8]}...)"
            )
        else:
            logger.debug(
                f"Vacante duplicada descartada: {job_data['title']} en {job_data['company']}"
            )
        return inserted
