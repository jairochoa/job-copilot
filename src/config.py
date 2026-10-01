import os
from pathlib import Path
from typing import List
from dotenv import load_dotenv

# Silenciar warnings de symlinks y telemetría de Hugging Face
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# Forzar carga de variables desde .env
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=True)


def _split_env_list(var_name: str, default: str) -> List[str]:
    """Helper para parsear listas separadas por comas desde variables de entorno."""
    raw = os.getenv(var_name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


class Settings:
    # -------------------------------------------------------------
    # Rutas base del proyecto
    # -------------------------------------------------------------
    PROJECT_ROOT: Path = BASE_DIR
    DATA_DIR: Path = BASE_DIR / "data"
    OUTPUT_DIR: Path = BASE_DIR / "output"

    # Archivos clave
    MASTER_CV_PATH: Path = DATA_DIR / "master_cv.json"
    DB_PATH: Path = DATA_DIR / "jobs.db"
    EXCEL_REPORT_PATH: Path = OUTPUT_DIR / "prospectos_calificados.xlsx"

    # -------------------------------------------------------------
    # Configuración de Gemini / LLM
    # -------------------------------------------------------------
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip().strip('"').strip("'")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    GEMINI_API_BASE_URL: str = os.getenv(
        "GEMINI_API_BASE_URL",
        "https://generativelanguage.googleapis.com/v1beta",
    )
    REQUEST_TIMEOUT: int = int(os.getenv("REQUEST_TIMEOUT", "30"))

    # -------------------------------------------------------------
    # Configuración de Ingesta y Scraping (JobSpy)
    # -------------------------------------------------------------
    SCRAPER_SEARCH_TERMS: List[str] = _split_env_list(
        "SCRAPER_SEARCH_TERMS",
        "Data Scientist, Machine Learning Engineer, Applied AI Scientist, Senior Statistician",
    )
    SCRAPER_LOCATIONS: List[str] = _split_env_list(
        "SCRAPER_LOCATIONS",
        "Colombia, Remote",
    )
    SCRAPER_RESULTS_WANTED: int = int(os.getenv("SCRAPER_RESULTS_WANTED", "5"))
    SCRAPER_HOURS_OLD: int = int(os.getenv("SCRAPER_HOURS_OLD", "72"))
    SCRAPER_IS_REMOTE: bool = os.getenv("SCRAPER_IS_REMOTE", "false").lower() in ("true", "1", "yes")
    SCRAPER_SITES: List[str] = _split_env_list(
        "SCRAPER_SITES",
        "linkedin,indeed,glassdoor,zip_recruiter,google",
    )
    SCRAPER_COUNTRY_INDEED: str = os.getenv("SCRAPER_COUNTRY_INDEED", "colombia")
    MIN_DESCRIPTION_LENGTH: int = int(os.getenv("MIN_DESCRIPTION_LENGTH", "50"))

    # -------------------------------------------------------------
    # Configuración de Embeddings y RAG Local
    # -------------------------------------------------------------
    EMBEDDING_MODEL_NAME: str = os.getenv(
        "EMBEDDING_MODEL_NAME", "paraphrase-multilingual-MiniLM-L12-v2"
    )
    COSINE_NOISE_FLOOR: float = float(os.getenv("COSINE_NOISE_FLOOR", "0.45"))
    COSINE_STRONG_MATCH: float = float(os.getenv("COSINE_STRONG_MATCH", "0.70"))

    # -------------------------------------------------------------
    # Ponderaciones y Umbrales de Calificación (Scoring)
    # -------------------------------------------------------------
    MIN_QUALIFIED_SCORE: float = float(os.getenv("MIN_QUALIFIED_SCORE", "60.0"))
    HARD_SKILLS_WEIGHT: float = float(os.getenv("HARD_SKILLS_WEIGHT", "0.70"))
    SOFT_SKILLS_WEIGHT: float = float(os.getenv("SOFT_SKILLS_WEIGHT", "0.30"))

    # Ponderaciones internas para Hard Skills (80% Mandatory / 20% Nice-to-have)
    MANDATORY_HARD_WEIGHT: float = float(os.getenv("MANDATORY_HARD_WEIGHT", "0.80"))
    NICE_TO_HAVE_HARD_WEIGHT: float = float(os.getenv("NICE_TO_HAVE_HARD_WEIGHT", "0.20"))

    # Gatekeepers y multiplicadores
    MIN_MANDATORY_HARD_THRESHOLD: float = float(
        os.getenv("MIN_MANDATORY_HARD_THRESHOLD", "30.0")
    )
    SENIORITY_FLOOR_MULTIPLIER: float = float(
        os.getenv("SENIORITY_FLOOR_MULTIPLIER", "0.50")
    )

    # Ponderaciones dimensionales
    WEIGHT_EDUCATION: float = float(os.getenv("WEIGHT_EDUCATION", "2.0"))
    WEIGHT_LANGUAGES: float = float(os.getenv("WEIGHT_LANGUAGES", "1.5"))
    WEIGHT_INDUSTRY: float = float(os.getenv("WEIGHT_INDUSTRY", "1.5"))
    WEIGHT_HARD_SKILLS: float = float(os.getenv("WEIGHT_HARD_SKILLS", "1.0"))
    WEIGHT_CERTIFICATIONS: float = float(os.getenv("WEIGHT_CERTIFICATIONS", "1.0"))

    # -------------------------------------------------------------
    # Compilador ATS y Perfil de Candidato
    # -------------------------------------------------------------
    MAX_BULLETS_PER_COMPANY: int = int(os.getenv("MAX_BULLETS_PER_COMPANY", "3"))
    CANDIDATE_PRIMARY_LOCATION: str = os.getenv("CANDIDATE_PRIMARY_LOCATION", "Colombia / LatAm")

    @property
    def gemini_endpoint_url(self) -> str:
        """Construye dinámicamente el endpoint para generateContent."""
        return f"{self.GEMINI_API_BASE_URL}/models/{self.GEMINI_MODEL}:generateContent"


settings = Settings()