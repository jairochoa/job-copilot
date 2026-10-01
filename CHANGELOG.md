# Changelog

## [1.0.0] - 2026-09-30
### Añadido
- Motor de matching híbrido multidimensional (Hard, Soft, Educación, Idiomas, Sectores).
- Extracción estructurada con Gemini REST y esquemas Pydantic.
- Deduplicación determinista con huella SHA-256 y SQLite idempotente.
- Scraper con JobSpy multicanal con filtrado geográfico de portales.
- Compilador ATS automático de CVs en PDF/Word y reporte en Excel.
- Interfaz CLI dinámica mediante `argparse` con banderas configurables en `main.py`.
- Configuración centralizada `src/config.py` y plantilla exhaustiva `.env.example`.

### Modificado / Refactorizado
- Eliminación total de funciones y datos de prueba (`seed_initial_jobs_if_empty` y vacantes mock).
- Cero hardcoding: todos los hiperparámetros, pesos vectoriales, umbrales y URLs desacoplados hacia `.env`.
- Extracción dinámica de entidades del CV maestro en lugar de términos fijos.
- Validación completa de la suite de pruebas unitarias (30/30 aprobadas).

## [1.1.0] - (En desarrollo)
### Planificado
- Rutina de prospección 100% remota para América y Europa (EE.UU., Canadá, UE, LatAm).
- Integración de APIs de portales remotos (Remotive, WeWorkRemotely).
- Parámetro de ejecución CLI `--scope [colombia|remote_global|all]`.
