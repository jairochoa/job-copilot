"""
Tests unitarios para el módulo de persistencia y utilidades de deduplicación.
"""

import sqlite3

from src.database import compute_job_hash, get_db_connection, init_db, insert_job


def test_compute_job_hash_normalization():
    """Valida que nombres con mayúsculas, sufijos legales y espacios generen el mismo hash SHA-256."""
    hash_1 = compute_job_hash(
        company="Bancolombia S.A.S.",
        title="Senior Data Scientist",
        description_snippet="Liderar iniciativas analíticas y modelos de ML en Python."
    )
    hash_2 = compute_job_hash(
        company="bancolombia",
        title="senior data scientist",
        description_snippet="Liderar iniciativas analíticas y modelos de ML en Python."
    )
    
    assert hash_1 == hash_2
    assert len(hash_1) == 64  # Longitud estándar de un hash SHA-256 en hexadecimal

def test_database_lifecycle_and_deduplication(tmp_path, monkeypatch):
    """Verifica creación de tablas, modo WAL y descarte transaccional de registros duplicados."""
    test_db_path = tmp_path / "test_jobs.db"
    monkeypatch.setattr("src.database.DB_PATH", test_db_path)

    # 1. Inicialización
    init_db()
    assert test_db_path.exists()

    # 2. Verificar modo WAL
    with sqlite3.connect(str(test_db_path)) as conn:
        mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        assert mode.lower() == "wal"

    # 3. Payload de prueba
    payload = {
        "title": "Machine Learning Engineer",
        "company": "IDATA",
        "location": "Medellín, Colombia",
        "url": "https://example.com/job/123",
        "portal_source": "linkedin",
        "description": "Desarrollo de modelos predictivos en PyTorch.",
        "ats_type": "UNKNOWN",
        "requires_login": 0,
        "status": "SCRAPED"
    }

    # 4. Primera inserción -> True
    assert insert_job(payload) is True

    # 5. Segunda inserción con datos equivalentes -> False (duplicado)
    assert insert_job(payload) is False

    # 6. Validar que la tabla solo contenga un registro
    with get_db_connection() as conn:
        row = conn.execute("SELECT COUNT(*) as total FROM job_applications;").fetchone()
        assert row["total"] == 1
