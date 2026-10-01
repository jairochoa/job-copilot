"""
Punto de entrada principal del Pipeline Automatizado Job-Copilot (Versión 2).
Flujo: Búsqueda -> Extracción Taxonómica -> RAG Matching -> Compilación ATS -> Reporte Excel.
"""
import argparse
import logging
import sys
from pathlib import Path
from typing import List, Optional

from src.compiler import ATSResumeCompiler, determine_country_profile
from src.config import settings
from src.database import get_db_connection, init_db, insert_job
from src.exporter import export_applications_to_excel
from src.extractor import extract_job_requirements
from src.matcher import evaluate_job_match

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


def run_full_pipeline(
    search_terms: Optional[List[str]] = None,
    locations: Optional[List[str]] = None,
    results_wanted: Optional[int] = None,
    hours_old: Optional[int] = None,
    is_remote: Optional[bool] = None,
    skip_scraping: bool = False,
    only_qualified_report: bool = False,
) -> None:
    """Ejecuta el flujo end-to-end de procesamiento de vacantes con parámetros dinámicos."""
    init_db()

    # 1. Prospección / Scraping dinámico (si no se omite explícitamente)
    if not skip_scraping:
        try:
            from src.scraper import run_scraper_flow
            logger.info("Iniciando prospección de vacantes...")
            run_scraper_flow(
                search_terms=search_terms,
                locations=locations,
                results_wanted=results_wanted,
                hours_old=hours_old,
                is_remote=is_remote,
            )
        except (ImportError, AttributeError) as e:
            logger.warning(f"Omitiendo paso de prospección externa: {e}")
    else:
        logger.info("Fase de scraping omitida (--skip-scraping activo).")

    # 2. Recuperar vacantes pendientes de procesamiento
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT rowid AS db_id, * 
        FROM job_applications 
        WHERE status IN ('PENDING', 'SCRAPED')
        """
    )
    pending_jobs = cursor.fetchall()
    conn.close()

    if not pending_jobs:
        logger.info("No hay vacantes pendientes por procesar.")
        show_funnel_metrics()
        export_applications_to_excel(only_qualified=only_qualified_report)
        return

    logger.info(
        f"Procesando {len(pending_jobs)} vacantes pendientes con RAG v2..."
    )
    compiler = ATSResumeCompiler()

    for job in pending_jobs:
        job_dict = dict(job)
        row_id = job_dict.get("db_id") or job_dict.get("rowid")

        title = job_dict.get("title") or "Posición no especificada"
        company = job_dict.get("company") or "Empresa confidencial"
        desc = job_dict.get("description") or ""

        logger.info(f"\n---> Analizando: {title} en {company}")

        # A. Extracción taxonómica estructurada con Gemini REST
        reqs = extract_job_requirements(
            job_title=title, company=company, description=desc
        )

        # B. Evaluación Vectorial RAG + Seniority agnóstico
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
    export_applications_to_excel(only_qualified=only_qualified_report)
    show_funnel_metrics()


def parse_args():
    """Configura los argumentos dinámicos de línea de comandos."""
    parser = argparse.ArgumentParser(
        description="Job-Copilot v1.0.0 - Búsqueda Inteligente, Matching Semántico RAG y Generación ATS",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--terms",
        type=str,
        default=None,
        help="Términos de búsqueda separados por comas (ej. 'Data Scientist, Machine Learning Engineer')",
    )
    parser.add_argument(
        "--locations",
        type=str,
        default=None,
        help="Ubicaciones geográficas separadas por comas (ej. 'Colombia, Remote')",
    )
    parser.add_argument(
        "--results",
        type=int,
        default=None,
        help=f"Resultados deseados por búsqueda (default de config: {settings.SCRAPER_RESULTS_WANTED})",
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=None,
        help=f"Antigüedad máxima en horas (default de config: {settings.SCRAPER_HOURS_OLD})",
    )
    parser.add_argument(
        "--remote",
        action="store_true",
        default=None,
        help="Filtrar estrictamente posiciones remotas",
    )
    parser.add_argument(
        "--skip-scraping",
        action="store_true",
        default=False,
        help="Omitir prospección web y procesar directamente la cola en SQLite",
    )
    parser.add_argument(
        "--only-qualified",
        action="store_true",
        default=False,
        help="Exportar únicamente vacantes QUALIFIED al reporte Excel",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    terms = [t.strip() for t in args.terms.split(",") if t.strip()] if args.terms else None
    locs = [l.strip() for l in args.locations.split(",") if l.strip()] if args.locations else None

    run_full_pipeline(
        search_terms=terms,
        locations=locs,
        results_wanted=args.results,
        hours_old=args.hours,
        is_remote=args.remote,
        skip_scraping=args.skip_scraping,
        only_qualified_report=args.only_qualified,
    )


if __name__ == "__main__":
    main()