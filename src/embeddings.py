"""
Módulo de embeddings y vectorización semántica local usando sentence-transformers.
Maneja la indexación en memoria del perfil maestro (master_cv.json).
"""

import json
import logging
import re
from typing import Any, Dict, List, Tuple
import unicodedata
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


def normalize_text(text: str) -> str:
    """Normaliza texto para comparaciones léxicas sin tildes, minúsculas y caracteres limpios."""
    import re
    import unicodedata

    if not text:
        return ""
    text = text.lower().strip()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("utf-8")
    text = re.sub(r"[^\w\s\+\#\.\-]", " ", text)
    return " ".join(text.split())


def calibrate_cosine_similarity(cos_sim: float) -> float:
    """
    Calibra la similitud coseno de SentenceTransformers multilingüe.
    En 'paraphrase-multilingual-MiniLM-L12-v2', oraciones sin ninguna relación
    semántica tienen un piso de ruido de 0.15 a 0.45.
    - cos_sim <= 0.45: Ruido de fondo / conceptos no relacionados -> 0.0
    - 0.45 < cos_sim < 0.70: Relación semántica emergente/parcial -> [0.25, 0.85]
    - cos_sim >= 0.70: Fuerte correspondencia semántica -> [0.85, 1.0]
    """
    if cos_sim <= 0.45:
        return 0.0
    elif cos_sim >= 0.70:
        return min(1.0, 0.85 + (cos_sim - 0.70) * (0.15 / 0.15))
    else:
        return 0.25 + (cos_sim - 0.45) * (0.60 / 0.25)


class MasterCVIndexer:
    """Indexador multidimensional y vectorial de todas las secciones del CV Maestro."""

    def __init__(self, master_cv_path: str = str(settings.MASTER_CV_PATH)):
        self.engine = EmbeddingEngine()
        with open(master_cv_path, "r", encoding="utf-8") as f:
            self.cv_data: Dict[str, Any] = json.load(f)

        self._build_index()

    def _build_index(self) -> None:
        """Construye y pre-calcula los índices léxicos y los vectores de skills, educación, idiomas e industrias."""
        logger.info("Indexando chunks y catálogo léxico de master_cv.json...")

        self.lexical_catalog: Dict[str, Dict[str, Any]] = {}

        def register_lexical(term: str, dimension: str, name: str, weight: float) -> None:
            norm = normalize_text(term)
            if norm and len(norm) >= 2:
                if norm not in self.lexical_catalog or weight > self.lexical_catalog[norm]["weight"]:
                    self.lexical_catalog[norm] = {
                        "dimension": dimension,
                        "name": name,
                        "weight": weight,
                        "term": term,
                    }

        # 1. Chunks y catálogo de Hard Skills (Herramientas del inventario)
        self.hard_skill_keys: List[str] = []
        self.hard_skill_texts: List[str] = []
        self.hard_skill_metadata: List[Dict[str, Any]] = []

        for key, item in self.cv_data.get("skills_inventory", {}).items():
            cat_display = key.replace("_", " ")
            register_lexical(cat_display, "hard_skills", cat_display, 1.0)
            kws = list(item.get("keywords", []))
            for kw in kws:
                register_lexical(kw, "hard_skills", kw, 1.0)
                # Indexamos herramientas contextualizadas en el dominio técnico para evitar colisiones multilingües
                self.hard_skill_keys.append(f"kw_{kw}")
                self.hard_skill_texts.append(f"Herramienta o tecnología de ciencia de datos y software analítico: {kw}")
                self.hard_skill_metadata.append({"dimension": "hard_skills", "weight": 1.0, "name": kw})

            # Párrafo de contexto del área
            kws_str = ", ".join(kws)
            chunk = f"{key}. Herramientas: {kws_str}. Contexto: {item.get('context', '')}"
            self.hard_skill_keys.append(key)
            self.hard_skill_texts.append(chunk)
            self.hard_skill_metadata.append({"dimension": "hard_skills", "weight": 1.0, "name": key})

        # 2. Formación Académica (Education) - Peso 2.0x
        edu_items = self.cv_data.get("education", [])
        edu_summary_parts = []
        for edu in edu_items:
            deg_es = edu.get("degree", {}).get("es", "")
            deg_en = edu.get("degree", {}).get("en", "")
            inst = edu.get("institution", "")
            details_es = edu.get("details", {}).get("es", "")
            details_en = edu.get("details", {}).get("en", "")

            if deg_es:
                register_lexical(deg_es, "education", deg_es, 2.0)
            if deg_en:
                register_lexical(deg_en, "education", deg_en, 2.0)
            if inst:
                register_lexical(inst, "education", inst, 2.0)

            edu_summary_parts.append(f"{deg_es} / {deg_en} en {inst}. {details_es} {details_en}")

        # Variaciones académicas clave para exact booster
        for academic_term in [
            "m.sc. in statistics", "msc in statistics", "master in statistics", "maestria en estadistica",
            "licenciado en estadistica", "b.sc. in statistics", "licenciatura en estadistica",
            "ingenieria en inteligencia artificial y ciencia de datos", "b.sc. in artificial intelligence & data science",
            "estadistica", "statistics", "data science", "ciencia de datos", "inteligencia artificial",
            "artificial intelligence", "stem degree", "grado en estadistica", "quantitative field",
            "universidad de los andes", "ula", "unad"
        ]:
            register_lexical(academic_term, "education", academic_term, 2.0)

        if edu_summary_parts:
            edu_chunk = "Formación Académica y Títulos: " + " ".join(edu_summary_parts)
            self.hard_skill_keys.append("education_summary")
            self.hard_skill_texts.append(edu_chunk)
            self.hard_skill_metadata.append({"dimension": "education", "weight": 2.0, "name": "Formación Académica"})

        # 3. Idiomas (Languages) - Peso 1.5x
        lang_items = self.cv_data.get("languages", [])
        lang_summary_parts = []
        for lang in lang_items:
            l_name_es = lang.get("language", {}).get("es", "")
            l_name_en = lang.get("language", {}).get("en", "")
            prof_es = lang.get("proficiency", {}).get("es", "") or lang.get("level", {}).get("es", "")
            prof_en = lang.get("proficiency", {}).get("en", "") or lang.get("level", {}).get("en", "")

            if l_name_es:
                register_lexical(l_name_es, "languages", l_name_es, 1.5)
            if l_name_en:
                register_lexical(l_name_en, "languages", l_name_en, 1.5)

            lang_summary_parts.append(f"{l_name_es} / {l_name_en}: {prof_es} / {prof_en}")

        for lang_term in [
            "ingles", "english", "ingles b2", "english b2", "b2", "aptis b2", "professional working proficiency",
            "competencia profesional operativa", "espanol", "spanish", "nativo", "native", "bilingual", "bilingue"
        ]:
            register_lexical(lang_term, "languages", lang_term, 1.5)

        if lang_summary_parts:
            lang_chunk = "Competencia en Idiomas: " + "; ".join(lang_summary_parts)
            self.hard_skill_keys.append("languages_summary")
            self.hard_skill_texts.append(lang_chunk)
            self.hard_skill_metadata.append({"dimension": "languages", "weight": 1.5, "name": "Idiomas"})

        # 4. Dominios de Industria (Industry Domains) - Peso 1.5x
        ind_items = self.cv_data.get("industry_domains", {})
        ind_summary_parts = []
        for ind_key, ind_data in ind_items.items():
            name_es = ind_data.get("name", {}).get("es", "")
            name_en = ind_data.get("name", {}).get("en", "")
            companies = ind_data.get("companies", [])
            keywords = ind_data.get("keywords", [])

            for kw in keywords:
                register_lexical(kw, "industry", kw, 1.5)
            for comp in companies:
                register_lexical(comp, "industry", comp, 1.5)

            ind_chunk = f"Dominio Sectorial e Industria: {name_es} / {name_en} ({', '.join(companies)}). Conceptos: {', '.join(keywords)}."
            self.hard_skill_keys.append(f"ind_{ind_key}")
            self.hard_skill_texts.append(ind_chunk)
            self.hard_skill_metadata.append({"dimension": "industry", "weight": 1.5, "name": name_es})
            ind_summary_parts.append(ind_chunk)

        # 5. Certificaciones (Certifications) - Peso 1.0x
        for cert in self.cv_data.get("certifications", []):
            cert_id = cert.get("id", "cert")
            name_es = cert.get("name", {}).get("es", "")
            name_en = cert.get("name", {}).get("en", "")
            issuer = cert.get("issuer", "")

            if name_es:
                register_lexical(name_es, "certifications", name_es, 1.0)
            if name_en:
                register_lexical(name_en, "certifications", name_en, 1.0)
            if issuer:
                register_lexical(issuer, "certifications", issuer, 1.0)

            chunk = f"Certificación y Curso: {name_es} / {name_en} por {issuer}. Estado: {cert.get('status', '')}"
            self.hard_skill_keys.append(cert_id)
            self.hard_skill_texts.append(chunk)
            self.hard_skill_metadata.append({"dimension": "certifications", "weight": 1.0, "name": name_es or name_en})

        # Pre-calcular vectores densos para todo el espectro hard/académico/industria
        self.hard_skill_vectors = self.engine.encode(self.hard_skill_texts)

        # 6. Chunks y catálogo de Soft Skills
        self.soft_skill_ids: List[str] = []
        self.soft_skill_texts: List[str] = []
        for item in self.cv_data.get("soft_skills", []):
            self.soft_skill_ids.append(item.get("id"))
            name_es = item.get("name", {}).get("es", "")
            name_en = item.get("name", {}).get("en", "")
            chunk = f"{name_es} / {name_en}: {item.get('context', '')}"
            self.soft_skill_texts.append(chunk)

        # Términos raíz clave para Soft Skills Booster
        soft_core_terms = [
            ("problem-solving", "Resolución de Problemas"),
            ("problem solving", "Resolución de Problemas"),
            ("resolucion de problemas", "Resolución de Problemas"),
            ("pensamiento critico", "Pensamiento Crítico"),
            ("critical thinking", "Pensamiento Crítico"),
            ("liderazgo", "Liderazgo Técnico"),
            ("leadership", "Liderazgo Técnico"),
            ("mentoria", "Mentoría"),
            ("mentorship", "Mentoría"),
            ("stakeholder", "Comunicación con Stakeholders"),
            ("stakeholders", "Comunicación con Stakeholders"),
            ("comunicacion", "Comunicación Efectiva"),
            ("communication", "Comunicación Efectiva"),
            ("agile", "Metodologías Ágiles"),
            ("scrum", "Scrum"),
            ("kanban", "Kanban"),
            ("agil", "Metodologías Ágiles"),
            ("ambiguity", "Gestión de la Ambigüedad"),
            ("ambiguedad", "Gestión de la Ambigüedad"),
            ("ambiguous", "Gestión de la Ambigüedad"),
            ("storytelling", "Data Storytelling"),
            ("etica", "Ética de IA"),
            ("ethics", "Ética de IA"),
        ]
        for term, label in soft_core_terms:
            register_lexical(term, "soft_skills", label, 1.0)

        self.soft_skill_vectors = self.engine.encode(self.soft_skill_texts)

        # 7. Chunks de Viñetas de Experiencia (para selector Top K)
        self.bullet_items: List[Dict[str, Any]] = self.cv_data.get("experience_bullets_pool", [])
        self.bullet_texts: List[str] = []
        for b in self.bullet_items:
            stack_str = ", ".join(b.get("stack", []))
            text_es = b.get("text", {}).get("es", "")
            text_en = b.get("text", {}).get("en", "")
            chunk = f"{b.get('company')} {stack_str}. {text_es} {text_en}"
            self.bullet_texts.append(chunk)

        self.bullet_vectors = self.engine.encode(self.bullet_texts)

        logger.info(
            f"Indexación completada: {len(self.hard_skill_texts)} vectores hard/edu/ind, "
            f"{len(self.soft_skill_texts)} soft skills, {len(self.lexical_catalog)} términos léxicos."
        )

    def match_requirement(self, req_text: str, is_soft: bool = False) -> Dict[str, Any]:
        """
        Evalúa un requisito individual utilizando el Exact/Phrase Match Booster jerárquico
        y la similitud coseno densa calibrada como respaldo.
        """
        norm_req = normalize_text(req_text)
        if not norm_req:
            return {
                "score": 0.0,
                "weight": 1.0,
                "dimension": "unknown",
                "match_type": "EMPTY",
                "matched_entity": "",
            }

        # 1. Booster Léxico: Coincidencia Exacta o Subfrase
        # A) Match idéntico directo respetando dimensión (hard vs soft)
        if norm_req in self.lexical_catalog:
            item = self.lexical_catalog[norm_req]
            if (is_soft and item["dimension"] == "soft_skills") or (not is_soft and item["dimension"] != "soft_skills"):
                return {
                    "score": 1.0,
                    "weight": item["weight"],
                    "dimension": item["dimension"],
                    "match_type": "EXACT",
                    "matched_entity": item["name"],
                }

        # B) Coincidencia de frase contenida con límites de palabra (\b)
        best_lexical = None
        for term, item in self.lexical_catalog.items():
            # Separación estricta entre dimensiones hard y soft
            if is_soft and item["dimension"] != "soft_skills":
                continue
            if not is_soft and item["dimension"] == "soft_skills":
                continue

            # Coincidencia con límites de palabra para evitar subcadenas espurias
            pattern = r"\b" + re.escape(term) + r"\b"
            req_pattern = r"\b" + re.escape(norm_req) + r"\b"

            is_match = False
            if re.search(pattern, norm_req):
                is_match = True
            elif len(norm_req) >= 4 and re.search(req_pattern, term):
                is_match = True

            if is_match:
                if best_lexical is None or item["weight"] > best_lexical["weight"]:
                    best_lexical = item

        if best_lexical is not None:
            return {
                "score": 1.0,
                "weight": best_lexical["weight"],
                "dimension": best_lexical["dimension"],
                "match_type": "PHRASE",
                "matched_entity": best_lexical["name"],
            }

        # 2. Respaldo Semántico con Similitud Coseno Calibrada
        req_vector = self.engine.encode([req_text])
        if is_soft and len(self.soft_skill_vectors) > 0:
            sims = self.engine.cosine_similarity_matrix(req_vector, self.soft_skill_vectors)[0]
            best_idx = int(np.argmax(sims))
            raw_sim = float(sims[best_idx])
            calibrated = calibrate_cosine_similarity(raw_sim)
            return {
                "score": calibrated,
                "weight": 1.0,
                "dimension": "soft_skills",
                "match_type": "SEMANTIC",
                "matched_entity": self.soft_skill_texts[best_idx][:40] + "...",
            }
        elif len(self.hard_skill_vectors) > 0:
            sims = self.engine.cosine_similarity_matrix(req_vector, self.hard_skill_vectors)[0]
            best_idx = int(np.argmax(sims))
            raw_sim = float(sims[best_idx])
            calibrated = calibrate_cosine_similarity(raw_sim)
            meta = self.hard_skill_metadata[best_idx]
            return {
                "score": calibrated,
                "weight": meta.get("weight", 1.0),
                "dimension": meta.get("dimension", "hard_skills"),
                "match_type": "SEMANTIC",
                "matched_entity": meta.get("name", self.hard_skill_texts[best_idx][:40]),
            }

        return {
            "score": 0.0,
            "weight": 1.0,
            "dimension": "hard_skills",
            "match_type": "NONE",
            "matched_entity": "",
        }


# Instancia única en memoria para reuso rápido
indexer = MasterCVIndexer()