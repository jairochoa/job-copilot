from src.database import get_db_connection

with get_db_connection() as conn:
    row = conn.execute("SELECT company, title, tailored_headline, tailored_summary FROM job_applications WHERE company LIKE '%Cavca%' LIMIT 1;").fetchone()

if row:
    print("=== EMPRESA ===")
    print(row["company"])
    print("\n=== CARGO ===")
    print(row["title"])
    print("\n=== HEADLINE ===")
    print(row["tailored_headline"])
    print("\n=== SUMMARY ===")
    print(row["tailored_summary"])
else:
    print("No se encontraron registros.")
