"""
Script de reprocesamiento masivo (Backfill).
Actualiza las vacantes históricas de jobs.db aplicando el nuevo extractor
y el motor RAG vectorial local sin asumir nombres rígidos de columnas.
"""

import json
import logging
from src.config import settings
from src.database import get_db_connection
from src.extractor import extract_job_requirements
from src.matcher import evaluate_job_match

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


def reprocess_all_jobs() -> None:
    conn = get_db_connection()
    cursor = conn.cursor()

    # Inspeccionar columnas existentes para saber cuál es el ID
    cursor.execute("PRAGMA table_info(job_applications)")
    cols = [row["name"] for row in cursor.fetchall()]
    id_col = "id" if "id" in cols else ("job_id" if "job_id" in cols else "rowid")

    # Traer todos los registros usando rowid como ancla segura
    cursor.execute(f"SELECT rowid, * FROM job_applications")
    jobs = cursor.fetchall()

    logger.info(
        f"Iniciando reprocesamiento de {len(jobs)} vacantes históricas (usando columna clave: '{id_col}')..."
    )

    for idx, row in enumerate(jobs, start=1):
        job_data = dict(row)
        db_rowid = job_data["rowid"]
        
        # Obtener valores tolerando nombres alternativos
        title = job_data.get("title", "") or "Sin Título"
        company = job_data.get("company", "") or "Confidencial"
        desc = job_data.get("description", "") or ""

        if not desc.strip():
            logger.warning(
                f"[{idx}/{len(jobs)}] Saltando registro rowid={db_rowid}: descripción vacía."
            )
            continue

        logger.info(
            f"[{idx}/{len(jobs)}] Procesando: '{title}' en '{company}'..."
        )

        try:
            # 1. Extracción estructurada con Gemini
            reqs = extract_job_requirements(title, company, desc)

            # 2. Matching semántico RAG local (0-100)
            score, hard, soft, rationale, bullets = evaluate_job_match(reqs)

            # 3. Actualización directa usando rowid para máxima compatibilidad
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
                WHERE rowid = ?
                """,
                (
                    score,
                    hard,
                    soft,
                    rationale,
                    json.dumps(reqs.model_dump(), ensure_ascii=False),
                    json.dumps(bullets, ensure_ascii=False),
                    1 if reqs.is_remote_or_eligible else 0,
                    score,
                    settings.MIN_QUALIFIED_SCORE,
                    db_rowid,
                ),
            )
            conn.commit()
            logger.info(
                f" -> Actualizado rowid={db_rowid}: Score {score} (Hard: {hard}%, Soft: {soft}%)"
            )

        except Exception as e:
            logger.error(f"Error procesando registro rowid={db_rowid}: {e}")

    conn.close()
    logger.info("Reprocesamiento histórico completado.")


if __name__ == "__main__":
    reprocess_all_jobs()