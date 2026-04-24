# AI Working Model & Documentation Strategy

This document outlines how AI assistants should interact with this project and how we organize artifacts to ensure maximum efficiency across sessions while keeping the Git history clean.

---

## 🧠 How AI "Sees" the Project

1. **The Invisible Barrier**: AI uses search tools (`fd`, `ripgrep`) that respect `.gitignore`. Files in `docs/_AI_/` are **invisible** unless explicitly pointed to.
2. **Context Loading**: At the start of a session, the AI reads the tracked files (like `README.md`, `CLAUDE.md`, and `docs/internal/`).
3. **Knowledge Items (KIs)**: Summaries of past work are provided to the AI. These are the "memory" that links sessions together.

---

## 🏗️ The Tiered Documentation System

To balance developer experience and AI context, we use three tiers:

### Tier 1: The Permanent Record (Tracked)

* **Location**: `docs/internal/<category>/YYMMDD-topic/`
* **Categories**:
  * `architecture/`: High-level system design, ADRs, and structural diagrams. (The "How we build").
  * `features/`: Specs, detailed requirements, and implementation plans for specific modules. (The "What we build").
* **Purpose**: Stable "Source of Truth" for both humans and AI.
* **Persistence**: Committed to Git.

### Tier 2: The Working Session (Gitignored)

* **Location**: `docs/_AI_/YYMMDD-topic/`
* **Purpose**: Raw prompts, long-form research logs, and experimental notes.
* **Persistence**: Local only (ignored via `.gitignore`).

### Tier 3: The Navigation Map (Tracked)

* **Location**: `docs/CONTEXT.md`
* **Purpose**: A guide that tells the AI "Go look at folder X for previous research on Y."

---

## ⚡ Action Plan: Starting & Finalizing Features

### 1. Starting a New Feature

1. **Create Workspace**: Create a directory: `docs/_AI_/YYMMDD-topic/`.
2. **Set Requirements**: Create a `prompt.md` inside that directory.
3. **Define Scope**: In `prompt.md`, list goals, constraints, and relevant files to read.

### 2. Finalizing a Session

Before ending the chat, use this **Universal Finalizer** prompt:

> **Universal Prompt**: *"Please summarize our work today. Create a permanent record in `docs/internal/features/YYMMDD-topic/` (or architecture/) with the final results. Also, update `docs/CONTEXT.md` to link these findings to our raw logs in `docs/_AI_/YYMMDD-topic/`."*

---

## 🖋️ Markdown Styling Standards

To ensure compatibility with `markdownlint` and maintain a clean appearance, always follow these rules:

1. **Blanks Around Headings** (MD022): Always leave exactly one blank line before and after every heading.
2. **List Marker Space** (MD030): Use exactly one space after a list marker (`*`, `-`, `1.`).
3. **Heading Hierarchy** (MD001): Never skip heading levels (e.g., don't go from `#` directly to `###`).
4. **No Trailing Spaces** (MD009): Ensure no lines end with invisible whitespace.

---

## 📁 Standardized Folder Structure

```text
fpcr/
├── docs/
│   ├── internal/             <-- [TRACKED]
│   │   ├── architecture/     <-- Global system design
│   │   └── features/         <-- Feature spikes & research (YYMMDD-topic)
│   ├── _AI_/                 <-- [IGNORED] Raw session logs
│   │   └── YYMMDD-topic/     <-- Matches tracked folders
│   └── CONTEXT.md            <-- [TRACKED] The "AI entry point"
├── src/                      <-- Source code
├── .gitignore
├── CLAUDE.md                 <-- [TRACKED] This file
└── README.md                 <-- [TRACKED] Project documentation
```

---

## 🛠️ Project-Specific Guidelines

### Dependencies

* **cpaiops**: Internal library for Check Point API operations (loaded from Azure DevOps)
* **arlogi**: Internal logging library
* **typer**: CLI framework
* **rich**: Terminal formatting

### Key Modules

* **fpcr.py**: Main CLI entry point with commands for show-domains, cpcrud, search-object
* **cpsearch.py**: Domain-aware object search with group membership traversal
* **cpcrud/**: YAML-based CRUD template processing
* **utils.py**: Utility functions including timing decorators

### Environment Configuration

The project uses `.env` and `.env.secrets` files for configuration:

* `API_MGMT`: Check Point management server IP
* `API_USERNAME`: API username
* `API_PASSWORD`: API password
* `LOG_LEVEL`: Logging level (TRACE, DEBUG, INFO, etc.)
* `CPAIOPS_LOG_LEVEL`: Specific log level for cpaiops

### Type Checking

* **mypy**: Strict mode enabled, Python 3.13 target
* **pyright**: Basic mode, Python 3.13, Windows platform

### Development Workflow

1. Use `uv` for dependency management
2. Run tests with `pytest` (use `uv run pytest` as well for other tools)
3. Format with `ruff`
4. Type check with `mypy` or `pyright`

---

## 📊 Knowledge Graph Commands

This project includes custom commands for working with knowledge graphs:

### `/graphify-labeled`

Build a knowledge graph with **meaningful community labels** instead of generic "Community 1", "Community 2", etc.

```bash
/graphify-labeled                 # Current directory
/graphify-labeled <path>          # Specific path
/graphify-labeled . --obsidian    # Also generate Obsidian vault
```

**What it does:**

1. Builds the graph using `/graphify`
2. Analyzes each community's content
3. Generates meaningful labels (Rulebase Processing, Client API Layer, Caching Layer, etc.)
4. Regenerates `graph.html` with proper labels

**Example labels:**

* Rulebase Processing
* Client API Layer
* Caching Layer
* Domain Management
* WebUI Components
* Test Suite
* Example Code
* Documentation
* CPCRUD Module
* RITM Implementation

**Outputs:**

* `graphify-out/graph.html` - Interactive graph with meaningful labels
* `graphify-out/GRAPH_REPORT.md` - Audit report
* `graphify-out/community_labels.json` - Saved labels

**Quick relabel after /graphify:**

```bash
python graphify-relabel.py
```
