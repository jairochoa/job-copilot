"""
Módulo de compilación de currículums ATS (Word .docx y PDF).
Inyecta dinámicamente las viñetas seleccionadas por el motor vectorial (Top K)
garantizando la integridad del documento y la regla de no-vacío.
"""

import json
import logging
import os
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

    def compile_cv(
        self,
        job_id: str,
        job_title: str,
        company_target: str,
        selected_bullet_ids: List[str],
        language: str = "en",
        country_profile: str = "CO",
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
        summary_text = self.cv_data.get("summary", {}).get(lang, "")
        p_summary = doc.add_paragraph(summary_text)
        p_summary.paragraph_format.space_after = Pt(8)

        # 3. Habilidades Técnicas Clave (desde skills_inventory)
        doc.add_heading("TECHNICAL SKILLS" if lang == "en" else "HABILIDADES TÉCNICAS", level=2)
        inv = self.cv_data.get("skills_inventory", {})
        skills_summary = []
        for cat, data in inv.items():
            kws = ", ".join(data.get("keywords", [])[:6])
            display_name = cat.replace("_", " ").title()
            skills_summary.append(f"• {display_name}: {kws}")
        
        for sk_line in skills_summary[:4]:  # Top categorías principales
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