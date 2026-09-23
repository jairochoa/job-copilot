"""
Módulo de Compilación de CVs (HU-05).
Mapea el esquema canónico de data/master_cv.json (profiles, experience_bullets_pool,
education, certifications, skills) hacia PDF (Playwright) y DOCX (python-docx).
Incluye localización estricta de fechas y traducción técnica bilingüe de skills.
"""

import json
import re
from collections import OrderedDict
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

# Diccionario de traducción técnica para habilidades
SKILLS_ES_TO_EN = {
    "análisis multivariante": "Multivariate Analysis",
    "analisis multivariante": "Multivariate Analysis",
    "bioestadística": "Biostatistics",
    "bioestadistica": "Biostatistics",
    "análisis de supervivencia": "Survival Analysis",
    "analisis de supervivencia": "Survival Analysis",
    "diseño experimental": "Design of Experiments (DoE)",
    "diseno experimental": "Design of Experiments (DoE)",
    "inferencia bayesiana": "Bayesian Inference",
    "series de tiempo": "Time Series Forecasting",
    "series temporales": "Time Series Forecasting",
    "aprendizaje supervisado": "Supervised Learning",
    "aprendizaje no supervisado": "Unsupervised Learning",
    "modelado estadístico": "Statistical Modeling",
    "modelado estadistico": "Statistical Modeling",
    "aprendizaje automático": "Machine Learning",
    "aprendizaje automatico": "Machine Learning",
}

# Diccionario para localización de fechas
MONTHS_ES_TO_EN = {
    "ene": "Jan",
    "feb": "Feb",
    "mar": "Mar",
    "abr": "Apr",
    "may": "May",
    "jun": "Jun",
    "jul": "Jul",
    "ago": "Aug",
    "sep": "Sep",
    "set": "Sep",
    "oct": "Oct",
    "nov": "Nov",
    "dic": "Dec",
    "actualidad": "Present",
    "presente": "Present",
}


def sanitize_filename(name: str) -> str:
    """Limpia caracteres inválidos para rutas de archivo."""
    return re.sub(r"[^\w\-_\. ]", "_", name).strip()


def load_master_cv() -> dict[str, Any]:
    with open(MASTER_CV_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def resolve_bilingual_field(field_val: Any, lang: str) -> str:
    """Extrae la cadena correcta según el idioma si es diccionario {'es':..., 'en':...}."""
    if isinstance(field_val, dict):
        return field_val.get(lang) or field_val.get("en") or field_val.get("es") or ""
    return str(field_val) if field_val is not None else ""


def localize_period_str(period: str, lang: str) -> str:
    """Traduce meses y términos de vigencia al idioma objetivo."""
    if not period or lang == "es":
        return period

    result = period
    for es_term, en_term in MONTHS_ES_TO_EN.items():
        pattern = re.compile(rf"\b{es_term}\b", re.IGNORECASE)
        result = pattern.sub(en_term, result)

    # Reemplazo de palabras clave
    result = re.sub(r"\bactualidad\b", "Present", result, flags=re.IGNORECASE)
    result = re.sub(r"\bpresente\b", "Present", result, flags=re.IGNORECASE)
    return result


def localize_skill_name(skill: str, lang: str) -> str:
    """Traduce un skill técnico si el idioma es inglés."""
    if lang == "es":
        return skill
    clean_k = skill.strip().lower()
    return SKILLS_ES_TO_EN.get(clean_k, skill)


def prepare_cv_context(
    job_record: dict[str, Any], master_cv: dict[str, Any]
) -> dict[str, Any]:
    """Ensambla y normaliza todos los bloques para Jinja2 y python-docx."""
    lang = job_record.get("language", "en")

    profiles = master_cv.get("profiles", {})
    profile = profiles.get("CO") or list(profiles.values())[0]

    # Parsing de viñetas seleccionadas por Gemini
    raw_bullets_json = job_record.get("selected_bullet_ids")
    selected_bullet_ids = set()
    if raw_bullets_json:
        try:
            parsed = json.loads(raw_bullets_json)
            if isinstance(parsed, dict):
                for b_list in parsed.values():
                    if isinstance(b_list, list):
                        selected_bullet_ids.update(b_list)
            elif isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict) and "bullet_ids" in item:
                        selected_bullet_ids.update(item["bullet_ids"])
                    elif isinstance(item, str):
                        selected_bullet_ids.add(item)
        except Exception:
            pass

    # Procesar experience_bullets_pool agrupando por empresa
    bullets_pool = master_cv.get("experience_bullets_pool", [])
    grouped_jobs: dict[str, dict[str, Any]] = OrderedDict()

    for item in bullets_pool:
        comp = item.get("company", "Experiencia Profesional")
        role = resolve_bilingual_field(item.get("standard_role"), lang) or item.get(
            "official_title", ""
        )
        raw_period = item.get("period", "")
        period = localize_period_str(raw_period, lang)
        key = f"{comp}|{role}|{period}"

        if key not in grouped_jobs:
            grouped_jobs[key] = {
                "company": comp,
                "title": role,
                "period": period,
                "bullets": [],
                "all_available_bullets": [],
            }

        bullet_text = resolve_bilingual_field(item.get("text"), lang)
        grouped_jobs[key]["all_available_bullets"].append(bullet_text)

        if not selected_bullet_ids or item.get("id") in selected_bullet_ids:
            grouped_jobs[key]["bullets"].append(bullet_text)

    # Fallback si un rol no tiene viñetas elegidas
    experience_list = []
    for job_data in grouped_jobs.values():
        if not job_data["bullets"]:
            job_data["bullets"] = job_data["all_available_bullets"][:2]
        experience_list.append(job_data)

    # Educación con periodos localizados
    education_list = []
    for edu in master_cv.get("education", []):
        edu_period = resolve_bilingual_field(edu.get("period"), lang)
        education_list.append(
            {
                "degree": resolve_bilingual_field(edu.get("degree"), lang),
                "institution": edu.get("institution", ""),
                "period": localize_period_str(edu_period, lang),
            }
        )

    # Certificaciones relevantes
    cert_list = []
    for c in master_cv.get("certifications", []):
        c_name = resolve_bilingual_field(c.get("name"), lang)
        cert_list.append(
            {
                "name": c_name,
                "issuer": c.get("issuer", ""),
                "year": c.get("year", ""),
            }
        )

    # Competencias técnicas con traducción profunda
    skills_dict = {}
    raw_skills = master_cv.get("skills", {})
    if isinstance(raw_skills, dict):
        mapping_es = {
            "machine_learning_ai": "Modelado e IA",
            "data_engineering_cloud": "Datos y Cloud",
            "statistical_modeling": "Estadística Avanzada",
            "languages": "Lenguajes",
            "devops_tools": "DevOps & MLOps",
        }
        mapping_en = {
            "machine_learning_ai": "ML & Applied AI",
            "data_engineering_cloud": "Data & Cloud",
            "statistical_modeling": "Statistical Modeling",
            "languages": "Languages",
            "devops_tools": "DevOps & MLOps",
        }
        mapping = mapping_es if lang == "es" else mapping_en

        for k, items in raw_skills.items():
            if k == "soft_skills":
                continue
            cat_label = mapping.get(k, k.replace("_", " ").title())
            if isinstance(items, list):
                translated_items = [localize_skill_name(it, lang) for it in items]
                skills_dict[cat_label] = ", ".join(translated_items)

    return {
        "language": lang,
        "personal": profile,
        "tailored_headline": job_record.get("tailored_headline")
        or resolve_bilingual_field(profile.get("professional_title"), lang),
        "tailored_summary": job_record.get("tailored_summary") or "",
        "experience": experience_list,
        "education": education_list,
        "certifications": cert_list[:8],
        "skills": skills_dict,
    }


def compile_pdf_with_playwright(html_content: str, output_path: Path) -> None:
    """Renderiza PDF limpio y listo para ATS con Playwright."""
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
    """Genera documento DOCX compatible con parsers ATS."""
    doc = Document()

    for s in doc.sections:
        s.top_margin = Inches(0.55)
        s.bottom_margin = Inches(0.55)
        s.left_margin = Inches(0.65)
        s.right_margin = Inches(0.65)

    personal = context["personal"]
    lang = context["language"]

    title_p = doc.add_paragraph()
    r_name = title_p.add_run(personal.get("full_name", ""))
    r_name.font.size = Pt(17)
    r_name.font.bold = True
    r_name.font.color.rgb = RGBColor(15, 23, 42)
    title_p.paragraph_format.space_after = Pt(2)

    h_p = doc.add_paragraph()
    r_head = h_p.add_run(context.get("tailored_headline", ""))
    r_head.font.size = Pt(10.5)
    r_head.font.bold = True
    r_head.font.color.rgb = RGBColor(29, 78, 216)
    h_p.paragraph_format.space_after = Pt(3)

    c_p = doc.add_paragraph()
    contact_parts = [
        personal.get("location", ""),
        personal.get("phone", ""),
        personal.get("email", ""),
        "linkedin.com/in/jairochoa",
        "github.com/jairochoa",
    ]
    r_cont = c_p.add_run(" | ".join([p for p in contact_parts if p]))
    r_cont.font.size = Pt(8.8)
    r_cont.font.color.rgb = RGBColor(71, 85, 105)
    c_p.paragraph_format.space_after = Pt(8)

    def add_section_header(title: str):
        sec_p = doc.add_paragraph()
        r_sec = sec_p.add_run(title.upper())
        r_sec.font.size = Pt(10.5)
        r_sec.font.bold = True
        r_sec.font.color.rgb = RGBColor(15, 23, 42)
        sec_p.paragraph_format.space_before = Pt(6)
        sec_p.paragraph_format.space_after = Pt(3)

    add_section_header(
        "RESUMEN PROFESIONAL" if lang == "es" else "PROFESSIONAL SUMMARY"
    )
    s_p = doc.add_paragraph(context.get("tailored_summary", ""))
    s_p.paragraph_format.space_after = Pt(6)

    add_section_header(
        "EXPERIENCIA PROFESIONAL" if lang == "es" else "PROFESSIONAL EXPERIENCE"
    )
    for exp in context.get("experience", []):
        job_p = doc.add_paragraph()
        r_role = job_p.add_run(f"{exp['title']} — {exp['company']}")
        r_role.font.bold = True
        job_p.add_run(f" ({exp['period']})")
        job_p.paragraph_format.space_after = Pt(1)

        for b in exp.get("bullets", []):
            b_p = doc.add_paragraph(b, style="List Bullet")
            b_p.paragraph_format.space_after = Pt(1.5)

    add_section_header("EDUCACIÓN SUPERIOR" if lang == "es" else "HIGHER EDUCATION")
    for edu in context.get("education", []):
        doc.add_paragraph(f"{edu['degree']} — {edu['institution']} ({edu['period']})")

    doc.save(str(output_path))


def build_applications_batch() -> int:
    """Compila PDFs y DOCXs para vacantes en estado 'SCORED' o 'GENERATED'."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    master_cv = load_master_cv()

    with open(TEMPLATE_HTML_PATH, "r", encoding="utf-8") as f:
        html_template = Template(f.read())

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM job_applications WHERE status IN ('SCORED', 'GENERATED');"
        )
        jobs_to_compile = [dict(row) for row in cursor.fetchall()]

    if not jobs_to_compile:
        logger.info("No hay vacantes calificadas para compilar.")
        return 0

    logger.info(f"Recompilando {len(jobs_to_compile)} CVs con localización completa...")
    count = 0

    for job in jobs_to_compile:
        context = prepare_cv_context(job, master_cv)
        rendered_html = html_template.render(**context)

        company_clean = sanitize_filename(job["company"])
        base_name = f"CV_Jairo_Ochoa_{company_clean}_{job['job_hash'][:6]}"

        pdf_path = OUTPUT_DIR / f"{base_name}.pdf"
        docx_path = OUTPUT_DIR / f"{base_name}.docx"

        compile_pdf_with_playwright(rendered_html, pdf_path)
        compile_docx(context, docx_path)

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE job_applications
                SET status = 'GENERATED', updated_at = CURRENT_TIMESTAMP
                WHERE job_hash = ?;
                """,
                (job["job_hash"],),
            )

        logger.info(f"✅ [{job['company']}] -> {pdf_path.name}")
        count += 1

    return count
