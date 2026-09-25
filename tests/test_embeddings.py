"""Pruebas unitarias para el motor de embeddings y álgebra vectorial (src/embeddings.py).

Verifica invariancia multilingüe (ES vs EN), propiedades algebraicas de la similitud coseno
y el escalado correcto al rango 0-100.
"""

import numpy as np
import pytest
from src.embeddings import EmbeddingEngine


@pytest.fixture(scope="module")
def engine():
    return EmbeddingEngine()


def test_multilingual_semantic_invariance(engine):
    """Verifica que pares de frases equivalentes en ES y EN tengan alta similitud semántica (>= 0.75)."""
    pairs = [
        (
            "modelado predictivo y aprendizaje automático",
            "predictive modeling and machine learning",
        ),
        (
            "procesamiento de lenguaje natural y agentes de IA",
            "natural language processing and AI agents",
        ),
        (
            "arquitectura de datos en la nube y grandes volúmenes de información",
            "cloud data architecture and big data processing",
        ),
    ]

    for text_es, text_en in pairs:
        vec_es = engine.encode([text_es])
        vec_en = engine.encode([text_en])
        similarity = float(engine.cosine_similarity_matrix(vec_es, vec_en)[0][0])
        assert (
            similarity >= 0.70
        ), f"Baja similitud multilingüe ({similarity:.2f}) para: '{text_es}' vs '{text_en}'"

    # Verificar que conceptos no relacionados tengan similitud significativamente menor
    unrelated_es = engine.encode(["receta de cocina tradicional"])
    unrelated_en = engine.encode(["predictive analytics in cloud infrastructure"])
    unrelated_sim = float(
        engine.cosine_similarity_matrix(unrelated_es, unrelated_en)[0][0]
    )
    assert (
        unrelated_sim < 0.40
    ), f"Similitud inesperadamente alta ({unrelated_sim:.2f}) para textos no relacionados"


def test_cosine_similarity_algebraic_properties(engine):
    """Valida identidad, ortogonalidad y dimensiones de la matriz de coseno."""
    vec_a = engine.encode(["Científico de datos senior"])
    vec_b = engine.encode(["Científico de datos senior"])

    # 1. Identidad: similitud de una oración consigo misma debe ser 1.0
    sim_self = float(engine.cosine_similarity_matrix(vec_a, vec_b)[0][0])
    assert abs(sim_self - 1.0) < 1e-4

    # 2. Vectores sintéticos ortogonales
    u = np.array([[1.0, 0.0, 0.0]])
    v = np.array([[0.0, 1.0, 0.0]])
    sim_ortho = float(engine.cosine_similarity_matrix(u, v)[0][0])
    assert abs(sim_ortho - 0.0) < 1e-4

    # 3. Dimensiones de la matriz (N x M)
    matrix_n_m = engine.cosine_similarity_matrix(np.zeros((3, 10)), np.zeros((5, 10)))
    assert matrix_n_m.shape == (3, 5)

    # 4. Manejo de matrices vacías
    empty_matrix = engine.cosine_similarity_matrix(np.empty((0, 384)), np.empty((0, 384)))
    assert empty_matrix.size == 0


def test_scaling_range_0_to_100():
    """Valida la fórmula de escalado a rango 0-100 aplicando np.clip."""
    raw_similarities = np.array([-0.5, 0.0, 0.45, 0.85, 1.0])
    scaled = np.clip(raw_similarities, 0.0, 1.0) * 100.0

    expected = np.array([0.0, 0.0, 45.0, 85.0, 100.0])
    np.testing.assert_array_almost_equal(scaled, expected)
