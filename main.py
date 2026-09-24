from src.exporter import sync_jobs_to_excel
"""
Orquestador Principal y CLI de Postulación (HU-06).
Coordina el pipeline end-to-end:
1. Scraping de portales configurados.
2. Prefiltro booleano ($0).
3. Evaluación semántica con Gemini API.
4. Compilación ATS (PDF y DOCX).
5. Asistente interactivo con portapapeles y registro de estado.
"""

import argparse
import webbrowser
from pathlib import Path

try:
    import pyperclip
except ImportError:
    pyperclip = None

from src.compiler import build_applications_batch
from src.database import get_db_connection, init_db
from src.logger import logger
from src.matcher import run_gemini_evaluation_batch, run_heuristic_filter_batch
from src.scraper import run_job_search

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"


def show_funnel_metrics() -> None:
    """Muestra el embudo de conversión actual en la base de datos."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT status, COUNT(*) as count 
            FROM job_applications 
            GROUP BY status;
            """
        )
        counts = dict(cursor.fetchall())

    total = sum(counts.values())
    scraped = counts.get("SCRAPED", 0)
    filtered = counts.get("FILTERED_OUT", 0)
    discarded = counts.get("DISCARDED", 0)
    scored = counts.get("SCORED", 0)
    generated = counts.get("GENERATED", 0)
    applied = counts.get("APPLIED", 0)

    print("\n" + "=" * 55)
    print(" 📊 EMBUDO DE CONVERSIÓN - JOB COPILOT")
    print("=" * 55)
    print(f" Total vacantes en base de datos: {total}")
    print(f" 📥 En espera de evaluación (SCRAPED):   {scraped}")
    print(f" 🚫 Descartadas por reglas duras:        {filtered}")
    print(f" 📉 Descartadas por score bajo Gemini:   {discarded}")
    print(f" 🎯 Calificadas con match alto:          {scored}")
    print(f" 📄 CVs compilados listos (GENERATED):   {generated}")
    print(f" ✅ Postulaciones enviadas (APPLIED):    {applied}")
    print("=" * 55 + "\n")


def run_pipeline() -> None:
    """Ejecuta el ciclo de vida batch completo."""
    logger.info("Iniciando pipeline automatizado...")
    init_db()

    logger.info("Fase 1: Extracción de vacantes...")
    run_job_search()

    logger.info("Fase 2: Prefiltro booleano ($0)...")
    run_heuristic_filter_batch()

    logger.info("Fase 3: Evaluación semántica con Gemini...")
    run_gemini_evaluation_batch()

    logger.info("Fase 4: Compilación ATS (PDF & DOCX)...")
    build_applications_batch()

    show_funnel_metrics()


def interactive_apply_assistant() -> None:
    """Asistente en consola para postular con asistencia de portapapeles y navegador."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT job_hash, title, company, url, match_score, tailored_summary, language
            FROM job_applications
            WHERE status = 'GENERATED'
            ORDER BY match_score DESC;
            """
        )
        ready_jobs = [dict(row) for row in cursor.fetchall()]

    if not ready_jobs:
        print("No hay vacantes en estado 'GENERATED' pendientes de postulación.")
        return

    print(f"\nSe encontraron {len(ready_jobs)} vacantes listas para postular.")

    for idx, job in enumerate(ready_jobs, start=1):
        print("\n" + "-" * 60)
        print(f"[{idx}/{len(ready_jobs)}] {job['company']} — {job['title']}")
        print(f"Match Score: {job['match_score']}/100 | Idioma: {job['language']}")
        print(f"URL: {job['url']}")
        print("-" * 60)
        print(f"Resumen adaptado:\n{job['tailored_summary']}\n")

        print(
            "Opciones: [o] Abrir URL y copiar resumen | [a] Marcar como APLICADA | [s] Saltar | [q] Salir"
        )
        choice = input("Selecciona una opción (o/a/s/q): ").strip().lower()

        if choice == "o":
            if pyperclip:
                pyperclip.copy(job["tailored_summary"] or "")
                print("📋 Resumen profesional copiado al portapapeles.")
            if job.get("url"):
                print("🌐 Abriendo URL en el navegador...")
                webbrowser.open(job["url"])

            sub_choice = (
                input("¿Deseas marcarla como enviada ahora? (s/n): ").strip().lower()
            )
            if sub_choice == "s":
                choice = "a"

        if choice == "a":
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE job_applications SET status = 'APPLIED', updated_at = CURRENT_TIMESTAMP WHERE job_hash = ?;",
                    (job["job_hash"],),
                )
            print("✅ Marcada como APLICADA.")
        elif choice == "q":
            print("Saliendo del asistente...")
            break
        else:
            print("⏩ Saltada temporalmente.")

    show_funnel_metrics()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Job Copilot - Pipeline de postulación inteligente"
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Ejecutar pipeline completo de scraping a compilación",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Lanzar asistente interactivo de postulación",
    )
    parser.add_argument(
        "--export-excel",
        action="store_true",
        help="Sincroniza vacantes evaluadas hacia output/pipeline_vacantes.xlsx incrementalmente",
    )
    parser.add_argument(
        "--stats", action="store_true", help="Ver métricas del embudo de conversión"
    )

    args = parser.parse_args()

    if args.run:
        run_pipeline()
    elif args.apply:
        interactive_apply_assistant()
    elif args.export_excel:
        added = sync_jobs_to_excel()
        print(f"[OK] Sincronización finalizada. Vacantes nuevas agregadas: {added}")
        return

    if args.stats:
        show_funnel_metrics()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
