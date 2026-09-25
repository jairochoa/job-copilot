"""
Módulo de configuración centralizada del sistema.
Desacopla parámetros del entorno, modelos, URLs y rutas del proyecto.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Forzar carga de variables desde .env
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=True)


class Settings:
    # Rutas base
    PROJECT_ROOT: Path = BASE_DIR
    DATA_DIR: Path = BASE_DIR / "data"
    OUTPUT_DIR: Path = BASE_DIR / "output"

    # Archivos clave
    MASTER_CV_PATH: Path = DATA_DIR / "master_cv.json"
    DB_PATH: Path = DATA_DIR / "jobs.db"
    EXCEL_REPORT_PATH: Path = OUTPUT_DIR / "prospectos_calificados.xlsx"

    # Configuración de Gemini / LLM
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip().strip('"').strip("'")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    GEMINI_API_BASE_URL: str = os.getenv(
        "GEMINI_API_BASE_URL",
        "https://generativelanguage.googleapis.com/v1beta",
    )
    REQUEST_TIMEOUT: int = int(os.getenv("REQUEST_TIMEOUT", "30"))

    # Configuración de Embeddings y RAG Local
    EMBEDDING_MODEL_NAME: str = os.getenv(
        "EMBEDDING_MODEL_NAME", "paraphrase-multilingual-MiniLM-L12-v2"
    )

    # Umbrales de Calificación (Scoring)
    MIN_QUALIFIED_SCORE: float = float(os.getenv("MIN_QUALIFIED_SCORE", "65.0"))
    HARD_SKILLS_WEIGHT: float = float(os.getenv("HARD_SKILLS_WEIGHT", "0.70"))
    SOFT_SKILLS_WEIGHT: float = float(os.getenv("SOFT_SKILLS_WEIGHT", "0.30"))

    @property
    def gemini_endpoint_url(self) -> str:
        """Construye dinámicamente el endpoint para generateContent."""
        return f"{self.GEMINI_API_BASE_URL}/models/{self.GEMINI_MODEL}:generateContent"


settings = Settings()