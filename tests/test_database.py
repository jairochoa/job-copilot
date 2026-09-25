"""
Pruebas unitarias para la capa de persistencia SQLite (src/database.py).
Valida hashing determinista, conexión y persistencia tolerante.
"""
from src.database import compute_job_hash, get_db_connection, insert_job


def test_compute_job_hash_determinism():
    h1 = compute_job_hash("Data Scientist", "Google", "Remote")
    h2 = compute_job_hash("  data scientist  ", "GOOGLE", "remote  ")
    assert h1 == h2
    assert len(h1) == 64  # SHA-256


def test_database_connection_and_table_structure():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='job_applications'")
    table = cursor.fetchone()
    assert table is not None
    
    # Comprobar que existen las columnas nuevas migradas
    cursor.execute("PRAGMA table_info(job_applications)")
    columns = [col[1] for col in cursor.fetchall()]
    assert "hard_match_score" in columns
    assert "soft_match_score" in columns
    assert "score_rationale" in columns
    conn.close()


def test_insert_job_idempotency():
    job_hash = "test_hash_unique_12345"
    inserted1 = insert_job(
        job_hash=job_hash,
        title="Test ML Engineer",
        company="Pytest Inc",
        location="Remote, CO",
        url="https://example.com/test-job",
        description="Testing database layer",
        status="PENDING"
    )
    # Segunda inserción con mismo job_hash debe ser ignorada (idempotencia)
    inserted2 = insert_job(
        job_hash=job_hash,
        title="Test ML Engineer",
        company="Pytest Inc",
        location="Remote, CO",
        url="https://example.com/test-job",
        description="Testing database layer",
        status="PENDING"
    )
    assert inserted2 is False


def test_sha_hash_deduplication_different_urls():
    """Valida que dos vacantes con el mismo hash SHA pero con URLs distintas sean rechazadas como duplicados."""
    import uuid

    uid = uuid.uuid4().hex[:8]
    title = f"Unique Senior Data Scientist {uid}"
    company = f"Unique Company Ltd {uid}"
    location = "Medellin, Colombia"
    desc = f"Detailed job description for SHA test {uid}"

    h1 = compute_job_hash(title=title, company=company, location=location, description=desc)

    ins1 = insert_job(
        job_hash=h1,
        title=title,
        company=company,
        location=location,
        url=f"https://linkedin.com/jobs/view/{uid}",
        description=desc,
    )
    assert ins1 is True

    # Intento de inserción con URL distinta de Indeed pero con la misma oferta (mismo hash)
    ins2 = insert_job(
        job_hash=h1,
        title=title,
        company=company,
        location=location,
        url=f"https://indeed.com/viewjob?id={uid}",
        description=desc,
    )
    assert ins2 is False