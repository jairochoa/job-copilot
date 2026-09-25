"""
Punto de entrada principal del Pipeline Automatizado Job-Copilot (Versión 2).
Flujo: Búsqueda -> Extracción Taxonómica -> RAG Matching -> Compilación ATS -> Reporte Excel.
"""
import sys
import logging
from pathlib import Path
from src.config import settings
from src.database import init_db, get_db_connection, insert_job
from src.extractor import extract_job_requirements
from src.matcher import evaluate_job_match
from src.compiler import ATSResumeCompiler, determine_country_profile
from src.exporter import export_applications_to_excel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("JobCopilot")


def show_funnel_metrics() -> dict:
    """Calcula y muestra las métricas consolidadas del embudo."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT status, COUNT(*) as total FROM job_applications GROUP BY status")
    rows = cursor.fetchall()
    conn.close()

    metrics = {row["status"]: row["total"] for row in rows}
    logger.info("=== MÉTRICAS DEL EMBUDO ===")
    for status, count in metrics.items():
        logger.info(f" - {status}: {count}")
    return metrics


def run_full_pipeline() -> None:
    """Ejecuta el flujo end-to-end de procesamiento de vacantes pendientes."""
    init_db()
    
    # 1. Prospección / Scraping (si existe módulo scraper)
    try:
        from src.scraper import run_scraper_flow
        logger.info("Iniciando prospección de vacantes...")
        run_scraper_flow()
    except (ImportError, AttributeError) as e:
        logger.warning(f"Omitiendo paso de prospección externa: {e}")

# 2. Recuperar vacantes pendientes de procesamiento
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT rowid AS db_id, * 
        FROM job_applications 
        WHERE status IN ('PENDING', 'SCRAPED')
        LIMIT 5
    """
    )
    pending_jobs = cursor.fetchall()
    conn.close()

    if not pending_jobs:
        logger.info("No hay vacantes pendientes por procesar.")
        show_funnel_metrics()
        export_applications_to_excel()
        return

    logger.info(
        f"Procesando {len(pending_jobs)} vacantes pendientes con RAG v2..."
    )
    compiler = ATSResumeCompiler()

    for job in pending_jobs:
        job_dict = dict(job)
        # Obtenemos el identificador de fila unívoco sin asumir la columna 'id'
        row_id = job_dict.get("db_id") or job_dict.get("rowid")

        title = job_dict.get("title") or "Posición no especificada"
        company = job_dict.get("company") or "Empresa confidencial"
        desc = job_dict.get("description") or ""

        logger.info(f"\n---> Analizando: {title} en {company}")

        # A. Extracción taxonómica estructurada con Gemini REST
        reqs = extract_job_requirements(
            job_title=title, company=company, description=desc
        )

        # B. Evaluación Vectorial RAG + Seniority agnóstico (80/20 hard skills)
        total_score, hard_score, soft_score, rationale, selected_bullet_ids = (
            evaluate_job_match(reqs)
        )

        # C. Determinar estatus según threshold configurado
        status = (
            "QUALIFIED"
            if total_score >= settings.MIN_QUALIFIED_SCORE
            else "DISQUALIFIED"
        )
        logger.info(f"Resultado: {status} (Score: {total_score}/100)")

        # D. Compilación de CV ATS si la vacante califica
        docx_str = ""
        pdf_str = ""
        if status == "QUALIFIED":
            country_code = determine_country_profile(
                location=job_dict.get("location", ""),
                country_detected=job_dict.get("country_detected", ""),
                target_profile=job_dict.get("target_profile", ""),
            )
            doc_lang = getattr(reqs, "language", "en") or "en"
            cv_paths = compiler.compile_cv(
                job_id=str(row_id),
                job_title=title,
                company_target=company,
                selected_bullet_ids=selected_bullet_ids,
                language=doc_lang,
                country_profile=country_code,
                requirements=reqs,
            )
            docx_str = cv_paths.get("docx", "")
            pdf_str = cv_paths.get("pdf", "")
            if docx_str:
                logger.info(
                    f"CV generado con éxito: {Path(docx_str).name} (Perfil: {country_code}, Idioma: {doc_lang})"
                )

        # E. Actualización atómica en SQLite usando rowid
        conn_upd = get_db_connection()
        cur_upd = conn_upd.cursor()
        cur_upd.execute(
            """
            UPDATE job_applications 
            SET status = ?,
                match_score = ?,
                hard_match_score = ?,
                soft_match_score = ?,
                score_rationale = ?,
                target_profile = ?,
                cv_docx_path = ?,
                cv_pdf_path = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE rowid = ?
        """,
            (
                status,
                total_score,
                hard_score,
                soft_score,
                rationale,
                reqs.role_category,
                docx_str,
                pdf_str,
                row_id,
            ),
        )
        conn_upd.commit()
        conn_upd.close()

    # 3. Exportar reporte consolidado a Excel y métricas
    export_applications_to_excel()
    show_funnel_metrics()


def main():
    run_full_pipeline()


if __name__ == "__main__":
    main()