import argparse
import sys
from pathlib import Path

from src.database import init_db
from src.logger import logger

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"

DEFAULT_SEARCH_TARGETS = [
    ("Data Scientist", "Colombia"),
    ("Senior Data Scientist", "Remote"),
    ("Machine Learning Engineer", "Remote"),
    ("Statistician", "Colombia"),
]

def run_scraping_flow(term: str | None = None, loc: str | None = None):
    from src.scraper import run_job_search
    if term and loc:
        targets = [(term, loc)]
    elif term:
        targets = [(term, "Remote"), (term, "Colombia")]
    else:
        targets = DEFAULT_SEARCH_TARGETS

    for s_term, s_loc in targets:
        logger.info(f"==> Iniciando prospección: '{s_term}' en '{s_loc}'...")
        try:
            run_job_search(search_term=s_term, location=s_loc, results_wanted=15)
        except Exception as err:
            logger.error(f"Falla durante la búsqueda de '{s_term}' en '{s_loc}': {err}")

def run_prefilter_flow():
    from src.matcher import run_heuristic_filter_batch
    logger.info("==> Aplicando prefiltro booleano ($0)...")
    run_heuristic_filter_batch()

def run_evaluation_flow():
    from src.matcher import run_gemini_evaluation_batch
    logger.info("==> Evaluando vacantes con Gemini (Rúbrica 40/25/20/15)...")
    run_gemini_evaluation_batch()

def run_compile_flow():
    from src.compiler import build_applications_batch
    logger.info("==> Compilando CVs para vacantes calificadas...")
    count = build_applications_batch()
    logger.info(f"==> Compilación finalizada. CVs procesados: {count}")

def run_export_flow():
    from src.exporter import sync_jobs_to_excel
    logger.info("==> Sincronizando con Excel...")
    added = sync_jobs_to_excel()
    print(f"[OK] Sincronización finalizada. Vacantes nuevas agregadas: {added}")

def run_stats_flow():
    import sqlite3
    db_path = BASE_DIR / "data" / "jobs.db"
    if not db_path.exists():
        print("Base de datos no encontrada.")
        return
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    rows = cur.execute("SELECT status, count(*) FROM job_applications GROUP BY status").fetchall()
    conn.close()
    print("\n--- RESUMEN DEL PIPELINE ---")
    for status, count in rows:
        print(f"  {status:<15}: {count}")
    print("----------------------------\n")

def run_full_pipeline():
    logger.info("Iniciando Pipeline Completo End-to-End...")
    run_scraping_flow()
    run_prefilter_flow()
    run_evaluation_flow()
    run_compile_flow()
    run_export_flow()
    logger.info("Pipeline completado exitosamente.")

def main():
    init_db()

    parser = argparse.ArgumentParser(
        description="Job-Copilot: Prospección, evaluación semántica y compilación ATS"
    )
    parser.add_argument("--run", action="store_true", help="Ejecuta todo el pipeline de extremo a extremo")
    parser.add_argument("--scrape", action="store_true", help="Solo raspa nuevas vacantes")
    parser.add_argument("--filter", action="store_true", help="Solo corre el prefiltro booleano ($0)")
    parser.add_argument("--evaluate", action="store_true", help="Solo evalúa vacantes con Gemini")
    parser.add_argument("--compile", action="store_true", help="Solo compila CVs de vacantes calificadas")
    parser.add_argument("--export-excel", action="store_true", help="Sincroniza vacantes hacia Excel")
    parser.add_argument("--stats", action="store_true", help="Muestra estadísticas del pipeline")
    parser.add_argument("--apply", action="store_true", help="Modo interactivo de postulación asistida")

    args = parser.parse_args()

    # Si se pasó una bandera específica, ejecutar solo esa bandera
    if args.scrape:
        run_scraping_flow()
    elif args.filter:
        run_prefilter_flow()
    elif args.evaluate:
        run_evaluation_flow()
    elif args.compile:
        run_compile_flow()
    elif args.export_excel:
        run_export_flow()
    elif args.stats:
        run_stats_flow()
    elif args.apply:
        from src.copilot import run_copilot_assistant
        run_copilot_assistant()
    elif args.run or len(sys.argv) == 1:
        run_full_pipeline()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
