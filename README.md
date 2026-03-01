# BlackRoad OS — Meilisearch

> **Production-ready, blazing-fast full-text search engine** built on BM25 ranking, FTS5, faceted search, and federated multi-index queries.  Available as a Python package and an npm-compatible REST service, with first-class Stripe billing integration.

[![CI](https://github.com/BlackRoad-OS/blackroad-os-meilisearch/actions/workflows/ci.yml/badge.svg)](https://github.com/BlackRoad-OS/blackroad-os-meilisearch/actions/workflows/ci.yml)
[![License: GPL-3.0](https://img.shields.io/badge/License-GPL--3.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)

---

## Table of Contents

1. [Overview](#1-overview)
2. [Features](#2-features)
3. [Architecture](#3-architecture)
4. [Installation](#4-installation)
   - [Python (pip)](#41-python-pip)
   - [npm / Node.js client](#42-npm--nodejs-client)
5. [Quick Start](#5-quick-start)
   - [Python SDK](#51-python-sdk)
   - [CLI](#52-cli)
6. [Index Management](#6-index-management)
   - [Create an Index](#61-create-an-index)
   - [Configure Attributes](#62-configure-attributes)
   - [Add Documents](#63-add-documents)
   - [Update a Document](#64-update-a-document)
   - [Delete a Document](#65-delete-a-document)
   - [Retrieve a Document](#66-retrieve-a-document)
7. [Search](#7-search)
   - [Basic Search](#71-basic-search)
   - [Filtered Search](#72-filtered-search)
   - [Faceted Search](#73-faceted-search)
   - [Sorted Search](#74-sorted-search)
   - [Multi-Index (Federated) Search](#75-multi-index-federated-search)
8. [BM25 Ranking](#8-bm25-ranking)
9. [Statistics & Monitoring](#9-statistics--monitoring)
10. [Stripe Billing Integration](#10-stripe-billing-integration)
11. [End-to-End Testing](#11-end-to-end-testing)
12. [CI / CD](#12-ci--cd)
13. [Contributing](#13-contributing)
14. [License](#14-license)

---

## 1. Overview

**BlackRoad OS Meilisearch** is a self-hosted, open-source full-text search engine that ships as a single Python module with zero heavy dependencies beyond the standard library.  It stores indexes in a local SQLite database, supports BM25 relevance ranking with per-field weighting, and exposes a clean Python API that mirrors the official [Meilisearch](https://www.meilisearch.com/) SDK.

The engine is designed to be embedded directly inside any Python service **or** exposed as a micro-service consumed over HTTP—allowing JavaScript / Node.js frontends to talk to it through the official npm client.

---

## 2. Features

| Feature | Description |
|---|---|
| **BM25 Ranking** | Industry-standard probabilistic relevance model with configurable `k1` and `b` parameters |
| **Per-field Weighting** | Boost `title` (3×), `description` (2×), `body` (1×), or any custom weight |
| **Faceted Search** | Real-time facet distribution counts across any filterable attribute |
| **Filtered Search** | Exact-match and list-membership filters applied after BM25 scoring |
| **Sorted Results** | Sort by any `sortable_attr` in addition to relevance |
| **Multi-Index / Federated Search** | Run a single query across multiple indexes simultaneously |
| **CRUD Document API** | Add, update (partial), delete, and retrieve individual documents |
| **Persistent Storage** | SQLite-backed inverted index survives restarts |
| **CLI** | `search_engine` command for scripting and DevOps workflows |
| **Stripe Billing** | Built-in metering hooks for usage-based billing via Stripe Meters |
| **E2E Test Suite** | pytest-based test suite with coverage reporting via Codecov |

---

## 3. Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        BlackRoad Search                          │
│                                                                  │
│  ┌────────────┐   ┌──────────────────────────────────────────┐  │
│  │  Python    │   │              SearchEngine                │  │
│  │  SDK / CLI │──▶│                                          │  │
│  └────────────┘   │  create_index()   add_documents()        │  │
│                   │  search()         multi_search()          │  │
│  ┌────────────┐   │  update_document() delete_document()     │  │
│  │ npm client │──▶│  get_stats()                              │  │
│  │ (REST)     │   │                                          │  │
│  └────────────┘   │  ┌────────────────────────────────────┐  │  │
│                   │  │  SQLite (FTS5 + Inverted Index)    │  │  │
│  ┌────────────┐   │  │  indexes / index_documents         │  │  │
│  │  Stripe    │   │  │  term_index / field_stats          │  │  │
│  │  Billing   │◀──│  └────────────────────────────────────┘  │  │
│  └────────────┘   └──────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 4. Installation

### 4.1 Python (pip)

```bash
# Install directly from GitHub (production pin)
pip install git+https://github.com/BlackRoad-OS/blackroad-os-meilisearch.git

# Or clone and install in editable mode for development
git clone https://github.com/BlackRoad-OS/blackroad-os-meilisearch.git
cd blackroad-os-meilisearch
pip install -e .
```

**Requirements:** Python 3.11+, no third-party dependencies (uses `sqlite3`, `json`, `math`, `re` from the standard library).

### 4.2 npm / Node.js client

The BlackRoad Search REST layer is consumed from JavaScript using the official npm package:

```bash
npm install blackroad-meilisearch-client
```

```javascript
import { SearchClient } from 'blackroad-meilisearch-client';

const client = new SearchClient({ host: 'http://localhost:7700' });

const results = await client.index('products').search('bluetooth headphones', {
  limit: 10,
  facets: ['brand', 'category'],
});

console.log(results.hits);
```

> **Note:** Start the Python REST server before connecting the npm client:
> ```bash
> python -m src.search_engine serve --port 7700
> ```

---

## 5. Quick Start

### 5.1 Python SDK

```python
from src.search_engine import SearchEngine

# 1. Initialise (persists to ~/.blackroad/search.db by default)
engine = SearchEngine()

# 2. Create an index
engine.create_index("products", primary_key="id")

# 3. Configure searchable and filterable attributes
engine.set_searchable_attrs("products", ["title", "description", "brand"])
engine.set_filterable_attrs("products", ["category", "brand", "in_stock"])
engine.set_sortable_attrs("products", ["price", "rating"])

# 4. Add documents
engine.add_documents("products", [
    {"id": "1", "title": "Wireless Headphones", "brand": "Sony",
     "category": "audio", "price": 249.99, "in_stock": True, "rating": 4.7},
    {"id": "2", "title": "Bluetooth Speaker", "brand": "JBL",
     "category": "audio", "price": 99.99, "in_stock": True, "rating": 4.5},
    {"id": "3", "title": "USB-C Cable", "brand": "Anker",
     "category": "accessories", "price": 12.99, "in_stock": False, "rating": 4.8},
])

# 5. Search
result = engine.search("products", "wireless audio",
                       filters={"in_stock": True},
                       facets=["brand", "category"],
                       limit=10)

print(f"Found {result.total} result(s) in {result.processing_time_ms:.2f} ms")
for hit in result.hits:
    print(f"  [{hit['id']}] {hit['title']} — ${hit['price']}")

print("Facets:", result.facet_distribution)
```

### 5.2 CLI

```bash
# Create an index
python -m src.search_engine create products --primary-key id

# Add documents from a JSON file
python -m src.search_engine add products --json-file docs.json

# Search
python -m src.search_engine search products "wireless headphones" --limit 5

# View stats
python -m src.search_engine stats
python -m src.search_engine stats --index products
```

---

## 6. Index Management

### 6.1 Create an Index

```python
index = engine.create_index(
    uid="movies",          # Unique identifier
    primary_key="movie_id",
    name="Movie Catalog",  # Optional human-readable name (defaults to uid)
)
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `uid` | `str` | ✅ | Unique index identifier |
| `primary_key` | `str` | ✅ | Field used as the document ID (default: `"id"`) |
| `name` | `str` | ❌ | Human-readable display name |

### 6.2 Configure Attributes

```python
# Fields that are full-text searched
engine.set_searchable_attrs("movies", ["title", "overview", "genres"])

# Fields that can be used in filters
engine.set_filterable_attrs("movies", ["genres", "release_year", "rating"])

# Fields that can be sorted
engine.set_sortable_attrs("movies", ["release_year", "rating", "runtime"])
```

### 6.3 Add Documents

Documents are **upserted** — existing documents with the same primary key are replaced.

```python
engine.add_documents("movies", [
    {"movie_id": "tt0111161", "title": "The Shawshank Redemption",
     "release_year": 1994, "rating": 9.3, "genres": ["Drama"]},
    {"movie_id": "tt0068646", "title": "The Godfather",
     "release_year": 1972, "rating": 9.2, "genres": ["Crime", "Drama"]},
])
```

### 6.4 Update a Document

Perform a **partial update** (patch) without replacing the entire document:

```python
engine.update_document("movies", "tt0111161", {"rating": 9.4})
```

### 6.5 Delete a Document

```python
engine.delete_document("movies", "tt0111161")
```

### 6.6 Retrieve a Document

```python
doc = engine.get_document("movies", "tt0068646")
print(doc["title"])  # "The Godfather"
```

---

## 7. Search

### 7.1 Basic Search

```python
result = engine.search("movies", "godfather")
```

`SearchResult` fields:

| Field | Type | Description |
|---|---|---|
| `index_uid` | `str` | Index the query ran against |
| `query` | `str` | Original query string |
| `hits` | `List[Dict]` | Ranked document list |
| `total` | `int` | Total matching documents (before pagination) |
| `processing_time_ms` | `float` | Query latency in milliseconds |
| `facet_distribution` | `Dict[str, Dict[str, int]]` | Facet counts (when requested) |

### 7.2 Filtered Search

```python
result = engine.search(
    "movies",
    "drama",
    filters={"release_year": 1994},      # Exact match
)

# List membership filter
result = engine.search(
    "movies",
    "crime",
    filters={"genres": ["Crime", "Thriller"]},   # Match any value in list
)
```

### 7.3 Faceted Search

```python
result = engine.search(
    "movies",
    "action",
    facets=["genres", "release_year"],
)

# result.facet_distribution →
# {
#   "genres": {"Action": 42, "Adventure": 18, "Sci-Fi": 11},
#   "release_year": {"2023": 7, "2022": 12, ...}
# }
```

### 7.4 Sorted Search

```python
result = engine.search(
    "movies",
    "thriller",
    sort=["rating:desc", "release_year:desc"],
    limit=5,
    offset=0,
)
```

### 7.5 Multi-Index (Federated) Search

Search across multiple indexes in a single round trip:

```python
results = engine.multi_search([
    {"index_uid": "movies",   "query": "action",    "limit": 5},
    {"index_uid": "products", "query": "action cam", "limit": 5},
    {"index_uid": "articles", "query": "action news","limit": 3},
])

for r in results:
    print(f"{r.index_uid}: {r.total} hits")
```

---

## 8. BM25 Ranking

BlackRoad Search uses the **Okapi BM25** probabilistic ranking function with sensible defaults and per-field weighting:

```
score(q, d) = Σ IDF(tᵢ) · TF_BM25(tᵢ, d) · field_weight
```

| Parameter | Default | Description |
|---|---|---|
| `k1` | `1.5` | Term-frequency saturation — higher values reward repeated terms more |
| `b` | `0.75` | Document-length normalisation — `1.0` = full normalisation, `0.0` = none |

**Default field weights:**

| Field | Weight |
|---|---|
| `title` | 3.0 |
| `description` | 2.0 |
| `body` | 1.0 |
| Any other field | 1.0 |

Adjust parameters at initialisation time:

```python
engine = SearchEngine()
engine.k1 = 1.2   # Reduce TF saturation
engine.b  = 0.5   # Reduce length normalisation
```

**Ranking rules** (applied in priority order per index):

```python
index.ranking_rules  # ["typo", "words", "proximity", "attribute", "exactness"]
```

---

## 9. Statistics & Monitoring

```python
# Global stats
stats = engine.get_stats()
# {"indexes": 3, "total_documents": 125000}

# Per-index stats
stats = engine.get_stats("products")
# {"uid": "products", "documents": 42000, "index_size_bytes": 8192000}
```

---

## 10. Stripe Billing Integration

BlackRoad Search ships with first-class support for **Stripe usage-based billing**.  Search queries are metered and reported to Stripe so you can offer tiered search-as-a-service plans.

### 10.1 Setup

```bash
pip install stripe
```

```python
import stripe
from src.search_engine import SearchEngine

stripe.api_key = "sk_live_..."   # or sk_test_... for development

engine = SearchEngine()
```

### 10.2 Metered Query Billing

```python
import stripe
from src.search_engine import SearchEngine

engine = SearchEngine()

def metered_search(customer_id: str, subscription_item_id: str,
                   index_uid: str, query: str, **kwargs):
    """Perform a search and report usage to Stripe."""
    result = engine.search(index_uid, query, **kwargs)

    # Report one query unit to Stripe Meters
    stripe.billing.MeterEvent.create(
        event_name="search_queries",
        payload={
            "stripe_customer_id": customer_id,
            "value": "1",
        },
    )

    return result
```

### 10.3 Document Ingestion Billing

```python
def metered_add_documents(customer_id: str, index_uid: str, documents: list):
    """Ingest documents and report usage to Stripe."""
    engine.add_documents(index_uid, documents)

    stripe.billing.MeterEvent.create(
        event_name="documents_indexed",
        payload={
            "stripe_customer_id": customer_id,
            "value": str(len(documents)),
        },
    )
```

### 10.4 Recommended Stripe Products

| Product | Meter Event | Unit |
|---|---|---|
| **Search Starter** | `search_queries` | per query |
| **Indexing** | `documents_indexed` | per 1,000 documents |
| **Storage** | `index_storage_gb` | per GB / month |

> See the [Stripe Billing Meters documentation](https://stripe.com/docs/billing/meters) for full setup instructions.

---

## 11. End-to-End Testing

The test suite lives in `tests/` and is run with `pytest`.

```bash
# Install test dependencies
pip install pytest pytest-cov

# Run all tests with coverage
pytest -v --cov=src

# Run a specific test file
pytest tests/test_search_engine.py -v

# Run E2E integration tests only
pytest tests/ -v -k "e2e"
```

### Coverage Report

Coverage reports are automatically uploaded to [Codecov](https://codecov.io/) on every CI run.

### Writing E2E Tests

```python
import pytest
from src.search_engine import SearchEngine

@pytest.fixture
def engine(tmp_path):
    return SearchEngine(db_path=str(tmp_path))

def test_e2e_full_workflow(engine):
    # 1. Create index
    engine.create_index("e2e_products", primary_key="id")
    engine.set_searchable_attrs("e2e_products", ["title", "description"])
    engine.set_filterable_attrs("e2e_products", ["category"])

    # 2. Ingest documents
    engine.add_documents("e2e_products", [
        {"id": "1", "title": "Widget Alpha", "category": "widgets",
         "description": "The best widget"},
        {"id": "2", "title": "Gadget Beta",  "category": "gadgets",
         "description": "A fantastic gadget"},
    ])

    # 3. Search and assert
    result = engine.search("e2e_products", "widget")
    assert result.total == 1
    assert result.hits[0]["id"] == "1"

    # 4. Filter
    result = engine.search("e2e_products", "widget",
                           filters={"category": "gadgets"})
    assert result.total == 0

    # 5. Facets
    result = engine.search("e2e_products", "", facets=["category"])
    assert "category" in result.facet_distribution

    # 6. Update and re-search
    engine.update_document("e2e_products", "1", {"title": "Widget Alpha Pro"})
    result = engine.search("e2e_products", "pro")
    assert result.total == 1

    # 7. Delete
    engine.delete_document("e2e_products", "1")
    stats = engine.get_stats("e2e_products")
    assert stats["documents"] == 1
```

---

## 12. CI / CD

The CI pipeline is defined in [`.github/workflows/ci.yml`](.github/workflows/ci.yml) and runs on every push and pull request to `main`:

| Step | Tool | Description |
|---|---|---|
| **Lint** | `flake8` | Syntax errors (`E9`, `F63`, `F7`, `F82`) and complexity checks |
| **Test** | `pytest` | Full test suite with `pytest-cov` coverage |
| **Coverage** | `codecov` | Coverage delta reported on every PR |

---

## 13. Contributing

We welcome contributions!  Please follow these steps:

1. **Fork** the repository and create a feature branch.
2. **Write tests** for your changes in `tests/`.
3. **Lint** your code: `flake8 src/ --max-line-length=127`
4. **Test** your code: `pytest -v --cov=src`
5. Open a **Pull Request** against `main` with a clear description.

Please see [`LICENSE`](LICENSE) for licensing terms before contributing.

---

## 14. License

This project is licensed under the **GNU General Public License v3.0** — see the [`LICENSE`](LICENSE) file for details.

---

*© 2024 BlackRoad OS — Built with ❤️ for developers who demand production-grade search.*
