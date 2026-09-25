"""
Módulo de extracción estructurada de vacantes utilizando configuración desacoplada y Pydantic.
Aplica desambiguación taxonómica entre Requirements (Mandatory), Nice to Have y Soft Skills.
"""

import json
import logging
import time
from typing import List, Optional
from pydantic import BaseModel, Field
import requests

from src.config import settings

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


class JobRequirementsSchema(BaseModel):
    is_remote_or_eligible: bool = Field(
        ...,
        description="True si la vacante es 100% remota a nivel global o explícitamente abierta a candidatos en Colombia/LatAm. False si exige presencialidad fuera de Colombia o residencia/ciudadanía estricta (ej. US Citizen Only, Secret Clearance).",
    )
    ineligibility_reason: Optional[str] = Field(
        default="",
        description="Si is_remote_or_eligible es False, describe brevemente la restricción geográfica o legal. Si es True, dejar vacío.",
    )
    language: str = Field(
        ...,
        description="Idioma principal en que está redactada la vacante ('es' para español, 'en' para inglés).",
    )
    role_category: str = Field(
        ...,
        description="Categoría principal del rol: 'Data Science', 'Machine Learning', 'Applied AI', 'Data Engineering', 'Statistics', o 'Other'.",
    )
    min_years_experience: Optional[int] = Field(
        default=0,
        description="Años mínimos de experiencia cuantitativa exigidos en el perfil (0 si no se menciona un número específico).",
    )
    mandatory_hard_skills: List[str] = Field(
        default_factory=list,
        description="Tecnologías, lenguajes, frameworks y herramientas duras listadas bajo 'Requirements', 'Requisitos' o 'Must-have'.",
    )
    nice_to_have_skills: List[str] = Field(
        default_factory=list,
        description="Tecnologías o herramientas listadas bajo 'Nice to have', 'Deseable', 'Bonus' o 'Plus'.",
    )
    soft_skills_context: List[str] = Field(
        default_factory=list,
        description="Competencias interpersonales, liderazgo, idiomas (ej. Inglés B2/C1), metodologías de trabajo o comunicación.",
    )


def extract_job_requirements(
    job_title: str,
    company: str,
    description: str,
    max_retries: int = 3,
    delay_between_calls: float = 4.2,
) -> JobRequirementsSchema:
    """
    Analiza técnicamente la oferta y extrae el esquema estructurado con reintentos y control de cuota.
    """
    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY no configurada en las variables de entorno.")

    logger.info(
        f"Extrayendo requisitos con [{settings.GEMINI_MODEL}] para: '{job_title}' en '{company}'..."
    )
    url = f"{settings.gemini_endpoint_url}?key={settings.GEMINI_API_KEY}"

    prompt = f"""
Eres un analista técnico de reclutamiento senior y arquitecto de soluciones de Inteligencia Artificial.
Analiza con rigor la siguiente descripción de vacante laboral y extrae los datos poblando estrictamente el esquema JSON.

Detalles de la oferta:
- Título: {job_title}
- Empresa: {company}
- Descripción:
{description}

REGLAS TAXONÓMICAS DE EXTRACCIÓN OBLIGATORIAS:
1. Mapeo de Secciones (Requirements vs Nice to have):
   - Todo lo que figure bajo encabezados como 'Requirements', 'Requisitos', 'Must-have', 'Qualifications', 'What you will need', 'Knowledge & Qualifications' o viñetas principales del perfil ES ESTRICTAMENTE OBLIGATORIO (MANDATORY).
   - Todo lo que figure bajo 'Nice to have', 'Deseable', 'Bonus', 'Plus', 'Preferred' DEBE ir a nice_to_have_skills.

2. Descomposición Anatómica de las Viñetas de Requisitos:
   - Años de Experiencia: Si una viñeta pide tiempo mínimo cuantitativo (ej. 'At least five years...', '3+ years of experience'), extrae el número entero a min_years_experience.
   - Herramientas y Hard Skills: Descompón en nombres atómicos de herramientas/conceptos técnicos (ej. ante 'capability using Python to construct APIs', extrae 'Python' y 'REST APIs'; ante 'AWS, Docker, ECS/EKS', desglosa en 'AWS', 'Docker', 'ECS', 'EKS').
   - Requisito de Idioma (ej. Inglés B2, Fluent English, Professional English):
     * Si figura bajo 'Requirements' o en el cuerpo principal de requisitos, clasifícalo en 'mandatory_hard_skills' (ej. 'English B2+' o 'Professional English').
     * Si figura bajo 'Nice to have' o deseable, clasifícalo en 'nice_to_have_skills'.
   - Habilidades Blandas e Interpersonales: Reserva 'soft_skills_context' para competencias de comunicación, liderazgo de equipos, negociación, trabajo con stakeholders o adaptabilidad.

3. Filtro Territorial (Gatekeeper):
   - is_remote_or_eligible = True si la posición admite trabajo remoto internacional/LatAm o candidatos ubicados en Colombia o Venezuela.
   - is_remote_or_eligible = False si exige presencialidad fuera de Colombia o Venezuela, o autorizaciones legales inaccesibles (ej. US Citizen Only, Active Security Clearance, Green Card indispensable sin opción remota).
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

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=settings.REQUEST_TIMEOUT,
            )

            if response.status_code == 429:
                wait_time = 35 * attempt
                logger.warning(
                    f"Límite de peticiones alcanzado (429). Esperando {wait_time}s para reintentar ({attempt}/{max_retries})..."
                )
                time.sleep(wait_time)
                continue

            response.raise_for_status()
            data = response.json()
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
            parsed = JobRequirementsSchema.model_validate_json(raw_text)

            time.sleep(delay_between_calls)
            return parsed

        except requests.exceptions.RequestException as e:
            if attempt == max_retries:
                logger.error(f"Fallo definitivo al extraer requisitos tras {max_retries} intentos: {e}")
                raise e
            logger.warning(f"Reintentando por fallo de red: {e}")
            time.sleep(5)


if __name__ == "__main__":
    print(f"--- TEST EXTRACTOR TAXONÓMICO [Modelo: {settings.GEMINI_MODEL}] ---")
    test_title = "AI Backend Engineer"
    test_company = "ScaleAI Solutions"
    test_desc = (
        "Requirements:\n"
        "- At least five years of hands-on backend engineering work\n"
        "- Proven capability using Python to construct APIs\n"
        "- Experience building Generative AI solutions\n\n"
        "Nice to have:\n"
        "- Exposure to LangChain, LlamaIndex\n"
    )
    res = extract_job_requirements(test_title, test_company, test_desc)
    print("\nResultado con Descomposición Semántica:")
    print(res.model_dump_json(indent=2))