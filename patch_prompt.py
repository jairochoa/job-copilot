import re
from pathlib import Path

p = Path("src/matcher.py")
text = p.read_text(encoding="utf-8")

old_prompt_func = re.search(r'def build_evaluation_prompt\(.*?\n(?=def )', text, re.DOTALL)

new_prompt_func = '''def build_evaluation_prompt(
    job_title: str, company: str, description: str, master_cv: dict[str, Any]
) -> str:
    """Construye el prompt con contexto completo, directivas ejecutivas estrictas y ejemplos few-shot."""
    profile_summary = {
        "candidate": master_cv.get("personal_info", {}).get("name"),
        "education": master_cv.get("education", []),
        "technical_skills": master_cv.get("technical_skills", {}),
        "experience": [
            {
                "company_id": exp.get("company_id"),
                "company": exp.get("company"),
                "title": exp.get("title_formula_a"),
                "bullets": [
                    {"id": b.get("id"), "es": b.get("text_es"), "en": b.get("text_en")}
                    for b in exp.get("bullets", [])
                ],
            }
            for exp in master_cv.get("experience", [])
        ],
    }

    return f"""Eres un Principal Tech Executive y especialista de élite en optimización de CVs para filtros ATS y comités de contratación de Silicon Valley y LATAM.
Evalúa el encaje entre la vacante y el perfil profesional con el más alto estándar de exigencia técnica.

=== VACANTE DE EMPLEO ===
Empresa: {company}
Cargo: {job_title}
Descripción y Requisitos:
{description}

=== PERFIL MAESTRO DEL CANDIDATO (ÚNICA FUENTE DE VERDAD) ===
{json.dumps(profile_summary, ensure_ascii=False, indent=2)}

=== INSTRUCCIONES MANDATORIAS Y EXCLUYENTES ===
1. match_score: Entero del 0 al 100 según afinidad técnica comprobable.
2. hard_skills_matched y missing_skills_gaps: Extrae stacks específicos (ej. "PySpark", "Databricks", "MLflow", "Azure ML").
3. language_detected: 'es' si la vacante está en español, 'en' si está en inglés.
4. tailored_headline: Titular corporativo de alto impacto alineado al cargo (ej. "Senior Data Scientist | Statistical Modeling & Applied AI").
5. REGLAS MANDATORIAS PARA tailored_summary (EXACTAMENTE 3 ORACIONES DENSAS, CERO CLICHÉS, CERO HUMO):
   - ORACIÓN 1 (Perfil de Entrada): Rol Senior de datos + "Magíster en Estadística" (o "Master of Science in Statistics") + "8+ años de experiencia" (o "10+ años" si el cargo es Lead). Si la oferta pide 3+ o 5+, alinear a esa cifra. NUNCA decir "15+" o "20+".
   - ORACIÓN 2 (Stack de Producción): Enumeración limpia de las tecnologías clave de la oferta que el candidato domina (ej. PySpark, Databricks, PyTorch, Azure ML, SQL, arquitecturas LLM).
   - ORACIÓN 3 (Impacto Cuantitativo): Cierre con 1 o 2 métricas reales del perfil (ej. "reducción de tiempos de procesamiento en hasta un 81%", "85.4% de sensibilidad en modelos de visión", o "automatización del 100% de pipelines corporativos").
   - PROHIBICIÓN ABSOLUTA: 
     * PROHIBIDO presentarlo como "estudiante", "en formación" o mencionar carreras de pregrado en curso. El candidato es un Magíster e investigador sénior.
     * PROHIBIDO usar clichés vacíos: "apasionado", "sólida base", "orientado a resultados", "transformar datos", "dispuesto a aprender", "proven track record". Solo métricas, stack y hechos concretos.

=== EJEMPLO DE SUMMARY EN ESPAÑOL (MODELO A REPLICAR) ===
"Científico de Datos Senior y Magíster en Estadística con más de 8 años de trayectoria en modelado predictivo, inferencia y analítica avanzada. Especialista en la construcción de arquitecturas de Machine Learning e ingeniería de datos con Python, SQL, Databricks, PySpark y despliegue en entornos cloud. Ha liderado pipelines de inferencia que optimizaron tiempos de cómputo en un 81% y modelos de clasificación con sensibilidad superior al 85%."

=== EJEMPLO DE SUMMARY EN INGLÉS (MODELO A REPLICAR) ===
"Senior Data Scientist and Master of Science in Statistics with 8+ years of experience leading advanced predictive modeling, machine learning, and quantitative analytics. Proficient in engineering distributed data pipelines and deploying AI solutions using Python, PySpark, Databricks, Azure ML, and SQL. Proven impact delivering end-to-end ML architectures that reduced data processing runtimes by up to 81% and automated 100% of corporate forecasting workflows."

6. selected_bullets: Selecciona entre 2 y 4 IDs EXACTOS de viñetas por empresa que mejor resuenen con los requerimientos técnicos. NUNCA inventes IDs.
7. strategic_fit_rationale: Justificación técnica y concisa del encaje para el reclutador.
"""
'''

if old_prompt_func:
    text = text[:old_prompt_func.start()] + new_prompt_func + text[old_prompt_func.end():]
    p.write_text(text, encoding="utf-8")
    print("build_evaluation_prompt actualizado con éxito.")
else:
    print("No se encontró la función build_evaluation_prompt.")
