"""
Módulo de Evaluación Semántica y Matching.
- HU-04 / Actividad 4.1: Prefiltro booleano por reglas duras locales (costo $0).
- HU-04 / Actividad 4.2: Evaluación semántica con Gemini API, control de tasa (15 RPM)
  y calibración de años de experiencia para mitigación de sobrecualificación.
"""

import json
import os
import re
import time
import unicodedata
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from google import genai
from google.genai import types
from google.genai.errors import APIError
from pydantic import BaseModel, Field

from src.database import get_db_connection
from src.logger import logger

BASE_DIR = Path(__file__).resolve().parent.parent
MASTER_CV_PATH = BASE_DIR / "data" / "master_cv.json"
DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")


class CompanyBulletsSelection(BaseModel):
    """Mapeo fuertemente tipado para evitar additionalProperties en la API."""

    company_id: str = Field(..., description="ID de la empresa según master_cv.json")
    bullet_ids: list[str] = Field(
        default_factory=list,
        description="Lista de IDs de viñetas seleccionadas de esa empresa",
    )


class JobMatchEvaluation(BaseModel):
    """Esquema estructurado generado por Gemini para cada vacante."""

    match_score: int = Field(
        ...,
        ge=0,
        le=100,
        description="Puntaje de afinidad técnica global entre 0 y 100.",
    )
    language_detected: str = Field(
        ...,
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
        ..., description="Titular profesional de alto impacto adaptado a la vacante."
    )
    tailored_summary: str = Field(
        ...,
        description="Resumen profesional de 3-4 líneas calibrado con los años de experiencia ideales.",
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
    """Elimina tildes y diacríticos para hacer el matching insensible a acentos."""
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
    """Evalúa si una vacante supera las reglas duras locales sin invocar LLM."""
    raw_title = title.lower()
    raw_corpus = f"{title}\n{description}".lower()
    clean_title = strip_accents(raw_title)
    text_corpus = strip_accents(raw_corpus)

    for neg_pattern in DISQUALIFYING_PATTERNS:
        match_title = re.search(neg_pattern, clean_title)
        if match_title:
            return (
                False,
                f"Descartada por rol antagónico en título: '{match_title.group(0)}'",
            )

    for neg_pattern in DISQUALIFYING_PATTERNS:
        match_desc = re.search(neg_pattern, text_corpus)
        if match_desc and not any(
            re.search(p, clean_title) for p in CORE_POSITIVE_PATTERNS
        ):
            return (
                False,
                f"Descartada por término antagónico detectado: '{match_desc.group(0)}'",
            )

    matched_positives = []
    for pos_pattern in CORE_POSITIVE_PATTERNS:
        match = re.search(pos_pattern, text_corpus)
        if match:
            matched_positives.append(match.group(0))

    if not matched_positives:
        return (
            False,
            "Descartada: no contiene términos del núcleo de datos/analítica.",
        )

    return (
        True,
        f"Aprobada para LLM. Términos detectados: {', '.join(set(matched_positives))}",
    )


def run_heuristic_filter_batch() -> int:
    """Aplica prefiltro booleano a vacantes SCRAPED y actualiza SQLite."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT job_hash, title, company, description FROM job_applications WHERE status = 'SCRAPED';"
        )
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
                    SET status = 'FILTERED_OUT',
                        match_score = 0,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE job_hash = ?;
                    """,
                    (job["job_hash"],),
                )
            logger.info(f"🚫 [{job['company']} - {job['title']}] -> {reason}")
            filtered_out_count += 1
        else:
            logger.info(f"✅ [{job['company']} - {job['title']}] -> {reason}")
            approved_count += 1

    logger.info(
        f"Prefiltro completado: {approved_count} aprobadas, {filtered_out_count} descartadas ($0)."
    )
    return filtered_out_count


def load_master_cv() -> dict[str, Any]:
    """Carga la base de verdad curricular data/master_cv.json."""
    if not MASTER_CV_PATH.exists():
        raise FileNotFoundError(
            f"No se encontró el archivo maestro en: {MASTER_CV_PATH}"
        )
    with open(MASTER_CV_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def build_evaluation_prompt(
    job_title: str, company: str, description: str, master_cv: dict[str, Any]
) -> str:
    """Construye el prompt con contexto completo, anti-alucinación y calibración de seniority."""
    profile_summary = {
        "candidate": master_cv.get("personal_info", {}).get("name"),
        "education": master_cv.get("education", []),
        "certifications": master_cv.get("certifications", []),
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

    return f"""Eres un Tech Recruiter de élite y especialista en optimización de CVs para sistemas ATS.
Evalúa con máximo rigor técnico el encaje entre la vacante y el perfil del candidato.

=== VACANTE DE EMPLEO ===
Empresa: {company}
Cargo: {job_title}
Descripción y Requisitos:
{description}

=== PERFIL MAESTRO DEL CANDIDATO (VERDAD ABSOLUTA) ===
{json.dumps(profile_summary, ensure_ascii=False, indent=2)}

=== INSTRUCCIONES ESTRICTAS ===
1. Calcula 'match_score' de 0 a 100 evaluando compatibilidad con la experiencia demostrable.
2. Identifica 'hard_skills_matched' y 'missing_skills_gaps' (tecnologías de la vacante ausentes en el candidato).
3. Determina el idioma dominante de la vacante: 'es' o 'en'.
4. Redacta 'tailored_headline' y 'tailored_summary' en el idioma detectado, con enfoque técnico de alto impacto.

5. CALIBRACIÓN ESTRICTA DE AÑOS DE EXPERIENCIA (ANTI-SOBRECUALIFICACIÓN):
   - Si la vacante especifica un requisito mínimo (ej. 3+, 5+ o 7+ años), alinea el resumen exactamente a ese requerimiento o ligeramente superior (ej. "Con más de 5 años de trayectoria..." o "With 6+ years of experience...").
   - Para cargos Senior, Lead o Especialista donde no se especifique o se pida 5+, utiliza el estándar óptimo de la industria tech: "8+ years" o "10+ years" (o "8+ años" / "10+ años" en español).
   - REGLA DE ORO PROHIBITIVA: NUNCA menciones "15+", "20+" ni frases como "más de 15 años de experiencia". Evita detonar sesgos de sobrecualificación, pretensiones salariales desbordadas o encasillamiento en roles puramente directivos/gerenciales.

6. POLÍTICA ESTRICTA ANTI-ALUCINACIÓN PARA VIÑETAS:
   - Para cada empresa en 'selected_bullets', utiliza ÚNICAMENTE los strings exactos de los 'id' presentes en el perfil maestro.
   - Selecciona de 2 a 4 viñetas relevantes por empresa según los requerimientos del cargo.
   - NUNCA inventes nuevos identificadores de viñeta.

7. Redacta 'strategic_fit_rationale' justificando objetivamente el encaje.
"""


def evaluate_single_job(
    job_record: dict[str, Any],
    api_key: str | None = None,
    model_name: str | None = None,
    max_retries: int = 3,
) -> JobMatchEvaluation | None:
    """Evalúa una vacante individual llamando a Gemini con reintentos."""
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

    client = genai.Client(api_key=gemini_key)

    for attempt in range(1, max_retries + 1):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=JobMatchEvaluation,
                    temperature=0.1,
                ),
            )
            evaluation = JobMatchEvaluation.model_validate_json(response.text)
            logger.info(
                f"Evaluación Gemini exitosa ({model}): {job_record.get('company')} - "
                f"{job_record.get('title')} | Score: {evaluation.match_score}/100"
            )
            return evaluation
        except APIError as e:
            if e.code in (503, 429) and attempt < max_retries:
                wait_time = 5 * attempt
                logger.warning(
                    f"Servidor ocupado o límite ({e.code}). Reintentando en {wait_time}s..."
                )
                time.sleep(wait_time)
            else:
                logger.error(f"Error de API Gemini: {e}")
                return None
        except Exception as e:  # noqa: BLE001
            logger.error(f"Error evaluando vacante con Gemini: {e}", exc_info=True)
            return None

    return None


def run_gemini_evaluation_batch(
    min_score_threshold: int = 60,
    max_batch_size: int = 10,
    delay_between_calls: float = 4.5,
) -> int:
    """
    Evalúa con Gemini las vacantes SCRAPED respetando la cuota de 15 RPM.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM job_applications WHERE status = 'SCRAPED' LIMIT ?;",
            (max_batch_size,),
        )
        pending_jobs = [dict(row) for row in cursor.fetchall()]

    if not pending_jobs:
        logger.info(
            "No hay vacantes pendientes en estado 'SCRAPED' para evaluar con Gemini."
        )
        return 0

    current_model = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
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

        new_status = (
            "SCORED" if eval_result.match_score >= min_score_threshold else "DISCARDED"
        )

        bullets_map = {
            item.company_id: item.bullet_ids for item in eval_result.selected_bullets
        }

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE job_applications
                SET match_score = ?,
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
