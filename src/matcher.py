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
    """Evalúa una vacante contra master_cv.json y devuelve:

    (score_total, hard_score, soft_score, rationale, selected_bullet_ids)
    """
    # 1. Gatekeeper Territorial / Geográfico
    if not requirements.is_remote_or_eligible:
        reason = (
            requirements.ineligibility_reason
            or "Vacante no elegible para trabajo remoto desde Colombia."
        )
        logger.info(f"Vacante excluida por filtro territorial: {reason}")
        return 0.0, 0.0, 0.0, f"Excluida territorialmente: {reason}", []

    engine = EmbeddingEngine()
    inventory = indexer.cv_data.get("skills_inventory", {})

    # 2. Evaluación de Seniority dinámica (sin llaves ni nombres de herramientas fijos)
    req_years = requirements.min_years_experience or 0

    inventory_years = [
        data.get("years_numeric", 0)
        for data in inventory.values()
        if isinstance(data, dict)
    ]
    candidate_max_years = max(inventory_years) if inventory_years else 10

    role_cat_key = (
        requirements.role_category.lower()
        .replace(" ", "_")
        .replace("-", "_")
    )
    relevant_years = inventory.get(role_cat_key, {}).get(
        "years_numeric", candidate_max_years
    )

    seniority_multiplier = 1.0
    if req_years > 0 and req_years > relevant_years:
        seniority_multiplier = max(0.5, relevant_years / req_years)

    # 3. Evaluación de Hard Skills (desglose 80% Mandatory / 20% Nice-to-have)
    mandatory_score = 0.0
    if requirements.mandatory_hard_skills and len(indexer.hard_skill_texts) > 0:
        mand_vectors = engine.encode(requirements.mandatory_hard_skills)
        mand_sim_matrix = engine.cosine_similarity_matrix(
            mand_vectors, indexer.hard_skill_vectors
        )
        best_mand = np.max(mand_sim_matrix, axis=1)
        mandatory_score = float(np.mean(np.clip(best_mand, 0.0, 1.0)) * 100.0)

    nice_score = 0.0
    if requirements.nice_to_have_skills and len(indexer.hard_skill_texts) > 0:
        nice_vectors = engine.encode(requirements.nice_to_have_skills)
        nice_sim_matrix = engine.cosine_similarity_matrix(
            nice_vectors, indexer.hard_skill_vectors
        )
        best_nice = np.max(nice_sim_matrix, axis=1)
        nice_score = float(np.mean(np.clip(best_nice, 0.0, 1.0)) * 100.0)

    # Ponderación interna desacoplada vía settings
    if requirements.mandatory_hard_skills and requirements.nice_to_have_skills:
        hard_semantic_score = (
            mandatory_score * settings.MANDATORY_HARD_WEIGHT
        ) + (nice_score * settings.NICE_TO_HAVE_HARD_WEIGHT)
    elif requirements.mandatory_hard_skills:
        hard_semantic_score = mandatory_score
    elif requirements.nice_to_have_skills:
        hard_semantic_score = nice_score
    else:
        hard_semantic_score = 75.0

    hard_score = round(hard_semantic_score * seniority_multiplier, 2)

    # 4. Evaluación de Soft Skills
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
        soft_score = 80.0

    # 5. Cálculo del Score Total Híbrido (70% Hard + 30% Soft desde settings)
    total_score = round(
        (hard_score * settings.HARD_SKILLS_WEIGHT)
        + (soft_score * settings.SOFT_SKILLS_WEIGHT),
        2,
    )

    # 6. Selector Top K de Viñetas de Experiencia por Afinidad Semántica
    all_req_text = " ".join(
        requirements.mandatory_hard_skills
        + requirements.nice_to_have_skills
        + requirements.soft_skills_context
    )
    job_vector = engine.encode([all_req_text])
    bullet_sims = engine.cosine_similarity_matrix(
        job_vector, indexer.bullet_vectors
    )[0]

    bullets_by_company: Dict[str, List[Tuple[float, Dict[str, Any]]]] = {}
    for sim, bullet in zip(bullet_sims, indexer.bullet_items):
        comp = bullet["company"]
        bullets_by_company.setdefault(comp, []).append((float(sim), bullet))

    selected_bullet_ids: List[str] = []
    for comp, bullets in bullets_by_company.items():
        sorted_bullets = sorted(
            bullets,
            key=lambda x: (x[0], -x[1].get("default_priority", 99)),
            reverse=True,
        )
        for _, b in sorted_bullets[:3]:
            selected_bullet_ids.append(b["id"])

    # 7. Justificación técnica estructurada con desglose transparente
    total_skills = len(requirements.mandatory_hard_skills) + len(
        requirements.nice_to_have_skills
    )
    rationale = (
        f"Match Score: {total_score}/100 | Hard: {hard_score}% (Mandatory: {mandatory_score:.1f}%, Nice: {nice_score:.1f}%), "
        f"Soft: {soft_score}%. Skills analizadas: {total_skills}. "
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