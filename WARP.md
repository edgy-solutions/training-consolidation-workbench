# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Tooling and common commands

The project uses [uv](https://github.com/astral-sh/uv) for fast Python package management and virtual environments.

### Setup

1.  **Install uv**:
    ```powershell
    # Windows
    powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
    ```
    ```bash
    # Linux/macOS
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

2.  **Create Virtual Environment**:
    ```bash
    uv venv
    ```
    *This creates a `.venv` directory in the project root.*

3.  **Install Dependencies**:
    ```bash
    uv pip install -e .
    ```

### BAML (Extraction Logic)

This project uses **BAML** (Boundary-Aware Model Language) for structured LLM outputs. The `baml-py` dependency handles the runtime, but you need to generate the client code when the `.baml` files change.

**Generate Python Client**:
Whenever you modify files in `baml_src/`, regenerate the Python client:
```bash
baml-cli generate
```
*Note: If `baml-cli` is not found, ensure you have installed the project dependencies via `uv pip install -e .`*

### Common Commands

- **Run Dagster**:
  ```bash
  # Windows
  .venv\Scripts\dagster dev -m src.pipelines.definitions
  
  # Linux/macOS
  source .venv/bin/activate
  dagster dev -m src.pipelines.definitions
  ```

- **Run Tests**:
  *(Not yet configured, but will use `uv run pytest`)*

**Windows:**
- **Poppler**: Download from [poppler-windows](https://github.com/oschwartz10612/poppler-windows/releases), extract, and add the `bin` folder to your PATH.
- **LibreOffice**: Install from [libreoffice.org](https://www.libreoffice.org/). Ensure `soffice.exe` is in your PATH (default locations are checked automatically).
- **Docker Desktop**: Required for MinIO.

**macOS:**
```bash
brew install poppler libmagic tesseract --cask libreoffice
```

### Verification

To verify Module 1 (Asset Foundry):

**Windows (PowerShell):**
```powershell
./verify_sensor.ps1
```

**Linux / macOS (Bash):**
```bash
chmod +x verify_sensor.sh
./verify_sensor.sh
```
This script will:
1. Check for Docker and start MinIO.
2. Install dependencies.
3. Create a test document.
4. Run the Dagster ingestion pipeline.

Check results at http://localhost:9001 (User/Pass: `minioadmin`). Look for the `training-content` bucket.

## Conceptual Architecture: The 5-Module System

The project follows a strict 5-module architecture designed to decouple extraction, understanding, harmonization, and synthesis.

### Module 1: The "Asset Foundry" (Ingestion & Rendering)
*   **Goal:** Turn opaque files (PPT, PDF, DOC) into accessible atomic units (Text chunks + Images).
*   **Responsibilities:**
    *   Pipeline construction (no AI reasoning yet).
    *   High-fidelity parsing and rendering.
    *   Generating raw assets: Slide images (PNGs), Text chunks (JSON), and Source Manifests.
*   **Tech Stack:** Dagster, Unstructured.io, python-pptx, pdf2image, MinIO (S3).

### Module 2: The "Cartographer" (Structure & Concept Extraction)
*   **Goal:** Understand content structure and map it to the Graph.
*   **Responsibilities:**
    *   Extracting Outlines (TOC/Headers) -> Neo4j Section nodes.
    *   Mining Concepts (from Slide Text) -> Neo4j Concept nodes.
    *   Vector Indexing -> Weaviate (linked to Neo4j UUIDs).
*   **Tech Stack:** BAML (strict typing), Ollama (Llama 3/Mistral), Neo4j, Weaviate.

### Module 3: The "Harmonizer" (Concept Alignment)
*   **Goal:** Clean up and align concepts across different business units.
*   **Responsibilities:**
    *   Identifying synonyms (e.g., "Emergency Stop" vs. "E-Halt").
    *   Clustering semantically similar terms using Chain of Thought.
    *   Creating `[:SAME_AS]` relationships or canonical nodes in Neo4j.
*   **Tech Stack:** DSPy (Chain of Thought), Neo4j.

### Module 4: The "Workbench" (The Domain Expert UI)
*   **Goal:** Visual environment for human curation.
*   **Responsibilities:**
    *   **Source Browser:** Tree view of original content (Neo4j-backed).
    *   **Slide Preview:** Displaying rendered PNGs (MinIO-backed).
    *   **Consolidation Canvas:** Drag-and-drop interface for building new outlines.
*   **Tech Stack:** React/Vue/Next.js (Frontend), Python FastAPI (Backend).

### Module 5: The "Ghostwriter" (Synthesis & Generation)
*   **Goal:** AI-assisted rewriting and content generation.
*   **Responsibilities:**
    *   Synthesizing new slides from selected source nodes.
    *   Applying style guides to merged text.
*   **Tech Stack:** DSPy (Signature Optimization), Ollama.


## Current Code Structure & Module Mapping

The codebase uses a `src/`-layout. Here is how the directory structure maps to the 5 modules:

*   `src/ingestion/` -> **Module 1 (Asset Foundry)**
    *   Contains Dagster jobs and Unstructured.io logic.
*   `src/semantic/` -> **Module 2, 3, & 5**
    *   *Recommend subdividing this package as the project grows:*
    *   `src/semantic/extraction/` -> **Module 2 (Cartographer)** (BAML/Ollama extraction logic)
    *   `src/semantic/harmonization/` -> **Module 3 (Harmonizer)** (DSPy clustering logic)
    *   `src/semantic/synthesis/` -> **Module 5 (Ghostwriter)** (DSPy generation logic)
*   `src/storage/` -> **Shared Infrastructure**
    *   Abstractions for MinIO (Mod 1), Weaviate/Neo4j (Mod 2/3).
*   `src/ui/` & `src/workbench/` -> **Module 4 (Workbench)**
    *   `src/ui/`: API endpoints and frontend serving.
    *   `src/workbench/`: Domain logic for the consolidation workflow (loading trees, saving plans).
*   `src/pipelines/`
    *   Orchestration glue that ties these modules together (e.g., triggering Module 2 after Module 1 completes).

## Recommended Development Order (Critical Path)

To minimize blockers, follow this implementation order:

1.  **Module 1 (Ingest):** Build the foundation (Raw Data -> S3).
2.  **Module 2 (Graph):** Build the structure (Nodes/Edges -> Neo4j).
3.  **Module 4 (UI - Read Only):** Visualize the data. Immediate feedback loop for parsing quality.
4.  **Module 3 (Harmonization):** Improve graph quality (deduplication/linking).
5.  **Module 5 (Synthesis):** Add generative capabilities ("Magic" button).
6.  **Module 4 (UI - Write):** Complete the builder/authoring workflow.

## How future agents should approach changes

- When implementing new features, first identify which conceptual layer(s) they belong to (ingestion, semantic, storage, UI, workbench) and place code in the corresponding `src/` package to preserve the current separation of concerns.
- When introducing new external systems or tools (e.g., different vector DB, alternative LLM runner), keep integrations behind clear interfaces in `storage/` or `semantic/` rather than wiring them directly into UI or orchestration code.
- If you add concrete build, lint, or test tooling, update both `README.md` and this `WARP.md` so future Warp instances have accurate, authoritative commands to run.
