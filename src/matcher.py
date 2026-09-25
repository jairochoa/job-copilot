"""
Motor de evaluación y matching híbrido (Filtros duros O(1) + RAG Similitud Coseno).
Calcula puntajes de 0 a 100 y selecciona el Top K de viñetas para el CV.
"""

import logging
from typing import Any, Dict, List, Tuple
import numpy as np

from src.config import settings
from src.embeddings import EmbeddingEngine, indexer
from src.extractor import JobRequirementsSchema

logger = logging.getLogger(__name__)


def evaluate_job_match(
    requirements: JobRequirementsSchema,
) -> Tuple[float, float, float, str, List[str]]:
    """
    Evalúa una vacante contra master_cv.json y devuelve:
    (score_total, hard_score, soft_score, rationale, selected_bullet_ids)
    """
    # 1. Gatekeeper Territorial / Geográfico
    if not requirements.is_remote_or_eligible:
        reason = requirements.ineligibility_reason or "Vacante no elegible para trabajo remoto desde Colombia."
        logger.info(f"Vacante excluida por filtro territorial: {reason}")
        return 0.0, 0.0, 0.0, f"Excluida territorialmente: {reason}", []

    engine = EmbeddingEngine()
    inventory = indexer.cv_data.get("skills_inventory", {})

    # 2. Evaluación de Hard Skills (70% del peso)
    # Filtro cuantitativo O(1): Años mínimos requeridos en Python / SQL / ML
    req_years = requirements.min_years_experience or 0
    python_years = inventory.get("python", {}).get("years_numeric", 0)

    # Penalización gradual si la vacante pide más años de los que tenemos
    seniority_multiplier = 1.0
    if req_years > python_years:
        seniority_multiplier = max(0.5, python_years / req_years)

    # Similitud semántica de Hard Skills obligatorias y deseables
    hard_queries = requirements.mandatory_hard_skills + requirements.nice_to_have_skills
    if hard_queries:
        query_vectors = engine.encode(hard_queries)
        sim_matrix = engine.cosine_similarity_matrix(
            query_vectors, indexer.hard_skill_vectors
        )
        # Tomamos la mejor coincidencia para cada skill requerida
        best_matches_per_skill = np.max(sim_matrix, axis=1)
        # Convertimos similitud [-1, 1] al rango [0, 100]
        hard_semantic_score = float(np.mean(np.clip(best_matches_per_skill, 0.0, 1.0)) * 100.0)
    else:
        hard_semantic_score = 75.0  # Base neutral si no declaró skills explícitas

    hard_score = round(hard_semantic_score * seniority_multiplier, 2)

    # 3. Evaluación de Soft Skills (30% del peso)
    soft_queries = requirements.soft_skills_context
    if soft_queries and len(indexer.soft_skill_texts) > 0:
        soft_query_vectors = engine.encode(soft_queries)
        soft_sim_matrix = engine.cosine_similarity_matrix(
            soft_query_vectors, indexer.soft_skill_vectors
        )
        best_soft_matches = np.max(soft_sim_matrix, axis=1)
        soft_score = round(
            float(np.mean(np.clip(best_soft_matches, 0.0, 1.0)) * 100.0), 2
        )
    else:
        soft_score = 80.0  # Ponderación base favorable

    # 4. Cálculo del Score Total Híbrido (0 a 100)
    total_score = round(
        (hard_score * settings.HARD_SKILLS_WEIGHT)
        + (soft_score * settings.SOFT_SKILLS_WEIGHT),
        2,
    )

    # 5. Selector Top K de Viñetas de Experiencia por Afinidad Semántica
    # Construimos un vector combinado de la vacante para rankear los logros
    all_req_text = " ".join(
        requirements.mandatory_hard_skills
        + requirements.nice_to_have_skills
        + requirements.soft_skills_context
    )
    job_vector = engine.encode([all_req_text])
    bullet_sims = engine.cosine_similarity_matrix(
        job_vector, indexer.bullet_vectors
    )[0]

    # Agrupamos viñetas por empresa para asegurar que ninguna quede vacía
    bullets_by_company: Dict[str, List[Tuple[float, Dict[str, Any]]]] = {}
    for sim, bullet in zip(bullet_sims, indexer.bullet_items):
        comp = bullet["company"]
        bullets_by_company.setdefault(comp, []).append((float(sim), bullet))

    selected_bullet_ids: List[str] = []
    # Seleccionamos las mejores 2 o 3 viñetas por empresa
    for comp, bullets in bullets_by_company.items():
        # Ordenar por afinidad semántica descendente, y en caso de empate por default_priority
        sorted_bullets = sorted(
            bullets,
            key=lambda x: (x[0], -x[1].get("default_priority", 99)),
            reverse=True,
        )
        # Tomar máximo 3 viñetas más relevantes de cada empresa
        for _, b in sorted_bullets[:3]:
            selected_bullet_ids.append(b["id"])

    # 6. Justificación técnica estructurada
    rationale = (
        f"Match Score: {total_score}/100 | Hard: {hard_score}%, Soft: {soft_score}%. "
        f"Skills analizadas: {len(hard_queries)}. "
        f"Seniority factor: {seniority_multiplier:.2f}. "
        f"Viñetas priorizadas: {len(selected_bullet_ids)}."
    )

    return total_score, hard_score, soft_score, rationale, selected_bullet_ids


if __name__ == "__main__":
    print("--- TEST DE MATCHING HÍBRIDO VECTORIAL ---")
    # Caso de prueba con el esquema de requisitos validado
    test_reqs = JobRequirementsSchema(
        is_remote_or_eligible=True,
        language="en",
        role_category="Data Science",
        min_years_experience=5,
        mandatory_hard_skills=["Python", "SQL", "scikit-learn", "XGBoost", "ROC-AUC"],
        nice_to_have_skills=["PySpark", "Databricks", "MLflow"],
        soft_skills_context=["Technical leadership", "Stakeholder presentation"],
    )

    score, hard, soft, rat, bullets = evaluate_job_match(test_reqs)
    print(f"Total Score : {score} / 100")
    print(f"Hard Score  : {hard} / 100")
    print(f"Soft Score  : {soft} / 100")
    print(f"Rationale   : {rat}")
    print(f"Bullets Top : {bullets}")