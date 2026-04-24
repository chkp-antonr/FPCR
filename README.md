# FPCR - Firewall Policy Change Request

A Python CLI tool for managing Check Point firewall policies through object search, CRUD operations, and domain-aware queries.

## Overview

FPCR provides a streamlined interface for interacting with Check Point management servers, enabling:

* **Domain-aware object search** across all Check Point domains
* **Group membership traversal** to understand object relationships
* **YAML-based CRUD templates** for batch object operations
* **Rich console output** for clear, formatted results

## Installation

### Prerequisites

* Python 3.13.5 or higher
* `uv` package manager
* Access to `cpaiops` internal library (Azure DevOps)

### Setup

```bash
# Clone the repository
git clone <repository-url>
cd FPCR

# Install dependencies with uv
uv sync

# Activate the virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

## Configuration

Create `.env` and `.env.secrets` files in the project root:

**.env**

```ini
API_MGMT=your-management-server-ip
API_USERNAME=your-username
LOG_LEVEL=INFO
CPAIOPS_LOG_LEVEL=INFO
```

**.env.secrets**

```ini
API_PASSWORD=your-password
```

## Usage

### Show Domains

List all available domains on the management server:

```bash
python src/fpcr.py show-domains
```

### Search Objects

Search for Check Point objects by IP, CIDR, range, or name:

```bash
# Search by IP
python src/fpcr.py search-object 192.168.1.10

# Search by CIDR
python src/fpcr.py search-object 10.0.0.0/24

# Search by name
python src/fpcr.py search-object "web-server-prod"

# Set max group traversal depth
python src/fpcr.py search-object "object-name" --max-depth 5
```

### CRUD Operations

Process YAML templates for creating, updating, or deleting objects:

```bash
# Process template (publishes changes)
python src/fpcr.py cpcrud template.yaml

# Process template without publishing
python src/fpcr.py cpcrud template.yaml --no-publish
```

### Test Logging

Verify logging configuration:

```bash
python src/fpcr.py test-logs
```

## WebUI

The FPCR tool includes a web-based UI built with FastAPI and React.

### Features

* Per-user RADIUS authentication
* Domain listing and management
* Session-based authentication with SQLite storage

### Package Selection Flow

The Domains page includes a cascading selection flow for exploring policy packages:

1. **Domain Selection** - Search and select a domain
2. **Package Selection** - Search and select a policy package
3. **Section View** - View all sections with their rule ranges
4. **Position Selection** - Choose Top, Bottom, or Custom rule number

This provides the foundation for rule insertion operations in Phase 2.

### Quick Start

See [Implementation Summary](docs/internal/features/260219-webui/IMPLEMENTATION_SUMMARY.md) for detailed instructions.

**Development (Two terminals):**

```bash
# Terminal 1 - Backend
uv run uvicorn src.fa.app:app --reload --reload-exclude ".venv" --port 8000

# Terminal 2 - Frontend (dev mode)
cd webui && npm run dev
```

Visit http://localhost:5173

**Production (Single terminal):**

```bash
cd webui && npm run build && cd ..
uv run uvicorn src.fa.app:app --host 0.0.0.0 --port 8000
```

Visit http://localhost:8000

### Environment Configuration

Add to `.env`:

```ini
WEBUI_SECRET_KEY=<generate-with-python>
WEBUI_SESSION_AGE_HOURS=8
WEBUI_CORS_ORIGINS=http://localhost:5173,http://localhost:8000
```

Generate a proper Fernet key:

```python
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
```

## Project Structure

```
fpcr/
├── src/
│   ├── fpcr.py           # Main CLI entry point
│   ├── cpsearch.py       # Object search and domain queries
│   ├── cpcrud/           # CRUD template processing
│   ├── cpaiops/          # Check Point API operations library
│   ├── arlogi/           # Logging library
│   └── utils.py          # Utility functions
├── docs/
│   ├── internal/         # Tracked documentation
│   ├── _AI_/             # AI session logs (gitignored)
│   └── CONTEXT.md        # AI navigation map
├── tests/                # Test files
├── .env                  # Environment configuration
├── .env.secrets          # Sensitive environment variables
├── CLAUDE.md             # AI working model
└── README.md             # This file
```

## Development

### Running Tests

```bash
pytest
```

### Code Quality

```bash
# Format code
ruff format .

# Lint code
ruff check .

# Type checking with mypy
mypy src/

# Type checking with pyright
pyright src/
```

### Dependencies

* `aiohttp` - Async HTTP client
* `aiosqlite` - Async SQLite support
* `asyncpg` - Async PostgreSQL support
* `cp-mgmt-api-sdk` - Check Point management API
* `pydantic` - Data validation
* `sqlalchemy` - SQL toolkit
* `sqlmodel` - SQLModel for ORM
* `rich` - Terminal formatting
* `typer` - CLI framework

## Documentation

For detailed documentation about project architecture and features, see:

* `docs/CONTEXT.md` - Project context and research history
* `CLAUDE.md` - AI working model and documentation strategy
* `docs/internal/` - Architecture and feature documentation

## License

Internal use only.
