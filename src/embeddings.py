"""
Módulo de embeddings y vectorización semántica local usando sentence-transformers.
Maneja la indexación en memoria del perfil maestro (master_cv.json).
"""

import json
import logging
from typing import Any, Dict, List, Tuple
import numpy as np
from sentence_transformers import SentenceTransformer

from src.config import settings

logger = logging.getLogger(__name__)


class EmbeddingEngine:
    _instance: "EmbeddingEngine | None" = None
    _model: SentenceTransformer | None = None

    def __new__(cls) -> "EmbeddingEngine":
        if cls._instance is None:
            cls._instance = super(EmbeddingEngine, cls).__new__(cls)
            logger.info(
                f"Cargando modelo de embeddings local: [{settings.EMBEDDING_MODEL_NAME}]..."
            )
            cls._model = SentenceTransformer(settings.EMBEDDING_MODEL_NAME)
            logger.info("Modelo de embeddings cargado exitosamente en memoria.")
        return cls._instance

    @property
    def model(self) -> SentenceTransformer:
        if self._model is None:
            self._model = SentenceTransformer(settings.EMBEDDING_MODEL_NAME)
        return self._model

    def encode(self, texts: List[str]) -> np.ndarray:
        """Genera representaciones vectoriales normalizadas (L2) para búsqueda por coseno."""
        if not texts:
            return np.empty((0, self.model.get_sentence_embedding_dimension()))
        embeddings = self.model.encode(
            texts, convert_to_numpy=True, normalize_embeddings=True
        )
        return embeddings

    @staticmethod
    def cosine_similarity_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        """
        Calcula la similitud coseno entre dos matrices de vectores normalizados.
        Rango de salida: [-1.0, 1.0].
        """
        if a.size == 0 or b.size == 0:
            return np.array([])
        return np.dot(a, b.T)


class MasterCVIndexer:
    """Indexador vectorial de las secciones del CV Maestro."""

    def __init__(self, master_cv_path: str = str(settings.MASTER_CV_PATH)):
        self.engine = EmbeddingEngine()
        with open(master_cv_path, "r", encoding="utf-8") as f:
            self.cv_data: Dict[str, Any] = json.load(f)

        self._build_index()

    def _build_index(self) -> None:
        """Construye y pre-calcula los vectores de skills y bullets del CV."""
        logger.info("Indexando chunks de master_cv.json...")

        # 1. Chunks de Hard Skills y Certificaciones
        self.hard_skill_keys: List[str] = []
        self.hard_skill_texts: List[str] = []
        for key, item in self.cv_data.get("skills_inventory", {}).items():
            self.hard_skill_keys.append(key)
            kws = ", ".join(item.get("keywords", []))
            chunk = f"{key}. Herramientas: {kws}. Contexto: {item.get('context', '')}"
            self.hard_skill_texts.append(chunk)

        for cert in self.cv_data.get("certifications", []):
            cert_id = cert.get("id", "cert")
            self.hard_skill_keys.append(cert_id)
            name_es = cert.get("name", {}).get("es", "")
            name_en = cert.get("name", {}).get("en", "")
            issuer = cert.get("issuer", "")
            chunk = f"Certificación y Curso: {name_es} / {name_en} por {issuer}. Estado: {cert.get('status', '')}"
            self.hard_skill_texts.append(chunk)

        self.hard_skill_vectors = self.engine.encode(self.hard_skill_texts)

        # 2. Chunks de Soft Skills
        self.soft_skill_ids: List[str] = []
        self.soft_skill_texts: List[str] = []
        for item in self.cv_data.get("soft_skills", []):
            self.soft_skill_ids.append(item.get("id"))
            chunk = (
                f"{item.get('name', {}).get('es', '')} / "
                f"{item.get('name', {}).get('en', '')}: {item.get('context', '')}"
            )
            self.soft_skill_texts.append(chunk)

        self.soft_skill_vectors = self.engine.encode(self.soft_skill_texts)

        # 3. Chunks de Viñetas de Experiencia (para selector Top K)
        self.bullet_items: List[Dict[str, Any]] = self.cv_data.get(
            "experience_bullets_pool", []
        )
        self.bullet_texts: List[str] = []
        for b in self.bullet_items:
            # Vectorizamos texto bilingüe + stack para máxima captura semántica
            stack_str = ", ".join(b.get("stack", []))
            text_es = b.get("text", {}).get("es", "")
            text_en = b.get("text", {}).get("en", "")
            chunk = f"{b.get('company')} {stack_str}. {text_es} {text_en}"
            self.bullet_texts.append(chunk)

        self.bullet_vectors = self.engine.encode(self.bullet_texts)
        logger.info(
            f"Indexación completada: {len(self.hard_skill_texts)} hard skills, "
            f"{len(self.soft_skill_texts)} soft skills, {len(self.bullet_texts)} viñetas."
        )


# Instancia única en memoria para reuso rápido
indexer = MasterCVIndexer()