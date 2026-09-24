try:
    from google import genai
except Exception:  # noqa: BLE001
    genai = None
"""
Módulo de Evaluación Semántica y Matching (HU-04).
Prefiltro booleano () + Evaluación con gemini-3.6-flash vía HTTP directa con requests.
"""

import json
import os
import re
import time
import unicodedata
from pathlib import Path
from typing import Any

import requests

try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except ImportError:
    pass

from pydantic import BaseModel, Field

from src.database import get_db_connection
from src.logger import logger

BASE_DIR = Path(__file__).resolve().parent.parent
MASTER_CV_PATH = BASE_DIR / "data" / "master_cv.json"
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"


class CompanyBulletsSelection(BaseModel):
    company_id: str = Field(..., description="ID de la empresa según master_cv.json")
    bullet_ids: list[str] = Field(
        default_factory=list,
        description="Lista de IDs de viñetas seleccionadas de esa empresa",
    )


class JobMatchEvaluation(BaseModel):
    model_config = {"populate_by_name": True, "extra": "ignore"}
    match_score: int = Field(
        ...,
        ge=0,
        le=100,
        description="Puntaje de afinidad técnica global entre 0 y 100.",
    )
    language_detected: str = Field(
        default='en',
        alias='language',
        description="Idioma principal de la vacante: 'es' para español o 'en' para inglés.",
    )
    hard_skills_matched: list[str] = Field(
        default_factory=list,
        description="Habilidades y herramientas requeridas presentes en el perfil.",
    )
    missing_skills_gaps: list[str] = Field(
        default_factory=list,
        description="Requisitos técnicos o herramientas que el candidato no domina.",
    )
    tailored_headline: str = Field(
        default='Senior Data Scientist & Applied AI Engineer',
        description="Titular profesional de alto impacto adaptado a la vacante."
    )
    tailored_summary: str = Field(
        ...,
        description=(
            "Resumen profesional ejecutivo de exactamente 3 oraciones densas: "
            "1) Rol Senior/Lead, M.Sc. en Estadística y años calibrados. "
            "2) Stack técnico clave requerido por la vacante y dominado por el candidato. "
            "3) 1 o 2 logros cuantitativos comprobables (métricas, % o tiempos) del perfil maestro. "
            "CERO clichés o adjetivos vacíos (prohibido 'passionate', 'results-driven', 'strong foundation')."
        ),
    )
    selected_bullets: list[CompanyBulletsSelection] = Field(
        default_factory=list,
        description="Lista de selecciones de viñetas agrupadas por empresa.",
    )
    strategic_fit_rationale: str = Field(
        ...,
        description="Breve justificación de cómo la experiencia cubre las necesidades del rol.",
    )


def strip_accents(text: str) -> str:
    nfkd_form = unicodedata.normalize("NFKD", text)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])


CORE_POSITIVE_PATTERNS = [
    r"\bdata\s+(&|and|y)?\s*analytics\b",
    r"\b(data\s+scientist|cientific[ao]\s+de\s+datos)\b",
    r"\b(data\s+analyst|analista\s+de\s+datos)\b",
    r"\b(data\s+engineer|ingenier[ao]\s+de\s+datos)\b",
    r"\b(analytics|analitica)\b",
    r"\bmachine\s+learning\b",
    r"\b(aprendizaje\s+automatico|modelos\s+predictivos)\b",
    r"\b(ai|ia)\s+(engineer|developer|consultant)\b",
    r"\bapplied\s+ai\b",
    r"\b(llm|nlp|vision\s+artificial|computer\s+vision)\b",
    r"\b(deep\s+learning|pytorch|scikit-learn|xgboost|lightgbm)\b",
    r"\b(estadistic[ao]|statistic(s|ian)?)\b",
    r"\b(databricks|pyspark|delta\s+lake|microsoft\s+fabric)\b",
    r"\bpower\s*bi\b",
    r"\bbusiness\s+intelligence\b",
]

DISQUALIFYING_PATTERNS = [
    r"\b(lead|senior|junior|staff)?\s*python\s+(developer|engineer|software\s+engineer|backend)\b",
    r"\b(java|dotnet|\.net|c#|golang|rust)\s+(developer|backend|engineer)\b",
    r"\bphp(\s+developer)?\b",
    r"\bfrontend\s+(developer|engineer|react|angular|vue)\b",
    r"\bfullstack\s+(developer|engineer)\b",
    r"\bsoftware\s+engineer\b",
    r"\bqa\s+(automation|tester|manual)\b",
    r"\b(scrum\s+master|product\s+owner)\b",
    r"\b(televentas|call\s+center|asistente\s+administrativo)\b",
]


def apply_boolean_prefilter(title: str, description: str) -> tuple[bool, str]:
    raw_title = title.lower()
    raw_corpus = f"{title}\n{description}".lower()
    clean_title = strip_accents(raw_title)
    text_corpus = strip_accents(raw_corpus)

    for neg_pattern in DISQUALIFYING_PATTERNS:
        match_title = re.search(neg_pattern, clean_title)
        if match_title:
            return False, f"Descartada por rol antagónico en título: '{match_title.group(0)}'"

    for neg_pattern in DISQUALIFYING_PATTERNS:
        match_desc = re.search(neg_pattern, text_corpus)
        if match_desc and not any(re.search(p, clean_title) for p in CORE_POSITIVE_PATTERNS):
            return False, f"Descartada por término antagónico detectado: '{match_desc.group(0)}'"

    matched_positives = []
    for pos_pattern in CORE_POSITIVE_PATTERNS:
        match = re.search(pos_pattern, text_corpus)
        if match:
            matched_positives.append(match.group(0))

    if not matched_positives:
        return False, "Descartada: no contiene términos del núcleo de datos/analítica."

    return True, f"Aprobada para LLM. Términos detectados: {', '.join(set(matched_positives))}"


def run_heuristic_filter_batch() -> int:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT job_hash, title, company, description FROM job_applications WHERE status = 'SCRAPED';")
        pending_jobs = [dict(row) for row in cursor.fetchall()]

    if not pending_jobs:
        logger.info("No hay vacantes pendientes en estado 'SCRAPED' para prefiltrar.")
        return 0

    logger.info(f"Aplicando prefiltro booleano a {len(pending_jobs)} vacantes...")
    filtered_out_count = 0
    approved_count = 0

    for job in pending_jobs:
        passes, reason = apply_boolean_prefilter(job["title"], job["description"])
        if not passes:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE job_applications
                    SET status = 'FILTERED_OUT', match_score = 0, updated_at = CURRENT_TIMESTAMP
                    WHERE job_hash = ?;
                    """,
                    (job["job_hash"],),
                )
            logger.info(f"🚫 [{job['company']} - {job['title']}] -> {reason}")
            filtered_out_count += 1
        else:
            logger.info(f"✅ [{job['company']} - {job['title']}] -> {reason}")
            approved_count += 1

    logger.info(f"Prefiltro completado: {approved_count} aprobadas, {filtered_out_count} descartadas ().")
    return filtered_out_count


def load_master_cv() -> dict[str, Any]:
    if not MASTER_CV_PATH.exists():
        raise FileNotFoundError(f"No se encontró el archivo maestro en: {MASTER_CV_PATH}")
    with open(MASTER_CV_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def build_evaluation_prompt(
    job_title: str, company: str, description: str, master_cv: dict[str, Any]
) -> str:
    """Construye el prompt con contexto completo, directivas ejecutivas estrictas y ponderación cuantitativa."""
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

=== RÚBRICA DE EVALUACIÓN Y CÁLCULO DE SCORE (ESCALA 0-100 CON PESOS ESTRICTOS) ===
Debes calcular el campo `match_score` como un entero (0 a 100) aplicando estrictamente la siguiente suma ponderada:

1. Alineación Técnica y Stack Requerido (Peso: 40% | Máximo: 40 puntos):
   - Coincidencia demostrable en herramientas y lenguajes clave requeridos por la vacante (Python, SQL, PySpark, scikit-learn, LightGBM, XGBoost, Databricks, Azure ML, arquitecturas LLM, cloud pipelines).
   - Penalización drástica (-20 a -25 pts) si la vacante exige como requisito excluyente tecnologías totalmente ajenas al perfil (ej. desarrollo frontend React/Angular, desarrollo móvil nativo en iOS/Android o soporte administrativo no analítico).

2. Nivel Académico y Rigor Cuantitativo (Peso: 25% | Máximo: 25 puntos):
   - 25 pts: La oferta demanda o valora formación avanzada de posgrado en áreas cuantitativas (Magíster en Estadística / M.Sc. in Statistics, Matemáticas Aplicadas, Ciencia de Datos cuantitativa).
   - 10 a 15 pts: La oferta requiere únicamente pregrado estándar con análisis descriptivo genérico.
   - 0 pts: Rol estrictamente desalineado del perfil cuantitativo/estadístico.

3. Seniority y Alcance del Cargo (Peso: 20% | Máximo: 20 puntos):
   - Calce entre la trayectoria senior demostrada del candidato (liderazgo técnico de iniciativas de datos, consultoría analítica estratégica, diseño de sistemas de machine learning en producción) y el nivel jerárquico demandado por el puesto vs. tareas puramente operativas de soporte junior.

4. Impacto de Negocio y Casos de Éxito Cuantificables (Peso: 15% | Máximo: 15 puntos):
   - Afinidad entre los retos del rol y los logros documentados del candidato con impacto económico y operativo medible (optimización de costos, reducción de tiempos computacionales, modelos predictivos y detección de anomalías).

=== INSTRUCCIONES MANDATORIAS Y EXCLUYENTES ===
1. match_score: Entero del 0 al 100 resultante de la suma matemática exacta de los 4 ejes de la rúbrica anterior.
2. hard_skills_matched y missing_skills_gaps: Extrae stacks específicos (ej. "PySpark", "Databricks", "MLflow", "Azure ML").
3. language_detected: 'es' si la vacante está en español, 'en' si está en inglés.
4. tailored_headline: Titular corporativo de alto impacto alineado al cargo (ej. "Senior Data Scientist | Statistical Modeling & Applied AI").
5. REGLAS MANDATORIAS PARA tailored_summary (EXACTAMENTE 3 ORACIONES DENSAS, CERO CLICHÉS, CERO HUMO):
   - ORACIÓN 1 (Perfil de Entrada): Rol Senior de datos + "Magíster en Estadística" (o "Master of Science in Statistics") + "8+ años de experiencia" (o "10+ años" si el cargo es Lead). Si la oferta pide 3+ o 5+, alinear a esa cifra. NUNCA menciones "15+", "20+".
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
7. strategic_fit_rationale: Justificación técnica y concisa que detalle el desglose de los puntos asignados en la rúbrica y el encaje global para el reclutador.
"""

def evaluate_single_job(
    job_record: dict[str, Any],
    api_key: str | None = None,
    model_name: str | None = None,
    max_retries: int = 3,
) -> JobMatchEvaluation | None:
    gemini_key = api_key or os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        logger.error("Variable GEMINI_API_KEY no configurada.")
        return None

    model = model_name or DEFAULT_GEMINI_MODEL
    master_cv = load_master_cv()
    prompt = build_evaluation_prompt(
        job_title=job_record.get("title", ""),
        company=job_record.get("company", ""),
        description=job_record.get("description", ""),
        master_cv=master_cv,
    )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {"Content-Type": "application/json"}
    params = {"key": gemini_key}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.1,
        },
    }

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(url, params=params, headers=headers, json=payload, timeout=90)
            if response.status_code in (429, 503) and attempt < max_retries:
                wait_time = 5 * attempt
                logger.warning(f"Servidor ocupado ({response.status_code}). Reintentando en {wait_time}s...")
                time.sleep(wait_time)
                continue

            if response.status_code != 200:
                logger.error(f"Error de API Gemini ({response.status_code}): {response.text}")
                return None

            result_data = response.json()
            candidates = result_data.get("candidates", [])
            if not candidates:
                logger.error("Gemini no retornó candidatos.")
                return None

            raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            evaluation = JobMatchEvaluation.model_validate_json(raw_text)
            logger.info(
                f"Evaluación Gemini exitosa ({model}): {job_record.get('company')} - "
                f"{job_record.get('title')} | Score: {evaluation.match_score}/100"
            )
            return evaluation
        except Exception as e:  # noqa: BLE001
            logger.error(f"Error evaluando vacante con Gemini: {e}", exc_info=True)
            return None

def run_gemini_evaluation_batch(
    min_score_threshold: int = 60,
    max_batch_size: int = 10,
    delay_between_calls: float = 4.5,
) -> int:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM job_applications WHERE status = 'SCRAPED' LIMIT ?;",
            (max_batch_size,),
        )
        pending_jobs = [dict(row) for row in cursor.fetchall()]

    if not pending_jobs:
        logger.info("No hay vacantes pendientes en estado 'SCRAPED' para evaluar con Gemini.")
        return 0

    current_model = DEFAULT_GEMINI_MODEL
    logger.info(
        f"Evaluando lote de {len(pending_jobs)} vacantes con Gemini ({current_model}) "
        f"[Pausa de seguridad: {delay_between_calls}s entre llamadas]..."
    )
    evaluated_count = 0

    for idx, job in enumerate(pending_jobs):
        if idx > 0:
            logger.info(f"Pausa de seguridad ({delay_between_calls}s)...")
            time.sleep(delay_between_calls)

        eval_result = evaluate_single_job(job, model_name=current_model)
        if not eval_result:
            continue

        new_status = "SCORED" if eval_result.match_score >= min_score_threshold else "DISCARDED"
        bullets_map = {item.company_id: item.bullet_ids for item in eval_result.selected_bullets}

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE job_applications
                SET match_score = ?,
                    score_rationale = ?,
                    tailored_headline = ?,
                    tailored_summary = ?,
                    selected_bullet_ids = ?,
                    raw_analysis_json = ?,
                    language = ?,
                    status = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_hash = ?;
                """,
                (
                    eval_result.match_score,
                    getattr(eval_result, 'strategic_fit_rationale', getattr(eval_result, 'score_rationale', '')),
                    eval_result.tailored_headline,
                    eval_result.tailored_summary,
                    json.dumps(bullets_map, ensure_ascii=False),
                    eval_result.model_dump_json(),
                    eval_result.language_detected,
                    new_status,
                    job["job_hash"],
                ),
            )
        evaluated_count += 1

    logger.info(f"Lote finalizado: {evaluated_count} vacantes evaluadas y persistidas.")
    return evaluated_count
