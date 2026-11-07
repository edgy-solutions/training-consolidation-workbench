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

- **Run the api**:
  ```bash
  uv run python -m uvicorn src.workbench.main:app --port 8000
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

Ingestion and semantic extraction run in the platform's doc-tools pipeline; this repo's api reads their outputs (`SOURCE_READER=store`).

## Conceptual Architecture: The 5-Module System

The project follows a strict 5-module architecture designed to decouple extraction, understanding, harmonization, and synthesis.

### Module 1: The "Asset Foundry" (Ingestion & Rendering)
*   **Goal:** Turn opaque files (PPT, PDF, DOC) into accessible atomic units (Text chunks + Images).
*   **Responsibilities:**
    *   Pipeline construction (no AI reasoning yet).
    *   High-fidelity parsing and rendering.
    *   Generating raw assets: Slide images (PNGs), Text chunks (JSON), and Source Manifests.
*   **Tech Stack:** Runs in the platform's doc-tools pipeline (outside this repo).

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

*   `src/dspy_modules/` and `src/services/` -> **Modules 3 & 5** (DSPy harmonization and generation)
*   `src/storage/` -> **Shared Infrastructure**
    *   Clients for MinIO, Weaviate and Neo4j.
*   `src/workbench/` -> **Module 4 (Workbench)**
    *   API endpoints and domain logic for the consolidation workflow (loading trees, saving plans).
*   *(Module 1 ingestion and Module 2 extraction live outside this repo, in the platform's doc-tools pipeline.)*
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
