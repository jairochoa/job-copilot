"""
Módulo de persistencia y migraciones para SQLite (data/jobs.db).
Maneja la inicialización, migraciones seguras y consultas del pipeline.
"""

import json
import logging
import os
import sqlite3
import hashlib
from typing import Any, Dict, List, Optional

from src.config import settings

logger = logging.getLogger(__name__)


def get_db_connection() -> sqlite3.Connection:
    """Crea y retorna una conexión a la base de datos SQLite con row_factory Row."""
    settings.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(settings.DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_and_migrate_db() -> None:
    """
    Inicializa la tabla job_applications si no existe y aplica migraciones
    idempotentes (ALTER TABLE) para soportar el matching híbrido y RAG.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Crear tabla base si no existe
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS job_applications (
            id TEXT PRIMARY KEY,
            title TEXT,
            company TEXT,
            location TEXT,
            url TEXT UNIQUE,
            description TEXT,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'PENDING',
            match_score REAL DEFAULT 0.0,
            score_rationale TEXT DEFAULT '',
            cv_pdf_path TEXT DEFAULT '',
            cv_docx_path TEXT DEFAULT ''
        )
    """
    )
    conn.commit()

    # 2. Inspeccionar columnas existentes para migración idempotente
    cursor.execute("PRAGMA table_info(job_applications)")
    existing_cols = {row["name"] for row in cursor.fetchall()}

    # 3. Definir nuevas columnas para HU-03 (Matching híbrido y selección Top K)
    new_columns = {
        "hard_match_score": "REAL DEFAULT 0.0",
        "soft_match_score": "REAL DEFAULT 0.0",
        "raw_requirements_json": "TEXT DEFAULT '{}'",
        "top_bullets_json": "TEXT DEFAULT '[]'",
        "is_remote_eligible": "INTEGER DEFAULT 1",
        "cv_docx_path": "TEXT DEFAULT ''",
        "cv_pdf_path": "TEXT DEFAULT ''",
        "job_hash": "TEXT DEFAULT ''",
        "target_profile": "TEXT DEFAULT ''",
    }

    for col_name, col_type in new_columns.items():
        if col_name not in existing_cols:
            logger.info(
                f"Migrando base de datos: Agregando columna '{col_name}'..."
            )
            cursor.execute(
                f"ALTER TABLE job_applications ADD COLUMN {col_name} {col_type}"
            )

    # 4. Crear índice único para job_hash para desduplicación estricta por SHA
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_job_applications_hash ON job_applications(job_hash) WHERE job_hash IS NOT NULL AND job_hash != ''"
    )

    conn.commit()
    conn.close()
    logger.info("Base de datos SQLite verificada y migrada exitosamente.")


def update_job_evaluation(
    job_id: str,
    match_score: float,
    hard_score: float,
    soft_score: float,
    rationale: str,
    raw_requirements: Dict[str, Any],
    top_bullets: List[str],
    is_remote_eligible: bool = True,
) -> None:
    """Actualiza la evaluación completa de una vacante tras el matching vectorial."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE job_applications
        SET match_score = ?,
            hard_match_score = ?,
            soft_match_score = ?,
            score_rationale = ?,
            raw_requirements_json = ?,
            top_bullets_json = ?,
            is_remote_eligible = ?,
            status = CASE WHEN ? >= ? THEN 'QUALIFIED' ELSE 'DISQUALIFIED' END
        WHERE id = ? OR job_hash = ? OR rowid = ?
    """,
        (
            match_score,
            hard_score,
            soft_score,
            rationale,
            json.dumps(raw_requirements, ensure_ascii=False),
            json.dumps(top_bullets, ensure_ascii=False),
            1 if is_remote_eligible else 0,
            match_score,
            settings.MIN_QUALIFIED_SCORE,
            job_id,
            job_id,
            job_id if str(job_id).isdigit() else -1,
        ),
    )
    conn.commit()
    conn.close()


def update_compiled_paths(
    job_id: str, pdf_path: str, docx_path: str
) -> None:
    """Actualiza las rutas de los CVs compilados para una vacante calificada."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE job_applications
        SET cv_pdf_path = ?,
            cv_docx_path = ?,
            status = 'COMPILED'
        WHERE id = ?
    """,
        (pdf_path, docx_path, job_id),
    )
    conn.commit()
    conn.close()


def get_pending_or_all_jobs(pending_only: bool = False) -> List[sqlite3.Row]:
    """Obtiene los registros de vacantes para evaluación o exportación."""
    conn = get_db_connection()
    cursor = conn.cursor()
    if pending_only:
        cursor.execute(
            "SELECT * FROM job_applications WHERE status = 'PENDING'"
        )
    else:
        cursor.execute(
            "SELECT * FROM job_applications ORDER BY scraped_at DESC"
        )
    rows = cursor.fetchall()
    conn.close()
    return rows


def init_db() -> None:
    """Inicializa la base de datos creando la tabla con el esquema v2 si no existe y migra columnas."""
    init_and_migrate_db()


def compute_job_hash(
    title: str = "", company: str = "", location: str = "", description: str = "", **kwargs
) -> str:
    """Genera un hash SHA-256 único y determinista para la vacante."""
    t = str(title).strip().lower()
    c = str(company).strip().lower()
    l = str(location).strip().lower()
    snippet = str(description or kwargs.get("description_snippet", "")).strip().lower()[:200]
    raw = f"{c}|{t}|{l}|{snippet}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def is_job_exists(job_hash: str = "", url: str = "") -> bool:
    """Verifica si ya existe una vacante en la BD por SHA hash o por URL."""
    clean_hash = str(job_hash or "").strip()
    clean_url = str(url or "").strip()

    if not clean_hash and not clean_url:
        return False

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT 1 FROM job_applications 
            WHERE (job_hash = ? AND job_hash != '') OR (url = ? AND url != '')
            """,
            (clean_hash, clean_url),
        )
        return cursor.fetchone() is not None
    finally:
        conn.close()


def insert_job(
    job_hash: Any = None,
    title: str = "",
    company: str = "",
    location: str = "",
    url: str = "",
    description: str = "",
    status: str = "PENDING",
    **kwargs,
) -> bool:
    """Inserta una vacante en SQLite de forma idempotente (soporta dict o kwargs)."""
    if isinstance(job_hash, dict):
        d = job_hash
        title = d.get("title", "")
        company = d.get("company", "")
        location = d.get("location", "")
        url = d.get("url", "")
        description = d.get("description", "")
        status = d.get("status", status)
        job_hash = d.get("job_hash") or compute_job_hash(title=title, company=company, location=location, description=description)

    if not job_hash:
        job_hash = compute_job_hash(title=title, company=company, location=location, description=description)

    # Verificación directa de duplicados antes de la inserción
    if is_job_exists(job_hash=job_hash, url=url):
        return False

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT OR IGNORE INTO job_applications (job_hash, title, company, location, url, description, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (job_hash, title, company, location, url, description, status),
        )
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_and_migrate_db()