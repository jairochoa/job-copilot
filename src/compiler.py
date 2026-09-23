"""
Módulo de Compilación de CVs (HU-05).
Genera versiones adaptadas en PDF (Playwright) y DOCX (python-docx)
cruzando el análisis de Gemini con data/master_cv.json.
"""

import json
import re
from pathlib import Path
from typing import Any

from docx import Document
from docx.shared import Inches, Pt, RGBColor
from jinja2 import Template
from playwright.sync_api import sync_playwright

from src.database import get_db_connection
from src.logger import logger

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"
MASTER_CV_PATH = BASE_DIR / "data" / "master_cv.json"
TEMPLATE_HTML_PATH = BASE_DIR / "templates" / "cv_template.html"


def sanitize_filename(name: str) -> str:
    """Limpia cadenas para usarlas de forma segura en nombres de archivo."""
    return re.sub(r"[^\w\-_\. ]", "_", name).strip()


def load_master_cv() -> dict[str, Any]:
    with open(MASTER_CV_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def prepare_cv_context(
    job_record: dict[str, Any], master_cv: dict[str, Any]
) -> dict[str, Any]:
    """Ensambla el payload final de datos en el idioma correspondiente."""
    lang = job_record.get("language", "en")
    text_key = "text_es" if lang == "es" else "text_en"

    # Mapeo de viñetas seleccionadas por empresa
    raw_bullets_json = job_record.get("selected_bullet_ids")
    selected_bullets_map: dict[str, list[str]] = {}
    if raw_bullets_json:
        try:
            selected_bullets_map = json.loads(raw_bullets_json)
        except Exception:
            selected_bullets_map = {}

    processed_experience = []
    for exp in master_cv.get("experience", []):
        cid = exp.get("company_id")
        allowed_ids = selected_bullets_map.get(cid, [])

        matching_bullets = []
        for b in exp.get("bullets", []):
            if not allowed_ids or b.get("id") in allowed_ids:
                matching_bullets.append(b.get(text_key, b.get("text_en")))

        # Fallback si no seleccionó ninguna viñeta
        if not matching_bullets and exp.get("bullets"):
            matching_bullets = [exp["bullets"][0].get(text_key)]

        processed_experience.append(
            {
                "company": exp.get("company"),
                "title": exp.get("title_formula_a"),
                "location": exp.get("location"),
                "period": exp.get("period_en")
                if lang == "en"
                else exp.get("period_es"),
                "selected_bullets": matching_bullets,
            }
        )

    # Certificaciones traducidas
    certs = []
    for c in master_cv.get("certifications", []):
        certs.append(
            {
                "name": c.get("name"),
                "issuer": c.get("issuer"),
                "year": c.get("year"),
            }
        )

    # Educación traducida
    education = []
    for edu in master_cv.get("education", []):
        education.append(
            {
                "degree": edu.get("degree_es")
                if lang == "es"
                else edu.get("degree_en"),
                "institution": edu.get("institution"),
                "year": edu.get("year"),
            }
        )

    return {
        "language": lang,
        "personal": master_cv.get("personal_info", {}),
        "tailored_headline": job_record.get("tailored_headline"),
        "tailored_summary": job_record.get("tailored_summary"),
        "experience": processed_experience,
        "education": education,
        "certifications": certs,
        "skills": master_cv.get("technical_skills", {}),
    }


def compile_pdf_with_playwright(html_content: str, output_path: Path) -> None:
    """Compila el HTML a PDF usando Playwright Chromium headless."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html_content, wait_until="networkidle")
        page.pdf(
            path=str(output_path),
            format="Letter",
            print_background=True,
            margin={
                "top": "1.2cm",
                "bottom": "1.2cm",
                "left": "1.4cm",
                "right": "1.4cm",
            },
        )
        browser.close()


def compile_docx(context: dict[str, Any], output_path: Path) -> None:
    """Genera documento DOCX compatible con ATS usando python-docx."""
    doc = Document()

    # Configurar márgenes
    sections = doc.sections
    for section in sections:
        section.top_margin = Inches(0.6)
        section.bottom_margin = Inches(0.6)
        section.left_margin = Inches(0.7)
        section.right_margin = Inches(0.7)

    personal = context["personal"]
    lang = context["language"]

    # Nombre
    title_p = doc.add_paragraph()
    r_name = title_p.add_run(personal.get("name", ""))
    r_name.font.size = Pt(18)
    r_name.font.bold = True
    r_name.font.color.rgb = RGBColor(15, 23, 42)
    title_p.paragraph_format.space_after = Pt(2)

    # Titular adaptado
    h_p = doc.add_paragraph()
    r_head = h_p.add_run(context.get("tailored_headline", ""))
    r_head.font.size = Pt(11)
    r_head.font.bold = True
    r_head.font.color.rgb = RGBColor(37, 99, 235)
    h_p.paragraph_format.space_after = Pt(4)

    # Contacto
    c_p = doc.add_paragraph()
    contact_str = (
        f"{personal.get('location')} | {personal.get('email')} | "
        f"{personal.get('phone')} | linkedin.com/in/jairochoa | github.com/jairochoa"
    )
    r_contact = c_p.add_run(contact_str)
    r_contact.font.size = Pt(9)
    r_contact.font.color.rgb = RGBColor(100, 116, 139)
    c_p.paragraph_format.space_after = Pt(10)

    def add_section_header(title: str):
        sec_p = doc.add_paragraph()
        r_sec = sec_p.add_run(title.upper())
        r_sec.font.size = Pt(11)
        r_sec.font.bold = True
        r_sec.font.color.rgb = RGBColor(15, 23, 42)
        sec_p.paragraph_format.space_before = Pt(8)
        sec_p.paragraph_format.space_after = Pt(4)

    # Resumen
    summary_title = "RESUMEN PROFESIONAL" if lang == "es" else "PROFESSIONAL SUMMARY"
    add_section_header(summary_title)
    s_p = doc.add_paragraph(context.get("tailored_summary", ""))
    s_p.paragraph_format.space_after = Pt(8)

    # Experiencia
    exp_title = "EXPERIENCIA LABORAL" if lang == "es" else "PROFESSIONAL EXPERIENCE"
    add_section_header(exp_title)
    for exp in context.get("experience", []):
        job_p = doc.add_paragraph()
        r_role = job_p.add_run(f"{exp['title']} - {exp['company']}")
        r_role.font.bold = True
        job_p.add_run(f" ({exp['period']})")
        job_p.paragraph_format.space_after = Pt(2)

        for b in exp.get("selected_bullets", []):
            b_p = doc.add_paragraph(b, style="List Bullet")
            b_p.paragraph_format.space_after = Pt(2)

    # Educación
    edu_title = "EDUCACIÓN" if lang == "es" else "EDUCATION"
    add_section_header(edu_title)
    for edu in context.get("education", []):
        doc.add_paragraph(f"{edu['degree']} — {edu['institution']} ({edu['year']})")

    # Guardar archivo
    doc.save(str(output_path))


def build_applications_batch() -> int:
    """Compila PDFs y DOCXs para todas las vacantes en estado 'SCORED'."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    master_cv = load_master_cv()

    with open(TEMPLATE_HTML_PATH, "r", encoding="utf-8") as f:
        html_template = Template(f.read())

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM job_applications WHERE status = 'SCORED';")
        scored_jobs = [dict(row) for row in cursor.fetchall()]

    if not scored_jobs:
        logger.info("No hay vacantes en estado 'SCORED' listas para compilar.")
        return 0

    logger.info(
        f"Iniciando compilación ATS para {len(scored_jobs)} vacantes calificadas..."
    )
    compiled_count = 0

    for job in scored_jobs:
        context = prepare_cv_context(job, master_cv)
        rendered_html = html_template.render(**context)

        company_clean = sanitize_filename(job["company"])
        title_clean = sanitize_filename(job["title"])
        base_name = f"CV_Jairo_Ochoa_{company_clean}_{job['job_hash'][:6]}"

        pdf_path = OUTPUT_DIR / f"{base_name}.pdf"
        docx_path = OUTPUT_DIR / f"{base_name}.docx"

        # 1. Generar PDF
        compile_pdf_with_playwright(rendered_html, pdf_path)
        # 2. Generar DOCX
        compile_docx(context, docx_path)

        # 3. Actualizar SQLite a 'GENERATED'
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE job_applications
                SET status = 'GENERATED',
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_hash = ?;
                """,
                (job["job_hash"],),
            )

        logger.info(f"📄 CVs compilados para [{job['company']} - {job['title']}]:")
        logger.info(f"   -> PDF:  {pdf_path.name}")
        logger.info(f"   -> DOCX: {docx_path.name}")
        compiled_count += 1

    logger.info(
        f"Compilación completada: {compiled_count} vacantes procesadas con éxito."
    )
    return compiled_count
