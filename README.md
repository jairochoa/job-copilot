# 🎯 Job-Copilot: Motor Inteligente de Prospección, Evaluación Semántica y Compilación ATS

Sistema integral y modular en Python para prospección automatizada de ofertas laborales, filtrado determinista multinivel sin costo ($0), evaluación semántica profunda con modelos de lenguaje Gemini mediante llamadas HTTP REST directas, compilación dinámica de currículums de alta fidelidad optimizados para Applicant Tracking Systems (ATS) en formatos PDF y DOCX, asistente interactivo por consola con portapapeles automático y sincronización incremental hacia una bitácora viva en Microsoft Excel.

---

## 📑 Tabla de Contenido
1. [Justificación del Proyecto](#1-justificación-del-proyecto)
2. [Definición del Problema](#2-definición-del-problema)
3. [Objetivos](#3-objetivos)
   - [Objetivo General](#objetivo-general)
   - [Objetivos Específicos](#objetivos-específicos)
4. [Metodología y Arquitectura del Sistema](#4-metodología-y-arquitectura-del-sistema)
5. [Estructura y Anatomía de Módulos (Explicación Exhaustiva)](#5-estructura-y-anatomía-de-módulos-explicación-exhaustiva)
   - [src/scraper.py](#srcscraperpy)
   - [src/filter.py](#srcfilterpy)
   - [src/matcher.py](#srcmatcherpy)
   - [src/compiler.py](#srccompilerpy)
   - [src/copilot.py](#srccopilotpy)
   - [src/exporter.py](#srcexporterpy)
   - [main.py](#mainpy)
6. [Flujo de Estados en Base de Datos (SQLite)](#6-flujo-de-estados-en-base-de-datos-sqlite)
7. [Mecanismo de Sincronización Incremental hacia Excel](#7-mecanismo-de-sincronización-incremental-hacia-excel)
8. [Requisitos Previos e Instalación](#8-requisitos-previos-e-instalación)
9. [Configuración del Entorno y Seguridad de Credenciales](#9-configuración-del-entorno-y-seguridad-de-credenciales)
10. [Guía de Uso: Referencia de Comandos CLI](#10-guía-de-uso-referencia-de-comandos-cli)
11. [Control de Calidad, Pruebas y Linter](#11-control-de-calidad-pruebas-y-linter)
12. [Hoja de Ruta: Agente Autónomo de Postulación](#12-hoja-de-ruta-agente-autónomo-de-postulación)

---

## 1. Justificación del Proyecto

En el mercado laboral actual para perfiles especializados en Datos (Data Science, Machine Learning Engineering, MLOps, Data Analytics), los procesos de selección están dominados por plataformas de filtrado automático ATS (como Workday, Taleo, Greenhouse, Lever y SmartRecruiters). Estos sistemas procesan cientos de aplicaciones y descartan de forma algorítmica las candidaturas que no reflejan un calce léxico, técnico y contextual estricto con los requerimientos del cargo.

Postularse de forma manual y masiva introduce ineficiencias estructurales:
* **Desgaste por tareas repetitivas:** El tiempo invertido en navegar portales, copiar datos personales y reformular resúmenes agota la energía del candidato.
* **Tasa de conversión baja por CVs genéricos:** Enviar un currículum estándar y estático reduce drásticamente las llamadas a entrevista técnica, ya que cada empresa evalúa combinaciones dispares de tecnologías (ej. AWS vs. GCP, PySpark vs. Polars, Time Series vs. Deep Learning).
* **Falta de trazabilidad cuantitativa:** El candidato rara vez lleva una bitácora exacta de qué versión de su perfil se entregó a qué reclutador y qué porcentaje de afinidad real tenía con el rol.

**Job-Copilot** automatiza todo el ciclo de prospección y preparación, garantizando que cada postulación cuente con un currículum personalizado, denso en métricas cuantitativas, ajustado a nivel posgrado y presentado en formatos que superan los filtros algorítmicos sin intervención de diseño manual.

---

## 2. Definición del Problema

El desarrollo de este sistema aborda y mitiga los siguientes cuellos de botella tecnológicos y operativos:

1. **Fragmentación de ofertas:** Las vacantes se publican dispersas en LinkedIn, Indeed, Glassdoor, ZipRecruiter, bolsas remotas y portales propietarios, exigiendo scraping heterogéneo y normalización de esquemas.
2. **Costo y latencia de inferencia ($0 Filter Rule):** Enviar descripciones largas directamente a modelos de lenguaje propietarios (LLMs) resulta costoso e ineficiente si la oferta exige seniorities incompatibles, tecnologías ajenas o requerimientos de nacionalidad inalcanzables. Se requiere una compuerta booleana determinista previa sin costo de tokens.
3. **Incompatibilidad de parsers ATS:** El uso de plantillas en PDF con tablas complejas, doble columna desbalanceada, iconos vectoriales o gráficos suele provocar fallos de lectura en los parsers corporativos.
4. **Fricciones de SDKs y autenticación con LLMs:** Las versiones recientes de Google AI Studio generan claves de API con prefijos específicos (como `AQ.`) que provocan excepciones `401 ACCESS_TOKEN_TYPE_UNSUPPORTED` o fallas por esquemas recursivos `$defs` en SDKs estándar. Se necesita una integración directa y resiliente vía HTTP REST nativo.
5. **Pérdida de historial en exportaciones:** Regenerar hojas de cálculo con exportaciones completas destruye las notas manuales y altera el seguimiento previo del candidato.

---

## 3. Objetivos

### Objetivo General
Construir, validar y operar un pipeline automatizado, resiliente y de alto rendimiento en Python para la extracción multicanal, prefiltrado lógico, calificación semántica asistida por Gemini, generación de CVs ATS bilingües en PDF/DOCX y gestión incremental en Excel para el mercado de Data & Analytics.

### Objetivos Específicos
1. **Extracción y Deduplicación Determinista:** Consolidar vacantes de múltiples plataformas en una base SQLite relacional (`data/jobs.db`), empleando un hash SHA-256 único por combinación de empresa, título y URL para garantizar cero duplicados.
2. **Prefiltrado Booleano ($0):** Implementar filtros basados en expresiones regulares que depuren ofertas fuera del perfil objetivo antes de invocar servicios externos.
3. **Calificación Semántica Robusta:** Evaluar cada vacante contra el perfil maestro (`data/master_cv.json`) mediante la API de Gemini (`gemini-2.5-flash` / `gemini-3.5-flash-lite`), extrayendo afinidad técnica, brechas formativas y un resumen ejecutivo estructurado estrictamente en 3 oraciones de alto impacto cuantitativo.
4. **Compilación ATS Bilingüe (PDF y DOCX):** Diseñar un motor de renderizado basado en Playwright (HTML a PDF unicolumna) y `python-docx` (DOCX nativo editable) para asegurar legibilidad algorítmica total.
5. **Control de Flujo Interactivo:** Diseñar una consola CLI que cargue automáticamente en el portapapeles del sistema operativo el resumen adaptado y abra la URL de postulación en el navegador predeterminado.
6. **Bitácora Incremental en Excel:** Desarrollar un exportador basado en `openpyxl` que anexe exclusivamente vacantes nuevas a `output/pipeline_vacantes.xlsx`, preservando filtros, hipervínculos funcionales y notas manuales previas.

---

## 4. Metodología y Arquitectura del Sistema

El proyecto sigue el patrón arquitectónico de **Tuberías y Filtros (*Pipes and Filters*)**:

```text
       ┌────────────────────────────────────────────────────────┐
       │ Fuentes de Datos: LinkedIn, Indeed, Glassdoor, etc.    │
       └───────────────────────────┬────────────────────────────┘
                                   │
                                   ▼
       ┌────────────────────────────────────────────────────────┐
       │ Módulo Scraper: Extracción y normalización de metadata │
       │ Generación de job_hash único (SHA-256)                 │
       └───────────────────────────┬────────────────────────────┘
                                   │
                                   ▼
       ┌────────────────────────────────────────────────────────┐
       │ Módulo Filter: Descarte Booleano de Costo Cero ($0)    │
       └───────────┬────────────────────────────────┬───────────┘
                   │ Descarta                       │ Pasa
                   ▼                                ▼
       [ Estado: FILTERED_OUT ]         [ Estado: SCRAPED ]
                                                    │
                                                    ▼
       ┌────────────────────────────────────────────────────────┐
       │ Módulo Matcher: Evaluación Semántica Gemini (HTTP REST)│
       │ Prompting de 3 oraciones ejecutivas y métricas         │
       └───────────┬────────────────────────────────┬───────────┘
                   │ Score < MIN_MATCH_SCORE        │ Score >= MIN_MATCH_SCORE
                   ▼                                ▼
         [ Estado: DISCARDED ]            [ Estado: SCORED ]
                                                    │
                                                    ▼
       ┌────────────────────────────────────────────────────────┐
       │ Módulo Compiler: Compilación ATS (Playwright / DOCX)   │
       │ Genera: output/cv_*.pdf y output/cv_*.docx             │
       └───────────────────────────┬────────────────────────────┘
                                   │
                                   ▼
                         [ Estado: GENERATED ]
                                   │
         ┌─────────────────────────┴─────────────────────────┐
         ▼                                                   ▼
┌──────────────────────────────────┐        ┌──────────────────────────────────┐
│ CLI Copilot: main.py --apply     │        │ Exporter: main.py --export-excel │
│ Portapapeles + Apertura Navegador│        │ output/pipeline_vacantes.xlsx    │
│ Actualiza a: APPLIED             │        │ Append incremental de nuevos IDs │
└──────────────────────────────────┘        └──────────────────────────────────┘
```

---

## 5. Estructura y Anatomía de Módulos (Explicación Exhaustiva)

```text
job-copilot/
├── data/
│   ├── jobs.db                 # Base de datos relacional SQLite (tabla: job_applications)
│   └── master_cv.json          # Perfil maestro enriquecido (experiencia, educación, proyectos)
├── output/                     # Artefactos compilados e ignorados por Git
│   ├── cv_*.pdf                # Currículums compilados en formato PDF para ATS
│   ├── cv_*.docx               # Currículums editables en formato Word DOCX
│   └── pipeline_vacantes.xlsx  # Bitácora incremental en hoja de cálculo
├── src/
│   ├── __init__.py
│   ├── scraper.py              # Extracción y deduplicación de vacantes
│   ├── filter.py               # Prefiltro léxico y determinista
│   ├── matcher.py              # Evaluador semántico con Gemini HTTP REST y Pydantic
│   ├── compiler.py             # Compilador documental ATS (Playwright + python-docx)
│   ├── copilot.py              # Asistente interactivo en terminal con clipboard
│   └── exporter.py             # Sincronizador incremental hacia Excel (openpyxl)
├── templates/
│   └── cv_ats_template.html    # Plantilla tipográfica HTML base para renderizado PDF
├── tests/
│   └── test_matcher.py         # Suite unitaria con mocks de requests y esquemas Pydantic
├── main.py                     # Orquestador y punto de entrada CLI
├── pyproject.toml              # Configuración de linter (Ruff) y herramientas
├── requirements.txt            # Declaración de librerías del proyecto
├── .env.example                # Plantilla pública de variables requeridas
└── .gitignore                  # Exclusiones de control de versiones (.env, output/, etc.)
```

### `src/scraper.py`
* **Propósito:** Conectar con proveedores de vacantes (como la librería JobSpy) y extraer registros según parámetros de búsqueda (cargos, países, modalidad remota).
* **Lógica especial:**
  * Normaliza títulos, descripciones y URLs.
  * Calcula un hash SHA-256 denominado `job_hash` a partir del trinomio `(company, title, clean_url)`.
  * Realiza una inserción idempotente en la base de datos `data/jobs.db`: si el `job_hash` ya existe, descarta la inserción para no alterar el estado histórico de postulaciones previas.

### `src/filter.py`
* **Propósito:** Eliminar vacantes no compatibles sin realizar llamadas de red a APIs externas, reduciendo el consumo de cuotas y costos.
* **Lógica especial:**
  * Evalúa títulos y textos de la vacante contra listas de palabras clave positivas (ej. `data scientist`, `machine learning`, `analytics engineer`) y negativas (ej. `java backend`, `sales representative`, `clearance required`).
  * Las ofertas incompatibles se mueven al estado `FILTERED_OUT`. Las que superan el filtro quedan en `SCRAPED`.

### `src/matcher.py`
* **Propósito:** Núcleo de inteligencia semántica. Contrasta los requerimientos específicos de cada vacante contra el perfil del postulante (`data/master_cv.json`).
* **Decisiones de Diseño y Estabilidad:**
  * **Llamadas HTTP REST Directas:** Realiza solicitudes directas mediante `requests.post` al endpoint `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}`. Esto evita las incompatibilidades de autenticación que sufren los SDKs con claves de Google AI Studio con formato `AQ.`.
  * **Eliminación de esquemas recursivos (`$defs`):** Para evitar errores de serialización JSON Schema (`INVALID_ARGUMENT`) con Pydantic en Gemini, se envía únicamente `responseMimeType: application/json` y se parsea la respuesta con el modelo flexible `CandidateEvaluation(BaseModel)` con `populate_by_name=True`.
  * **Prompt Ejecutivo Estricto:** El modelo sigue una instrucción invariable para redactar el `tailored_summary` en exactamente tres oraciones:
    1. Grado académico de posgrado (Magíster en Estadística / M.Sc. in Statistics), años de experiencia y especialidad.
    2. Stack tecnológico duro alineado explícitamente a las herramientas solicitadas en la vacante.
    3. Logro cuantificable con impacto medible en porcentaje o métricas de negocio.
  * Si la calificación (`match_score`) es mayor o igual a `MIN_MATCH_SCORE`, la vacante avanza a `SCORED`; si no, pasa a `DISCARDED`.

### `src/compiler.py`
* **Propósito:** Generar los archivos físicos del currículum adaptado en PDF y DOCX.
* **Lógica especial:**
  * Carga `data/master_cv.json` y la plantilla `templates/cv_ats_template.html`.
  * Inyecta el titular adaptado (`tailored_headline`), el resumen de 3 oraciones (`tailored_summary`) y reordena los logros relevantes según el análisis semántico.
  * **Generación PDF:** Ejecuta una instancia controlada de Chromium mediante **Playwright**, renderizando el HTML con márgenes de 0.5 pulgadas, fuentes universales y estructura de una sola columna sin tablas anidadas ni fondos decorativos.
  * **Generación DOCX:** Emplea **python-docx** para construir un archivo editable gemelo, garantizando compatibilidad con empresas cuyos portales rechazan PDFs.

### `src/copilot.py`
* **Propósito:** Asistente interactivo por línea de comandos para agilizar el envío de candidaturas.
* **Lógica especial:**
  * Lee las vacantes en estado `SCORED` o `READY_TO_APPLY` ordenadas de mayor a menor `match_score`.
  * Muestra en pantalla el resumen de la empresa, cargo, puntuación y rationale técnico.
  * Al confirmar el usuario, **copia automáticamente el `tailored_summary` al portapapeles del sistema operativo** (vía `pyperclip` o APIs nativas de Windows/Linux) y abre la URL de postulación en el navegador web predeterminado.
  * Al regresar a la terminal, permite marcar la vacante como `APPLIED`.

### `src/exporter.py`
* **Propósito:** Sincronizar de manera incremental la base de datos hacia una hoja de cálculo sin pérdida de datos manuales.
* **Lógica especial:**
  * Lee el archivo `output/pipeline_vacantes.xlsx` si ya existe y carga en un conjunto en memoria (`set`) todos los `job_hash` registrados en la primera columna.
  * Consulta en SQLite la tabla `job_applications` y detecta cuáles registros no están presentes en el Excel.
  * Agrega al final (`append`) únicamente las nuevas filas con estilos empresariales (cabecera azul marino `#1F497D`, texto blanco en negrita, bordes finos, celdas alineadas y enlaces web con la función `=HYPERLINK`).
  * Congela la fila superior y activa autofiltros automáticos. Si no hay vacantes nuevas, no altera el archivo.

### `main.py`
* **Propósito:** Orquestador principal por línea de comandos (CLI). Interpreta banderas como `--scrape`, `--evaluate`, `--compile`, `--apply`, `--export-excel` y `--stats`, o ejecuta el pipeline completo de extremo a extremo.

---

## 6. Flujo de Estados en Base de Datos (SQLite)

La persistencia de datos reside en `data/jobs.db`, principalmente en la tabla `job_applications`. Cada fila transita por los siguientes estados:

| Estado | Descripción |
| :--- | :--- |
| `SCRAPED` | Vacante extraída del portal web y almacenada; aún no evaluada por el LLM. |
| `FILTERED_OUT` | Descartada por el prefiltro léxico booleano ($0 costo de tokens). |
| `SCORED` | Evaluada por Gemini con puntaje semántico igual o superior al umbral (`match_score >= MIN_MATCH_SCORE`). |
| `DISCARDED` | Evaluada por Gemini pero con puntaje semántico inferior al umbral. |
| `GENERATED` | Currículums ATS compilados con éxito en `output/` (PDF y DOCX). |
| `APPLIED` | Postulación completada por el usuario a través del CLI o marcada manualmente. |

---

## 7. Mecanismo de Sincronización Incremental hacia Excel

El exportador `src/exporter.py` resuelve la desincronización entre procesos automáticos y revisiones manuales:

1. **Lectura no destructiva:** Si `output/pipeline_vacantes.xlsx` existe, el módulo abre el libro mediante `openpyxl.load_workbook()` sin sobrescribir ni vaciar el contenido existente.
2. **Control por Clave Primaria:** Recorre la columna A (*Hash ID*) e indexa los identificadores.
3. **Inserción Selectiva:** Solo las vacantes de SQLite cuyo `job_hash` sea nuevo son añadidas al final de la tabla.
4. **Preservación de Cambios:** Si el usuario agregó columnas personalizadas, notas o cambió colores en Excel, dichos cambios se mantienen intactos en las ejecuciones posteriores.
5. **Columnas de Control Generadas:**
   * `Hash ID`, `Score`, `Perfil Objetivo`, `Portal / Fuente`, `Tipo ATS`, `Requiere Login`
   * `Empresa`, `Cargo`, `Ubicación`, `Idioma`, `Estado Pipeline`, `Estado Postulación (Agente)`
   * `URL Directa` (Hipervínculo funcional), `Ruta CV PDF`, `Ruta CV DOCX`
   * `Headline ATS`, `Resumen Adaptado (Tailored Summary)`, `Razón del Score (Rationale)`
   * `Fecha Scraped`, `Fecha Postulado`

---

## 8. Requisitos Previos e Instalación

### Prerrequisitos del Sistema
* **Python:** Versión 3.11, 3.12 o 3.14 con pip configurado en el PATH del sistema.
* **Git:** Para clonación y control de versiones.
* **Conexión a Internet:** Para scraping y peticiones HTTPS a la API de Gemini.

### Instalación Paso a Paso

1. **Clonar el repositorio:**
   ```bash
   git clone https://github.com/jairochoa/job-copilot.git
   cd job-copilot
   ```

2. **Crear y activar el entorno virtual:**
   * En Windows (PowerShell):
     ```powershell
     python -m venv .venv
     .\.venv\Scripts\Activate.ps1
     ```
   * En Linux o macOS:
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```

3. **Instalar dependencias del proyecto:**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Instalar el motor de renderizado Chromium para Playwright:**
   ```bash
   playwright install chromium
   ```

---

## 9. Configuración del Entorno y Seguridad de Credenciales

El sistema utiliza variables de entorno declaradas en un archivo local `.env`.

> ⚠️ **REGLA DE SEGURIDAD ESTRICTA:**  
> Nunca agregues tu clave real de API dentro de `.env.example` ni la confirmes en Git. El archivo `.env` está expresamente incluido en `.gitignore` para proteger tus credenciales contra escaneos automáticos de seguridad (*Push Protection* de GitHub).

1. **Crear el archivo `.env` a partir de la plantilla:**
   ```powershell
   Copy-Item .env.example .env
   ```

2. **Definir los valores en `.env`:**
   ```env
   # Clave de API obtenida en Google AI Studio (https://aistudio.google.com/)
   GEMINI_API_KEY=AIzaSyTuClaveRealSinComillas

   # Modelo utilizado para evaluación semántica
   GEMINI_MODEL=gemini-2.5-flash

   # Umbral mínimo de afinidad para calificar vacantes (0 a 100)
   MIN_MATCH_SCORE=75

   # Rutas de base de datos y archivos de salida
   DATABASE_PATH=data/jobs.db
   MASTER_CV_PATH=data/master_cv.json
   EXCEL_PIPELINE_PATH=output/pipeline_vacantes.xlsx
   ```

---

## 10. Guía de Uso: Referencia de Comandos CLI

El punto de entrada unificado es `main.py`. Puede invocarse con distintas banderas según la tarea requerida:

### Pipeline Completo (End-to-End)
Ejecuta secuencialmente la extracción, el filtrado, la evaluación semántica, la compilación de CVs y la actualización del archivo Excel:
```powershell
python main.py
```

### 1. Solo Extracción de Vacantes (`--scrape`)
Ejecuta la búsqueda de ofertas en las plataformas configuradas y las registra en SQLite en estado `SCRAPED`:
```powershell
python main.py --scrape
```

### 2. Solo Evaluación Semántica (`--evaluate`)
Toma las vacantes pendientes en estado `SCRAPED`, realiza el llamado a Gemini y las clasifica en `SCORED` o `DISCARDED`:
```powershell
python main.py --evaluate
```

### 3. Compilación de Currículums ATS (`--compile`)
Genera los documentos PDF y DOCX en la carpeta `output/` para todas las vacantes con estado `SCORED`:
```powershell
python main.py --compile
```

### 4. Asistente Interactivo de Postulación (`--apply`)
Abre la consola asistida: muestra las vacantes aprobadas, copia automáticamente al portapapeles el resumen adaptado y abre el enlace de la oferta en el navegador:
```powershell
python main.py --apply
```

### 5. Sincronización Incremental a Excel (`--export-excel`)
Lee `data/jobs.db` y agrega únicamente las vacantes que no existan previamente en `output/pipeline_vacantes.xlsx`:
```powershell
python main.py --export-excel
```

### 6. Inspección de Estadísticas del Embudo (`--stats`)
Presenta un balance cuantitativo consolidado con el conteo de vacantes por estado:
```powershell
python main.py --stats
```

---

## 11. Control de Calidad, Pruebas y Linter

El repositorio incluye validación de tipos, análisis estático y pruebas unitarias automatizadas:

### 1. Pruebas Unitarias con `pytest`
Verifican el parsing del modelo de Gemini, los esquemas de Pydantic, la consistencia de los prompts y las llamadas HTTP mockeadas:
```powershell
pytest -v
```
*(Resultado esperado: 19 passed en suite completa).*

### 2. Verificación de Código con `ruff`
Garantiza el cumplimiento estricto de los estándares PEP 8, orden de importaciones y ausencia de errores sintácticos o variables huérfanas:
```powershell
ruff check .
```
*(Resultado esperado: `All checks passed!` sin advertencias).*

---

## 12. Hoja de Ruta: Agente Autónomo de Postulación

La arquitectura actual prepara el terreno para la siguiente fase evolutiva del proyecto:

1. **Ampliación de Fuentes Ligeras:** Integración de conectores para APIs y feeds RSS de plataformas remotas (RemoteOK, Remotive, We Work Remotely, JobLeads).
2. **Agente Playwright Autónomo (*Quick Apply*):** Módulo en segundo plano que lea las vacantes en estado `READY_TO_APPLY` del Excel, navegue a portales estándar sin autenticación pesada (Greenhouse, Lever), complete automáticamente los campos de formulario, adjunte el PDF compilado e inyecte el resumen ejecutivo.
3. **Modo Supervisado (*Human-in-the-Loop*):** Manejo inteligente de captchas o validaciones por correo electrónico mediante pausas programadas y alertas acústicas o por consola antes del envío final.

---

## 📄 Licencia y Responsabilidad
Herramienta de uso personal desarrollada con fines de optimización y automatización profesional. Al utilizar scrapers o agentes automáticos en sitios de empleo, asegúrate de cumplir con los términos de servicio, políticas de uso aceptable y cuotas razonables de cada plataforma.