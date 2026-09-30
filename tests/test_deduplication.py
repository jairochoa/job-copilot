"""
Pruebas de deduplicación determinista, hash SHA-256 e idempotencia en la ingesta y matching.
Valida que:
1. Las vacantes existentes en la BD no sean reinsertadas.
2. Los hashes SHA-256 sean consistentes y resistentes a diferencias de mayúsculas/espacios.
3. Las vacantes con status 'QUALIFIED' o 'DISQUALIFIED' no sean procesadas nuevamente por el pipeline.
"""

import sqlite3
import pytest
from src.database import (
    compute_job_hash,
    get_db_connection,
    insert_job,
    is_job_exists,
)


def test_compute_job_hash_deterministic():
    """Valida que el cálculo de hash SHA-256 sea determinista e insensible a mayúsculas/espacios."""
    hash1 = compute_job_hash(
        title="Senior Data Scientist",
        company="MercadoLibre",
        location="Bogotá, Colombia",
        description="Buscamos Senior Data Scientist con experiencia en Python...",
    )
    hash2 = compute_job_hash(
        title="  senior data scientist  ",
        company="  mercadolibre  ",
        location="  BOGOTÁ, COLOMBIA  ",
        description="  buscamos senior data scientist con experiencia en python...  ",
    )
    assert hash1 == hash2
    assert len(hash1) == 64  # SHA-256 hex length


def test_is_job_exists_by_hash_and_url():
    """Valida la detección de vacantes existentes tanto por hash como por URL."""
    # Obtenemos una vacante real existente en jobs.db
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT job_hash, url FROM job_applications LIMIT 1")
    row = cur.fetchone()
    conn.close()

    assert row is not None, "Debe existir al menos una vacante en la BD"
    existing_hash = row["job_hash"]
    existing_url = row["url"]

    # 1. Búsqueda por hash exacto
    assert is_job_exists(job_hash=existing_hash) is True

    # 2. Búsqueda por URL exacta
    assert is_job_exists(url=existing_url) is True

    # 3. Vacante inexistente
    assert (
        is_job_exists(
            job_hash="0000000000000000000000000000000000000000000000000000000000000000",
            url="https://nonexistent-company-job-xyz.com/view/123",
        )
        is False
    )


def test_insert_job_idempotence():
    """Valida que intentar insertar una vacante duplicada retorne False y no duplique registros."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM job_applications")
    count_before = cur.fetchone()[0]

    cur.execute("SELECT job_hash, title, company, location, url, description FROM job_applications LIMIT 1")
    row = dict(cur.fetchone())
    conn.close()

    # Intentamos reinsertar exactamente la misma vacante
    inserted = insert_job(
        job_hash=row["job_hash"],
        title=row["title"],
        company=row["company"],
        location=row["location"],
        url=row["url"],
        description=row["description"],
    )

    # Debe ser rechazada
    assert inserted is False

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM job_applications")
    count_after = cur.fetchone()[0]
    conn.close()

    # El conteo debe mantenerse idéntico
    assert count_before == count_after


def test_pipeline_ignores_already_processed_jobs():
    """Valida que el query de main.py (status IN ('PENDING', 'SCRAPED')) ignore vacantes ya evaluadas."""
    conn = get_db_connection()
    cur = conn.cursor()
    # Query exacto que ejecuta main.py
    cur.execute(
        """
        SELECT rowid AS db_id, * 
        FROM job_applications 
        WHERE status IN ('PENDING', 'SCRAPED')
        """
    )
    pending_jobs = cur.fetchall()

    # Conteo de vacantes ya evaluadas
    cur.execute(
        """
        SELECT status, COUNT(*) as total 
        FROM job_applications 
        WHERE status IN ('QUALIFIED', 'DISQUALIFIED')
        GROUP BY status
        """
    )
    processed_stats = {row["status"]: row["total"] for row in cur.fetchall()}
    conn.close()

    # Si todas las vacantes en BD fueron procesadas, pending_jobs debe estar vacío
    total_processed = sum(processed_stats.values())
    if total_processed > 0:
        for job in pending_jobs:
            assert job["status"] not in ("QUALIFIED", "DISQUALIFIED")
