import logging
from pathlib import Path
import sqlite3
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

logger = logging.getLogger("JobCopilot.Exporter")

DEFAULT_DB_PATH = Path("data/jobs.db")
DEFAULT_EXCEL_PATH = Path("output/pipeline_vacantes.xlsx")

HEADERS = [
    "Hash ID",
    "Score",
    "Perfil Objetivo",
    "Portal / Fuente",
    "Tipo ATS",
    "Requiere Login",
    "Empresa",
    "Cargo",
    "Ubicación",
    "Idioma",
    "Estado Pipeline",
    "Estado Postulación (Agente)",
    "URL Directa",
    "Ruta CV PDF",
    "Ruta CV DOCX",
    "Headline ATS",
    "Resumen Adaptado (Tailored Summary)",
    "Razón del Score (Rationale)",
    "Fecha Scraped",
    "Fecha Postulado",
]

HEADER_FILL = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
REGULAR_FONT = Font(name="Calibri", size=10)
BORDER_THIN = Border(
    left=Side(style="thin", color="D9D9D9"),
    right=Side(style="thin", color="D9D9D9"),
    top=Side(style="thin", color="D9D9D9"),
    bottom=Side(style="thin", color="D9D9D9"),
)

def init_excel_workbook(file_path: Path) -> openpyxl.Workbook:
    """Crea un nuevo libro de Excel con formato profesional, encabezados congelados y estilos."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Pipeline de Vacantes"
    ws.views.sheetView[0].showGridLines = True

    ws.append(HEADERS)
    for col_num, _ in enumerate(HEADERS, start=1):
        cell = ws.cell(row=1, column=col_num)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    ws.freeze_panes = "A2"
    return wb

def sync_jobs_to_excel(
    db_path: Path = DEFAULT_DB_PATH,
    excel_path: Path = DEFAULT_EXCEL_PATH,
    min_score: int = 0,
) -> int:
    """
    Sincroniza vacantes de la tabla 'job_applications' en SQLite hacia Excel de forma incremental.
    Solo añade filas para los job_hash que aún no existan en la hoja de cálculo.
    """
    if not db_path.exists():
        logger.warning(f"Base de datos {db_path} no encontrada.")
        return 0

    excel_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Cargar o crear libro y recopilar identificadores ya exportados
    existing_ids = set()
    if excel_path.exists():
        try:
            wb = openpyxl.load_workbook(excel_path)
            ws = wb.active
            for row in range(2, ws.max_row + 1):
                val = ws.cell(row=row, column=1).value
                if val:
                    existing_ids.add(str(val).strip())
        except Exception as e:
            logger.error(f"Error abriendo Excel existente: {e}. Creando nuevo.")
            wb = init_excel_workbook(excel_path)
            ws = wb.active
    else:
        wb = init_excel_workbook(excel_path)
        ws = wb.active

    # 2. Consultar registros calificados y relevantes
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = """
    SELECT 
        job_hash,
        match_score,
        target_profile,
        portal_source,
        ats_type,
        requires_login,
        company,
        title,
        location,
        language,
        status,
        url,
        resolved_url,
        pdf_path,
        docx_path,
        tailored_headline,
        tailored_summary,
        score_rationale,
        scraped_at,
        applied_at
    FROM job_applications
    -- Incluye todo el pipeline: GENERATED, SCORED, APPLIED, SCRAPED y DISCARDED
    WHERE 1=1
      AND (match_score >= ? OR match_score IS NULL)
    ORDER BY match_score DESC, scraped_at DESC
    """
    rows = cursor.execute(query, (min_score,)).fetchall()
    conn.close()

    added_count = 0

    # 3. Anexar registros nuevos sin alterar los existentes
    for r in rows:
        job_hash = str(r["job_hash"]).strip()
        if job_hash in existing_ids:
            continue

        score = r["match_score"] or 0
        target_profile = r["target_profile"] or ""
        portal_source = r["portal_source"] or "Directo"
        ats_type = r["ats_type"] or "Desconocido"
        requires_login = "SÍ" if r["requires_login"] else "NO"
        company = r["company"] or ""
        title = r["title"] or ""
        location = r["location"] or ""
        language = r["language"] or "en"
        pipeline_status = r["status"] or ""
        agent_status = "READY_TO_APPLY" if pipeline_status == "SCORED" else pipeline_status
        link_url = r["resolved_url"] or r["url"] or ""
        pdf_path = r["pdf_path"] or ""
        docx_path = r["docx_path"] or ""
        headline = r["tailored_headline"] or ""
        summary = r["tailored_summary"] or ""
        rationale = r["score_rationale"] or ""
        scraped_at = r["scraped_at"] or ""
        applied_at = r["applied_at"] or ""

        ws.append([
            job_hash,
            score,
            target_profile,
            portal_source,
            ats_type,
            requires_login,
            company,
            title,
            location,
            language,
            pipeline_status,
            agent_status,
            link_url,
            pdf_path,
            docx_path,
            headline,
            summary,
            rationale,
            scraped_at,
            applied_at,
        ])

        curr_row = ws.max_row

        # Bordes y fuentes
        for col_idx in range(1, len(HEADERS) + 1):
            c = ws.cell(row=curr_row, column=col_idx)
            c.font = REGULAR_FONT
            c.border = BORDER_THIN
            c.alignment = Alignment(vertical="top")

        # Score centrado
        ws.cell(row=curr_row, column=2).alignment = Alignment(horizontal="center", vertical="top")

        # Hipervínculo directo
        if link_url.startswith("http"):
            url_cell = ws.cell(row=curr_row, column=13)
            url_cell.hyperlink = link_url
            url_cell.font = Font(name="Calibri", size=10, color="0563C1", underline="single")

        existing_ids.add(job_hash)
        added_count += 1

    # 4. Dimensionamiento y auto-filtros si hubo cambios
    if added_count > 0 or not excel_path.exists():
        widths = {
            1: 14,  # Hash ID
            2: 8,   # Score
            3: 18,  # Target Profile
            4: 15,  # Portal Source
            5: 14,  # ATS Type
            6: 12,  # Requires Login
            7: 22,  # Company
            8: 30,  # Title
            9: 18,  # Location
            10: 10, # Language
            11: 16, # Pipeline Status
            12: 24, # Agent Status
            13: 35, # Direct URL
            14: 25, # PDF Path
            15: 25, # DOCX Path
            16: 30, # Headline
            17: 45, # Summary
            18: 35, # Rationale
            19: 18, # Scraped At
            20: 18, # Applied At
        }
        for col_idx, width in widths.items():
            col_letter = get_column_letter(col_idx)
            ws.column_dimensions[col_letter].width = width

        ws.auto_filter.ref = f"A1:{get_column_letter(len(HEADERS))}{ws.max_row}"
        wb.save(excel_path)
        logger.info(f"Sincronización exitosa: {added_count} vacantes agregadas a {excel_path}")
    else:
        logger.info("El archivo Excel ya se encuentra actualizado.")

    return added_count
