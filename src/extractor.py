"""
Módulo de extracción estructurada de vacantes utilizando configuración desacoplada y Pydantic.
"""

import json
import logging
from typing import List, Optional
import requests
from pydantic import BaseModel, Field

from src.config import settings

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


class JobRequirementsSchema(BaseModel):
    is_remote_or_eligible: bool = Field(
        ...,
        description="True si la vacante es 100% remota o abierta a Colombia/LatAm. False si exige presencialidad fuera de Colombia o visa/ciudadanía exclusiva.",
    )
    ineligibility_reason: Optional[str] = Field(
        default="",
        description="Motivo de exclusión geográfica o legal si is_remote_or_eligible es False.",
    )
    language: str = Field(
        ...,
        description="Idioma principal de la vacante: 'es' o 'en'.",
    )
    role_category: str = Field(
        ...,
        description="Categoría principal: 'Data Science', 'Machine Learning', 'Applied AI', 'Data Engineering', 'Statistics', o 'Other'.",
    )
    min_years_experience: Optional[int] = Field(
        default=0,
        description="Años mínimos de experiencia requeridos explícitamente (0 si no especifica).",
    )
    mandatory_hard_skills: List[str] = Field(
        default_factory=list,
        description="Tecnologías y herramientas obligatorias.",
    )
    nice_to_have_skills: List[str] = Field(
        default_factory=list,
        description="Tecnologías o herramientas opcionales/deseables.",
    )
    soft_skills_context: List[str] = Field(
        default_factory=list,
        description="Competencias blandas, liderazgo y comunicación requeridas.",
    )


def extract_job_requirements(
    job_title: str, company: str, description: str
) -> JobRequirementsSchema:
    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY no configurada en las variables de entorno.")

    logger.info(
        f"Iniciando extracción con modelo [{settings.GEMINI_MODEL}] para: '{job_title}' en '{company}'..."
    )

    url = f"{settings.gemini_endpoint_url}?key={settings.GEMINI_API_KEY}"

    prompt = f"""
Analiza técnicamente la siguiente vacante laboral y extrae los requisitos en un JSON estricto.

Título: {job_title}
Empresa: {company}
Descripción:
{description}

Reglas:
1. Filtro Territorial: is_remote_or_eligible = True si un candidato residente en Colombia puede postularse de forma remota. False si exige presencialidad en otro país o ciudadanía restringida (ej. US Citizen only).
2. Hard Skills: Separa mandatory_hard_skills y nice_to_have_skills.
3. Soft Skills: En soft_skills_context.
4. Idioma: 'es' o 'en'.
"""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "response_schema": JobRequirementsSchema.model_json_schema(),
            "temperature": 0.0,
        },
    }

    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=settings.REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = JobRequirementsSchema.model_validate_json(raw_text)
        logger.info("Extracción estructurada completada con éxito.")
        return parsed
    except Exception as e:
        logger.error(f"Error en llamada a Gemini ({settings.GEMINI_MODEL}): {e}")
        if "response" in locals() and hasattr(response, "text") and response.text:
            logger.error(f"Detalle API: {response.text}")
        raise e


if __name__ == "__main__":
    print(f"--- TEST EXTRACTOR [Modelo: {settings.GEMINI_MODEL}] ---")
    sample_title = "Senior Data Scientist (Remote - LatAm)"
    sample_company = "Tech Global"
    sample_desc = """
    We are looking for a Senior Data Scientist to join our team. 100% remote within Latin America.
    Requirements:
    - 5+ years of experience in Python, SQL, and Machine Learning.
    - Deep knowledge of scikit-learn, XGBoost, and model evaluation metrics (ROC-AUC).
    - Experience with PySpark or Databricks is a plus.
    - Strong communication skills to present insights to executive leaders.
    """
    reqs = extract_job_requirements(sample_title, sample_company, sample_desc)
    print("\nResultado JSON:")
    print(reqs.model_dump_json(indent=2))