"""
Módulo de compilación de currículums ATS (Word .docx y PDF).
Inyecta dinámicamente las viñetas seleccionadas por el motor vectorial (Top K)
garantizando la integridad del documento y la regla de no-vacío.
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

from src.config import settings

logger = logging.getLogger(__name__)


class ATSResumeCompiler:
    def __init__(self, master_cv_path: Path = settings.MASTER_CV_PATH):
        self.master_cv_path = master_cv_path
        with open(self.master_cv_path, "r", encoding="utf-8") as f:
            self.cv_data: Dict[str, Any] = json.load(f)

    def _select_bullets_for_role(
        self,
        company: str,
        selected_ids: List[str],
        max_bullets: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Filtra viñetas para una empresa específica usando los IDs del motor RAG.
        Garantiza la regla de no-vacío usando default_priority como fallback.
        """
        all_pool = self.cv_data.get("experience_bullets_pool", [])
        company_bullets = [b for b in all_pool if b.get("company") == company]

        # 1. Viñetas que coincidieron en la selección del Top K
        matched = [b for b in company_bullets if b.get("id") in selected_ids]

        # 2. Si no hubo matches o hay muy pocas, completar con default_priority
        if len(matched) < 2:
            remaining = [b for b in company_bullets if b not in matched]
            remaining_sorted = sorted(
                remaining, key=lambda x: x.get("default_priority", 99)
            )
            for b in remaining_sorted:
                matched.append(b)
                if len(matched) >= 2:
                    break

        return matched[:max_bullets]

    def _build_tailored_summary(
        self,
        job_title: str,
        requirements: Optional[Any],
        lang: str,
        base_summary: str,
    ) -> str:
        """
        Construye un resumen profesional personalizado según el rol objetivo y las habilidades requeridas.
        """
        if not requirements:
            return base_summary

        m_skills = getattr(requirements, "mandatory_hard_skills", None)
        if m_skills is None and isinstance(requirements, dict):
            m_skills = requirements.get("mandatory_hard_skills", [])

        if not m_skills:
            return base_summary

        clean_skills = [s.strip() for s in m_skills if len(s.strip()) > 1]
        top_skills = clean_skills[:4]
        skills_str = ", ".join(top_skills) if top_skills else ""

        target_title = (
            job_title.strip()
            if job_title and job_title.strip()
            else ("Senior Data Scientist" if lang == "en" else "Científico de Datos Senior")
        )

        if lang == "en":
            prefix = f"{target_title} with an M.Sc. in Statistics and 7+ years of experience leading predictive modeling, advanced analytics, and AI integration in production environments."
            if skills_str:
                skills_clause = f" Proven expertise in {skills_str}, with a focus on operational efficiency and scalable solutions."
            else:
                skills_clause = ""
            return f"{prefix}{skills_clause}"
        else:
            prefix = f"{target_title} con Maestría en Estadística y más de 7 años de experiencia liderando el modelado predictivo, analítica avanzada e integración de Inteligencia Artificial en entornos productivos."
            if skills_str:
                skills_clause = f" Especialista en {skills_str}, con enfoque riguroso en optimización operativa, reproducibilidad y visión de negocio."
            else:
                skills_clause = ""
            return f"{prefix}{skills_clause}"

    def _build_tailored_skills_section(
        self,
        requirements: Optional[Any],
    ) -> List[str]:
        """
        Filtra, califica y reordena las categorías e ítems de skills_inventory según las
        habilidades requeridas por la vacante (mandatory_hard_skills y nice_to_have_skills).
        """
        inv = self.cv_data.get("skills_inventory", {})
        if not inv:
            return []

        req_skills = []
        if requirements:
            m_skills = getattr(requirements, "mandatory_hard_skills", None)
            if m_skills is None and isinstance(requirements, dict):
                m_skills = requirements.get("mandatory_hard_skills", [])
            nth_skills = getattr(requirements, "nice_to_have_skills", None)
            if nth_skills is None and isinstance(requirements, dict):
                nth_skills = requirements.get("nice_to_have_skills", [])
            raw_skills = (m_skills or []) + (nth_skills or [])
            req_skills = [s.strip().lower() for s in raw_skills if s and s.strip()]

        scored_categories = []
        for idx, (cat, data) in enumerate(inv.items()):
            display_name = cat.replace("_", " ").title()
            keywords = list(data.get("keywords", []))

            if req_skills:
                matched_kws = []
                other_kws = []
                score = 0
                for kw in keywords:
                    kw_lower = kw.lower()
                    if any(kw_lower in rs or rs in kw_lower for rs in req_skills):
                        matched_kws.append(kw)
                        score += 2
                    else:
                        other_kws.append(kw)
                ordered_kws = matched_kws + other_kws
            else:
                ordered_kws = keywords
                score = 0

            kws_str = ", ".join(ordered_kws[:6])
            scored_categories.append((score, -idx, f"• {display_name}: {kws_str}"))

        if req_skills:
            scored_categories.sort(key=lambda x: (x[0], x[1]), reverse=True)

        return [line for _, _, line in scored_categories[:4]]

    def compile(
        self,
        job_id: str = "0",
        job_title: str = "",
        company_target: str = "",
        selected_bullet_ids: Optional[List[str]] = None,
        language: str = "en",
        country_profile: str = "CO",
        **kwargs,
    ) -> Dict[str, str]:
        """
        Método de conveniencia y compatibilidad que invoca compile_cv aceptando parámetros alternativos.
        """
        target_role = kwargs.get("target_role") or kwargs.get("title") or job_title
        target_company = kwargs.get("target_company") or kwargs.get("company") or company_target
        reqs = kwargs.get("requirements")
        if reqs and hasattr(reqs, "language"):
            language = reqs.language
        country_profile = kwargs.get("country_code") or country_profile

        return self.compile_cv(
            job_id=str(job_id),
            job_title=target_role,
            company_target=target_company,
            selected_bullet_ids=selected_bullet_ids or [],
            language=language,
            country_profile=country_profile,
            requirements=reqs,
        )

    def compile_cv(
        self,
        job_id: str,
        job_title: str,
        company_target: str,
        selected_bullet_ids: List[str],
        language: str = "en",
        country_profile: str = "CO",
        requirements: Optional[Any] = None,
    ) -> Dict[str, str]:
        """
        Genera el documento Word ATS-friendly formateado y preparado para exportar.
        Retorna un diccionario con las rutas generadas: {'docx': path, 'pdf': path}.
        """
        lang = "en" if language.lower().startswith("en") else "es"
        profile = self.cv_data.get("profiles", {}).get(country_profile, self.cv_data["profiles"]["CO"])

        doc = Document()

        # Ajuste de márgenes estándar ATS (0.6 pulgadas)
        for section in doc.sections:
            section.top_margin = Inches(0.6)
            section.bottom_margin = Inches(0.6)
            section.left_margin = Inches(0.6)
            section.right_margin = Inches(0.6)

        # 1. Encabezado de Contacto
        title_p = doc.add_paragraph()
        title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        name_run = title_p.add_run(profile.get("full_name", "").upper())
        name_run.bold = True
        name_run.font.size = Pt(16)
        name_run.font.color.rgb = RGBColor(0x1A, 0x36, 0x5D)

        role_p = doc.add_paragraph()
        role_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        prof_title = profile.get("professional_title", {}).get(lang, "")
        role_run = role_p.add_run(prof_title)
        role_run.font.size = Pt(11)
        role_run.bold = True
        role_run.font.color.rgb = RGBColor(0x2B, 0x6C, 0xB0)

        contact_p = doc.add_paragraph()
        contact_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        contact_text = (
            f"{profile.get('location')} | {profile.get('phone')} | {profile.get('email')} | "
            f"LinkedIn: {profile.get('linkedin')}"
        )
        contact_run = contact_p.add_run(contact_text)
        contact_run.font.size = Pt(9.5)

        # 2. Resumen Profesional
        doc.add_heading("PROFESSIONAL SUMMARY" if lang == "en" else "RESUMEN PROFESIONAL", level=2)
        base_summary = self.cv_data.get("summary", {}).get(lang, "")
        summary_text = self._build_tailored_summary(job_title, requirements, lang, base_summary)
        p_summary = doc.add_paragraph(summary_text)
        p_summary.paragraph_format.space_after = Pt(8)

        # 3. Habilidades Técnicas Clave (desde skills_inventory dinámico)
        doc.add_heading("TECHNICAL SKILLS" if lang == "en" else "HABILIDADES TÉCNICAS", level=2)
        skills_summary = self._build_tailored_skills_section(requirements)
        
        for sk_line in skills_summary:
            p_sk = doc.add_paragraph(sk_line)
            p_sk.paragraph_format.space_after = Pt(2)

        # 4. Experiencia Laboral con viñetas seleccionadas Top K
        doc.add_heading("WORK EXPERIENCE" if lang == "en" else "EXPERIENCIA LABORAL", level=2)
        
        # Obtener empresas únicas ordenadas de la más reciente a la más antigua
        seen_companies = []
        for b in self.cv_data.get("experience_bullets_pool", []):
            comp = b.get("company")
            if comp not in seen_companies:
                seen_companies.append(comp)

        for comp in seen_companies:
            bullets = self._select_bullets_for_role(comp, selected_bullet_ids, max_bullets=3)
            if not bullets:
                continue

            first_bullet = bullets[0]
            role_title = first_bullet.get("standard_role", {}).get(lang, first_bullet.get("official_title", ""))
            period = first_bullet.get("period", "")

            # Encabezado del Rol
            exp_p = doc.add_paragraph()
            role_run = exp_p.add_run(f"{role_title} — {comp}")
            role_run.bold = True
            role_run.font.size = Pt(10.5)

            period_p = doc.add_paragraph()
            period_run = period_p.add_run(period)
            period_run.italic = True
            period_run.font.size = Pt(9.5)
            period_p.paragraph_format.space_after = Pt(3)

            # Inyectar las viñetas seleccionadas
            for b in bullets:
                bullet_text = b.get("text", {}).get(lang, "")
                stack_list = b.get("stack", [])
                stack_str = f" [Stack: {', '.join(stack_list[:4])}]" if stack_list else ""
                
                bp = doc.add_paragraph(style="List Bullet")
                bp.paragraph_format.space_after = Pt(2)
                bp.add_run(bullet_text)
                if stack_str:
                    stack_run = bp.add_run(stack_str)
                    stack_run.font.size = Pt(8.5)
                    stack_run.italic = True
                    stack_run.font.color.rgb = RGBColor(0x71, 0x80, 0x96)

        # 5. Educación
        doc.add_heading("EDUCATION" if lang == "en" else "EDUCACIÓN", level=2)
        for edu in self.cv_data.get("education", []):
            deg = edu.get("degree", {}).get(lang, "")
            inst = edu.get("institution", "")
            period = edu.get("period", {}).get(lang, "")
            ep = doc.add_paragraph()
            ep.paragraph_format.space_after = Pt(2)
            deg_run = ep.add_run(f"• {deg} — {inst} ({period})")
            deg_run.font.size = Pt(9.5)

        # Asegurar directorio de salida
        settings.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        docx_filename = f"CV_Jairo_Ochoa_{company_target.replace(' ', '_')}_{job_id[:8]}.docx"
        docx_path = settings.OUTPUT_DIR / docx_filename

        doc.save(str(docx_path))
        logger.info(f"CV generado exitosamente en: {docx_path}")

        # Conversión a PDF nativo
        pdf_path = docx_path.with_suffix(".pdf")
        pdf_generated = ""
        try:
            from docx2pdf import convert

            convert(str(docx_path), str(pdf_path))
            if pdf_path.exists():
                pdf_generated = str(pdf_path)
                logger.info(f"CV .pdf exportado exitosamente en: {pdf_path}")
        except Exception as e:
            logger.warning(
                f"No se pudo exportar automáticamente a PDF: {e}. El .docx sigue disponible."
            )

        return {
            "docx": str(docx_path),
            "pdf": "",  # Integrable con docx2pdf en Windows si está habilitado Word
        }

def sanitize_filename(name: str) -> str:
    """Limpia caracteres inválidos para nombres de archivo en Windows."""
    clean = re.sub(r'[\\/*?:"<>|]', "", name)
    return clean.replace(" ", "_").strip()


def determine_country_profile(
    location: str = "", country_detected: str = "", target_profile: str = ""
) -> str:
    """
    Determina el código del perfil de país (VE o CO) según las reglas:
    1. Si la vacante es en territorio venezolano -> Usar perfil VE del master_cv.json.
    2. Si es Colombia o cualquier país fuera de Colombia -> Usar perfil CO del master_cv.json.
    """
    loc_text = f"{location} {country_detected}".lower()
    if (
        "venezuela" in loc_text
        or "mérida" in loc_text
        or "caracas" in loc_text
        or str(target_profile).upper() == "VE"
    ):
        return "VE"
    return "CO"


def prepare_cv_context(
    language: str = "es", selected_bullet_ids: Optional[List[str]] = None
) -> dict:
    """Helper de compatibilidad que invoca el compilador ATS."""
    compiler = ATSResumeCompiler()
    return compiler.cv_data

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("--- TEST DEL COMPILADOR ATS ---")
    compiler = ATSResumeCompiler()

    # Viñetas simuladas devueltas por el matcher
    sample_bullets = ["exp_free_01", "exp_idata_01", "exp_idata_05", "exp_banco_02"]
    out_paths = compiler.compile_cv(
        job_id="test_job_12345",
        job_title="Senior Data Scientist",
        company_target="MercadoLibre",
        selected_bullet_ids=sample_bullets,
        language="en",
    )
    print(f"Resultado: {out_paths}")