from src.compiler import build_applications_batch
from src.database import get_db_connection
from src.matcher import run_gemini_evaluation_batch

# 1. Resetear todas las vacantes aprobadas para reevaluarlas con el nuevo estandar
with get_db_connection() as conn:
    conn.execute("UPDATE job_applications SET status = 'SCRAPED' WHERE status IN ('SCORED', 'APPLIED');")
    conn.commit()
    print("Base de datos reseteada a SCRAPED.")

# 2. Reevaluar con Gemini (respetando los 4.5s de cortesía para no saturar cuota)
print("\n--- Evaluando con Gemini bajo el nuevo estándar estricto ---")
run_gemini_evaluation_batch()

# 3. Compilar los PDFs limpios
print("\n--- Recompilando todos los CVs ---")
build_applications_batch()
