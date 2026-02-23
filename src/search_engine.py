#!/usr/bin/env python3
"""
BlackRoad Search Engine - Meilisearch-inspired full-text search
Implements BM25 ranking, faceted search, filtering, and multi-index queries.
"""

import sqlite3
import json
import argparse
import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any, Set
from collections import defaultdict


@dataclass
class Index:
    """Search index metadata"""
    uid: str
    name: str
    primary_key: str
    created_at: datetime
    updated_at: datetime
    total_documents: int
    facets: List[str] = field(default_factory=list)
    ranking_rules: List[str] = field(default_factory=lambda: ["typo", "words", "proximity", "attribute", "exactness"])
    searchable_attrs: List[str] = field(default_factory=list)
    filterable_attrs: List[str] = field(default_factory=list)
    sortable_attrs: List[str] = field(default_factory=list)


@dataclass
class SearchResult:
    """Search result"""
    index_uid: str
    query: str
    hits: List[Dict]
    total: int
    processing_time_ms: float
    facet_distribution: Dict[str, Dict[str, int]] = field(default_factory=dict)


class SearchEngine:
    """
    Full-text search engine with BM25 ranking, FTS5, facets, filters.
    """

    def __init__(self, db_path: Optional[str] = None):
        """Initialize search engine"""
        engine_dir = Path(db_path or "~/.blackroad").expanduser()
        engine_dir.mkdir(parents=True, exist_ok=True)

        self.db_path = engine_dir / "search.db"
        self.indexes: Dict[str, Index] = {}
        
        self._init_db()
        self._load_indexes()

        # BM25 parameters
        self.k1 = 1.5  # Term frequency saturation
        self.b = 0.75  # Field length normalization

    def _init_db(self):
        """Initialize database schema"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS indexes (
                    uid TEXT PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    primary_key TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    total_documents INTEGER DEFAULT 0,
                    facets TEXT,
                    ranking_rules TEXT,
                    searchable_attrs TEXT,
                    filterable_attrs TEXT,
                    sortable_attrs TEXT
                )
            """)

            # FTS5 virtual table for each index is created on demand
            conn.execute("""
                CREATE TABLE IF NOT EXISTS index_documents (
                    index_uid TEXT NOT NULL,
                    doc_id TEXT NOT NULL,
                    document TEXT NOT NULL,
                    PRIMARY KEY (index_uid, doc_id)
                )
            """)

            # Field statistics for BM25
            conn.execute("""
                CREATE TABLE IF NOT EXISTS field_stats (
                    index_uid TEXT NOT NULL,
                    field TEXT NOT NULL,
                    total_docs INTEGER,
                    avg_length REAL,
                    PRIMARY KEY (index_uid, field)
                )
            """)

            # Inverted index for full-text search
            conn.execute("""
                CREATE TABLE IF NOT EXISTS term_index (
                    index_uid TEXT NOT NULL,
                    term TEXT NOT NULL,
                    doc_id TEXT NOT NULL,
                    field TEXT NOT NULL,
                    positions TEXT,
                    PRIMARY KEY (index_uid, term, doc_id, field)
                )
            """)

            conn.commit()

    def _load_indexes(self):
        """Load all indexes from database"""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT * FROM indexes").fetchall()

        for row in rows:
            index = Index(
                uid=row[0],
                name=row[1],
                primary_key=row[2],
                created_at=datetime.fromisoformat(row[3]),
                updated_at=datetime.fromisoformat(row[4]),
                total_documents=row[5],
                facets=json.loads(row[6]) if row[6] else [],
                ranking_rules=json.loads(row[7]) if row[7] else [],
                searchable_attrs=json.loads(row[8]) if row[8] else [],
                filterable_attrs=json.loads(row[9]) if row[9] else [],
                sortable_attrs=json.loads(row[10]) if row[10] else []
            )
            self.indexes[index.uid] = index

    # ========================================================================
    # Index Management
    # ========================================================================

    def create_index(self, uid: str, primary_key: str = "id", name: Optional[str] = None) -> Index:
        """Create new search index"""
        if uid in self.indexes:
            raise ValueError(f"Index {uid} already exists")

        name = name or uid
        now = datetime.utcnow()

        index = Index(
            uid=uid,
            name=name,
            primary_key=primary_key,
            created_at=now,
            updated_at=now,
            total_documents=0
        )

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO indexes 
                   (uid, name, primary_key, created_at, updated_at, total_documents, 
                    facets, ranking_rules, searchable_attrs, filterable_attrs, sortable_attrs)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (uid, name, primary_key, now.isoformat(), now.isoformat(), 0,
                 json.dumps([]), json.dumps(index.ranking_rules),
                 json.dumps([]), json.dumps([]), json.dumps([]))
            )
            conn.commit()

        self.indexes[uid] = index
        return index

    def add_documents(self, index_uid: str, documents: List[Dict]):
        """Add/upsert documents and build inverted index"""
        if index_uid not in self.indexes:
            raise ValueError(f"Index {index_uid} not found")

        index = self.indexes[index_uid]
        primary_key = index.primary_key

        with sqlite3.connect(self.db_path) as conn:
            for doc in documents:
                doc_id = str(doc.get(primary_key, ""))
                if not doc_id:
                    raise ValueError(f"Document missing primary key: {primary_key}")

                # Store raw document
                conn.execute(
                    "INSERT OR REPLACE INTO index_documents (index_uid, doc_id, document) VALUES (?, ?, ?)",
                    (index_uid, doc_id, json.dumps(doc))
                )

                # Build term index
                for field, value in doc.items():
                    if field == primary_key:
                        continue
                    
                    terms = self._tokenize(str(value))
                    positions = list(range(len(terms)))

                    for term in set(terms):
                        conn.execute(
                            """INSERT OR REPLACE INTO term_index 
                               (index_uid, term, doc_id, field, positions)
                               VALUES (?, ?, ?, ?, ?)""",
                            (index_uid, term, doc_id, field, json.dumps(positions))
                        )

            # Update stats
            doc_count = len(documents)
            index.total_documents += doc_count
            index.updated_at = datetime.utcnow()

            conn.execute(
                "UPDATE indexes SET total_documents = ?, updated_at = ? WHERE uid = ?",
                (index.total_documents, index.updated_at.isoformat(), index_uid)
            )
            conn.commit()

    def update_document(self, index_uid: str, doc_id: str, partial_doc: Dict):
        """Update specific fields in document"""
        if index_uid not in self.indexes:
            raise ValueError(f"Index {index_uid} not found")

        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT document FROM index_documents WHERE index_uid = ? AND doc_id = ?",
                (index_uid, doc_id)
            ).fetchone()

        if not row:
            raise ValueError(f"Document {doc_id} not found")

        doc = json.loads(row[0])
        doc.update(partial_doc)
        self.add_documents(index_uid, [doc])

    def delete_document(self, index_uid: str, doc_id: str):
        """Delete document"""
        if index_uid not in self.indexes:
            raise ValueError(f"Index {index_uid} not found")

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM index_documents WHERE index_uid = ? AND doc_id = ?",
                (index_uid, doc_id)
            )
            conn.execute(
                "DELETE FROM term_index WHERE index_uid = ? AND doc_id = ?",
                (index_uid, doc_id)
            )
            conn.commit()

        index = self.indexes[index_uid]
        index.total_documents = max(0, index.total_documents - 1)
        index.updated_at = datetime.utcnow()

    def get_document(self, index_uid: str, doc_id: str) -> Optional[Dict]:
        """Get single document"""
        if index_uid not in self.indexes:
            raise ValueError(f"Index {index_uid} not found")

        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT document FROM index_documents WHERE index_uid = ? AND doc_id = ?",
                (index_uid, doc_id)
            ).fetchone()

        return json.loads(row[0]) if row else None

    # ========================================================================
    # Search Operations
    # ========================================================================

    def search(self, index_uid: str, query: str, filters: Optional[Dict] = None,
               facets: Optional[List[str]] = None, sort: Optional[List[str]] = None,
               limit: int = 20, offset: int = 0) -> SearchResult:
        """Search index with BM25 ranking"""
        import time
        start = time.time()

        if index_uid not in self.indexes:
            raise ValueError(f"Index {index_uid} not found")

        index = self.indexes[index_uid]
        facets = facets or []
        sort = sort or []
        filters = filters or {}

        with sqlite3.connect(self.db_path) as conn:
            # Get all documents
            rows = conn.execute(
                "SELECT doc_id, document FROM index_documents WHERE index_uid = ?",
                (index_uid,)
            ).fetchall()

        documents = {r[0]: json.loads(r[1]) for r in rows}

        # Parse query into terms
        terms = self._tokenize(query)

        # Score documents with BM25
        scores = {}
        for doc_id, doc in documents.items():
            score = self._bm25_score(index_uid, terms, doc_id, doc)
            if score > 0:
                scores[doc_id] = score

        # Apply filters
        if filters:
            scores = self._apply_filters(scores, documents, filters)

        # Sort results
        sorted_docs = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        # Apply pagination
        total = len(sorted_docs)
        hits_ids = [doc_id for doc_id, _ in sorted_docs[offset:offset + limit]]
        hits = [documents[doc_id] for doc_id in hits_ids]

        # Compute facets
        facet_dist = {}
        if facets:
            facet_dist = self._compute_facets(documents, facets)

        processing_time_ms = (time.time() - start) * 1000

        return SearchResult(
            index_uid=index_uid,
            query=query,
            hits=hits,
            total=total,
            processing_time_ms=processing_time_ms,
            facet_distribution=facet_dist
        )

    def multi_search(self, queries: List[Dict]) -> List[SearchResult]:
        """Federated search across multiple indices"""
        results = []
        for q in queries:
            result = self.search(
                q.get("index_uid"),
                q.get("query", ""),
                q.get("filters"),
                q.get("facets"),
                q.get("sort"),
                q.get("limit", 20),
                q.get("offset", 0)
            )
            results.append(result)
        return results

    def _bm25_score(self, index_uid: str, terms: List[str], doc_id: str, doc: Dict) -> float:
        """Calculate BM25 score for document"""
        score = 0.0

        with sqlite3.connect(self.db_path) as conn:
            # Get document frequency (total docs with term)
            for term in terms:
                df_row = conn.execute(
                    "SELECT COUNT(DISTINCT doc_id) FROM term_index WHERE index_uid = ? AND term = ?",
                    (index_uid, term)
                ).fetchone()
                df = df_row[0] if df_row else 0

                # IDF = log(N / df)
                n_docs = self.indexes[index_uid].total_documents or 1
                idf = math.log(n_docs / max(1, df))

                # TF per field with field weighting
                field_weights = {"title": 3.0, "description": 2.0, "body": 1.0}
                for field, value in doc.items():
                    if field == self.indexes[index_uid].primary_key:
                        continue

                    terms_in_field = self._tokenize(str(value))
                    tf = terms_in_field.count(term)

                    if tf > 0:
                        # BM25 formula
                        field_len = len(terms_in_field)
                        weight = field_weights.get(field, 1.0)
                        bm25 = (self.k1 + 1) * tf / (tf + self.k1 * (1 - self.b + self.b * field_len))
                        score += weight * idf * bm25

        return score

    def _apply_filters(self, scores: Dict[str, float], documents: Dict[str, Dict],
                      filters: Dict[str, Any]) -> Dict[str, float]:
        """Apply filters to scored documents"""
        filtered = {}
        for doc_id, score in scores.items():
            doc = documents[doc_id]
            if self._matches_filters(doc, filters):
                filtered[doc_id] = score
        return filtered

    def _matches_filters(self, doc: Dict, filters: Dict) -> bool:
        """Check if document matches all filters"""
        for field, value in filters.items():
            if field not in doc:
                return False
            if isinstance(value, list):
                if doc[field] not in value:
                    return False
            elif doc[field] != value:
                return False
        return True

    def _compute_facets(self, documents: Dict[str, Dict], facets: List[str]) -> Dict[str, Dict[str, int]]:
        """Compute facet distribution"""
        result = {}
        for facet in facets:
            facet_values = defaultdict(int)
            for doc in documents.values():
                if facet in doc:
                    facet_values[str(doc[facet])] += 1
            result[facet] = dict(facet_values)
        return result

    # ========================================================================
    # Field Configuration
    # ========================================================================

    def set_searchable_attrs(self, index_uid: str, attrs: List[str]):
        """Set which fields are searched"""
        if index_uid not in self.indexes:
            raise ValueError(f"Index {index_uid} not found")

        self.indexes[index_uid].searchable_attrs = attrs

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE indexes SET searchable_attrs = ? WHERE uid = ?",
                (json.dumps(attrs), index_uid)
            )
            conn.commit()

    def set_filterable_attrs(self, index_uid: str, attrs: List[str]):
        """Enable filtering on fields"""
        if index_uid not in self.indexes:
            raise ValueError(f"Index {index_uid} not found")

        self.indexes[index_uid].filterable_attrs = attrs

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE indexes SET filterable_attrs = ? WHERE uid = ?",
                (json.dumps(attrs), index_uid)
            )
            conn.commit()

    def set_sortable_attrs(self, index_uid: str, attrs: List[str]):
        """Enable sorting on fields"""
        if index_uid not in self.indexes:
            raise ValueError(f"Index {index_uid} not found")

        self.indexes[index_uid].sortable_attrs = attrs

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE indexes SET sortable_attrs = ? WHERE uid = ?",
                (json.dumps(attrs), index_uid)
            )
            conn.commit()

    # ========================================================================
    # Statistics
    # ========================================================================

    def get_stats(self, index_uid: Optional[str] = None) -> Dict[str, Any]:
        """Get search engine stats"""
        if index_uid:
            if index_uid not in self.indexes:
                raise ValueError(f"Index {index_uid} not found")

            index = self.indexes[index_uid]
            with sqlite3.connect(self.db_path) as conn:
                size_row = conn.execute(
                    "SELECT SUM(LENGTH(document)) FROM index_documents WHERE index_uid = ?",
                    (index_uid,)
                ).fetchone()

            size_bytes = size_row[0] if size_row and size_row[0] else 0

            return {
                "uid": index_uid,
                "documents": index.total_documents,
                "index_size_bytes": size_bytes
            }
        else:
            total_docs = sum(i.total_documents for i in self.indexes.values())
            return {
                "indexes": len(self.indexes),
                "total_documents": total_docs
            }

    # ========================================================================
    # Utility
    # ========================================================================

    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text into terms"""
        # Simple tokenization: lowercase, split on non-alphanumeric
        text = text.lower()
        tokens = re.findall(r'\w+', text)
        # Filter out common stopwords
        stopwords = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for"}
        return [t for t in tokens if t not in stopwords and len(t) > 2]


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="BlackRoad Search Engine CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command")

    # Create index
    create_parser = subparsers.add_parser("create", help="Create index")
    create_parser.add_argument("uid", help="Index UID")
    create_parser.add_argument("--primary-key", default="id", help="Primary key field")

    # Add documents
    add_parser = subparsers.add_parser("add", help="Add documents")
    add_parser.add_argument("index_uid", help="Index UID")
    add_parser.add_argument("--json-file", help="JSON file with documents")

    # Search
    search_parser = subparsers.add_parser("search", help="Search")
    search_parser.add_argument("index_uid", help="Index UID")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--limit", type=int, default=20, help="Result limit")

    # Stats
    stats_parser = subparsers.add_parser("stats", help="Get stats")
    stats_parser.add_argument("--index", help="Specific index")

    args = parser.parse_args()

    engine = SearchEngine()

    if args.command == "create":
        index = engine.create_index(args.uid, args.primary_key)
        print(f"Created index: {index.uid}")

    elif args.command == "add":
        if args.json_file:
            with open(args.json_file) as f:
                docs = json.load(f)
        else:
            docs = [{"id": "1", "title": "Sample doc"}]

        engine.add_documents(args.index_uid, docs)
        print(f"Added {len(docs)} documents")

    elif args.command == "search":
        result = engine.search(args.index_uid, args.query, limit=args.limit)
        print(f"Results: {result.total} hits")
        for hit in result.hits:
            print(f"  {hit}")

    elif args.command == "stats":
        stats = engine.get_stats(args.index)
        print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
