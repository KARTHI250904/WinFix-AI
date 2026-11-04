"""SQLite Repository for troubleshooting knowledge base in WinFix AI (Phase 19).

Provides transactional CRUD operations, schema initialization, and referential integrity
for Knowledge Articles and associated diagnostics, symptoms, causes, and verification steps.
Enforces parameterized queries and strict safety rules: LLM != Windows Shell.
"""

from datetime import datetime
import logging
from typing import Any, Dict, List, Optional, Set
import uuid

# ToolRegistry type hint without immediate circular module evaluation
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from agent.tool_registry import ToolRegistry

from database.db import DatabaseManager, db_manager
from database.knowledge_models import (
    KnowledgeArticle,
    KnowledgeCategory,
    KnowledgeCause,
    KnowledgeDiagnosticStep,
    KnowledgeSearchResult,
    KnowledgeSeverity,
    KnowledgeSymptom,
    KnowledgeToolLink,
    KnowledgeToolRole,
    KnowledgeValidationError,
    KnowledgeVerificationStep,
    validate_knowledge_article,
)

logger = logging.getLogger(__name__)


class KnowledgeRepository:
    """Handles CRUD operations and transactional persistence for troubleshooting knowledge."""

    def __init__(
        self,
        db: Optional[DatabaseManager] = None,
        tool_registry: Optional[Any] = None,
    ) -> None:
        self.db = db or db_manager
        if tool_registry is not None:
            self.tool_registry = tool_registry
        else:
            from agent.tool_registry import default_tool_registry
            self.tool_registry = default_tool_registry
        self._fts5_available: Optional[bool] = None
        self.init_knowledge_schema()

    @property
    def valid_tool_ids(self) -> Set[str]:
        """Set of registered tool IDs from the authoritative ToolRegistry."""
        return set(self.tool_registry.list_tool_names())

    def init_knowledge_schema(self) -> None:
        """Initialize knowledge tables and optional FTS5 virtual table if not already present."""
        try:
            with self.db.get_connection() as conn:
                # 1. Base tables
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS knowledge_articles (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        category TEXT NOT NULL,
                        summary TEXT NOT NULL,
                        severity TEXT NOT NULL DEFAULT 'MEDIUM',
                        confidence REAL NOT NULL DEFAULT 1.0,
                        platform TEXT NOT NULL DEFAULT 'Windows 10/11',
                        source TEXT NOT NULL DEFAULT 'Built-in',
                        version INTEGER NOT NULL DEFAULT 1,
                        enabled INTEGER NOT NULL DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS knowledge_symptoms (
                        id TEXT PRIMARY KEY,
                        article_id TEXT NOT NULL,
                        symptom_text TEXT NOT NULL,
                        weight REAL DEFAULT 1.0,
                        FOREIGN KEY (article_id) REFERENCES knowledge_articles(id) ON DELETE CASCADE
                    );
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS knowledge_causes (
                        id TEXT PRIMARY KEY,
                        article_id TEXT NOT NULL,
                        cause_text TEXT NOT NULL,
                        likelihood TEXT DEFAULT 'POSSIBLE',
                        FOREIGN KEY (article_id) REFERENCES knowledge_articles(id) ON DELETE CASCADE
                    );
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS knowledge_diagnostic_steps (
                        id TEXT PRIMARY KEY,
                        article_id TEXT NOT NULL,
                        step_order INTEGER NOT NULL,
                        step_text TEXT NOT NULL,
                        FOREIGN KEY (article_id) REFERENCES knowledge_articles(id) ON DELETE CASCADE
                    );
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS knowledge_tool_links (
                        id TEXT PRIMARY KEY,
                        article_id TEXT NOT NULL,
                        tool_id TEXT NOT NULL,
                        tool_role TEXT NOT NULL DEFAULT 'DIAGNOSTIC',
                        FOREIGN KEY (article_id) REFERENCES knowledge_articles(id) ON DELETE CASCADE
                    );
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS knowledge_verification_steps (
                        id TEXT PRIMARY KEY,
                        article_id TEXT NOT NULL,
                        step_order INTEGER NOT NULL,
                        step_text TEXT NOT NULL,
                        FOREIGN KEY (article_id) REFERENCES knowledge_articles(id) ON DELETE CASCADE
                    );
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS knowledge_metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)

                # 2. Try FTS5 table initialization
                try:
                    conn.execute("""
                        CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_articles_fts USING fts5(
                            article_id UNINDEXED,
                            title,
                            category,
                            summary,
                            symptoms_text,
                            causes_text,
                            steps_text
                        );
                    """)
                    self._fts5_available = True
                except Exception as fts_err:
                    logger.debug("FTS5 table initialization skipped/unavailable: %s", fts_err)
                    self._fts5_available = False

            logger.debug("Knowledge schema initialized successfully (FTS5=%s).", self._fts5_available)
        except Exception as exc:
            logger.error("Failed to initialize knowledge schema: %s", exc)
            raise

    def is_fts5_available(self) -> bool:
        """Check whether SQLite FTS5 full-text indexing is available."""
        if self._fts5_available is None:
            try:
                with self.db.get_connection() as conn:
                    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='knowledge_articles_fts';")
                    self._fts5_available = cursor.fetchone() is not None
            except Exception:
                self._fts5_available = False
        return bool(self._fts5_available)

    def create_article(
        self,
        article: KnowledgeArticle,
        validate: bool = True,
    ) -> KnowledgeArticle:
        """Validate and insert a knowledge article along with all related details atomically."""
        if validate:
            validate_knowledge_article(article, self.valid_tool_ids)

        now_str = datetime.now().isoformat()
        article.created_at = article.created_at or now_str
        article.updated_at = now_str

        category_str = article.category.value if isinstance(article.category, KnowledgeCategory) else str(article.category)
        severity_str = article.severity.value if isinstance(article.severity, KnowledgeSeverity) else str(article.severity)

        with self.db.get_connection() as conn:
            # Insert main article
            conn.execute(
                """
                INSERT INTO knowledge_articles (
                    id, title, category, summary, severity, confidence, platform, source, version, enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    article.id,
                    article.title,
                    category_str,
                    article.summary,
                    severity_str,
                    article.confidence,
                    article.platform,
                    article.source,
                    article.version,
                    1 if article.enabled else 0,
                    article.created_at,
                    article.updated_at,
                ),
            )

            # Insert symptoms
            for idx, sym in enumerate(article.symptoms):
                sym_id = f"sym_{article.id}_{idx}_{uuid.uuid4().hex[:6]}"
                conn.execute(
                    "INSERT INTO knowledge_symptoms (id, article_id, symptom_text, weight) VALUES (?, ?, ?, ?);",
                    (sym_id, article.id, sym, 1.0),
                )

            # Insert causes
            for idx, cause in enumerate(article.possible_causes):
                cause_id = f"cause_{article.id}_{idx}_{uuid.uuid4().hex[:6]}"
                conn.execute(
                    "INSERT INTO knowledge_causes (id, article_id, cause_text, likelihood) VALUES (?, ?, ?, ?);",
                    (cause_id, article.id, cause, "POSSIBLE"),
                )

            # Insert diagnostic steps
            for idx, step in enumerate(article.diagnostic_steps):
                step_id = f"step_{article.id}_{idx}_{uuid.uuid4().hex[:6]}"
                conn.execute(
                    "INSERT INTO knowledge_diagnostic_steps (id, article_id, step_order, step_text) VALUES (?, ?, ?, ?);",
                    (step_id, article.id, idx + 1, step),
                )

            # Insert tool links (diagnostic)
            for tool_id in article.related_tools:
                link_id = f"link_diag_{article.id}_{tool_id}_{uuid.uuid4().hex[:6]}"
                conn.execute(
                    "INSERT INTO knowledge_tool_links (id, article_id, tool_id, tool_role) VALUES (?, ?, ?, ?);",
                    (link_id, article.id, tool_id, KnowledgeToolRole.DIAGNOSTIC.value),
                )

            # Insert tool links (repair references)
            for tool_id in article.repair_references:
                link_id = f"link_rep_{article.id}_{tool_id}_{uuid.uuid4().hex[:6]}"
                conn.execute(
                    "INSERT INTO knowledge_tool_links (id, article_id, tool_id, tool_role) VALUES (?, ?, ?, ?);",
                    (link_id, article.id, tool_id, KnowledgeToolRole.REPAIR.value),
                )

            # Insert verification steps
            for idx, vstep in enumerate(article.verification_steps):
                vstep_id = f"vstep_{article.id}_{idx}_{uuid.uuid4().hex[:6]}"
                conn.execute(
                    "INSERT INTO knowledge_verification_steps (id, article_id, step_order, step_text) VALUES (?, ?, ?, ?);",
                    (vstep_id, article.id, idx + 1, vstep),
                )

            # Update FTS5 index if available
            self._sync_fts5_article(conn, article)

        logger.debug("Successfully created knowledge article '%s' (%s)", article.id, article.title)
        return article

    def get_article(self, article_id: str, conn: Optional[Any] = None) -> Optional[KnowledgeArticle]:
        """Retrieve a fully reconstructed KnowledgeArticle by its unique ID."""
        if conn is not None:
            return self._fetch_single_article(conn, article_id)

        with self.db.get_connection() as c:
            return self._fetch_single_article(c, article_id)

    def _fetch_single_article(self, conn: Any, article_id: str) -> Optional[KnowledgeArticle]:
        """Internal helper to reconstruct KnowledgeArticle from an open connection."""
        cursor = conn.execute("SELECT * FROM knowledge_articles WHERE id = ?;", (article_id,))
        row = cursor.fetchone()
        if not row:
            return None

        # Retrieve symptoms
        s_cursor = conn.execute(
            "SELECT symptom_text FROM knowledge_symptoms WHERE article_id = ? ORDER BY id ASC;",
            (article_id,),
        )
        symptoms = [r["symptom_text"] for r in s_cursor.fetchall()]

        # Retrieve causes
        c_cursor = conn.execute(
            "SELECT cause_text FROM knowledge_causes WHERE article_id = ? ORDER BY id ASC;",
            (article_id,),
        )
        causes = [r["cause_text"] for r in c_cursor.fetchall()]

        # Retrieve diagnostic steps
        d_cursor = conn.execute(
            "SELECT step_text FROM knowledge_diagnostic_steps WHERE article_id = ? ORDER BY step_order ASC;",
            (article_id,),
        )
        diag_steps = [r["step_text"] for r in d_cursor.fetchall()]

        # Retrieve tool links
        t_cursor = conn.execute(
            "SELECT tool_id, tool_role FROM knowledge_tool_links WHERE article_id = ?;",
            (article_id,),
        )
        related_tools = []
        repair_references = []
        for tr in t_cursor.fetchall():
            if tr["tool_role"] == KnowledgeToolRole.REPAIR.value:
                repair_references.append(tr["tool_id"])
            else:
                related_tools.append(tr["tool_id"])

        # Retrieve verification steps
        v_cursor = conn.execute(
            "SELECT step_text FROM knowledge_verification_steps WHERE article_id = ? ORDER BY step_order ASC;",
            (article_id,),
        )
        verification_steps = [r["step_text"] for r in v_cursor.fetchall()]

        cat_enum = KnowledgeCategory(row["category"]) if row["category"] in [c.value for c in KnowledgeCategory] else KnowledgeCategory.GENERAL
        sev_enum = KnowledgeSeverity(row["severity"]) if row["severity"] in [s.value for s in KnowledgeSeverity] else KnowledgeSeverity.MEDIUM

        return KnowledgeArticle(
            id=row["id"],
            title=row["title"],
            category=cat_enum,
            summary=row["summary"],
            symptoms=symptoms,
            possible_causes=causes,
            diagnostic_steps=diag_steps,
            related_tools=related_tools,
            repair_references=repair_references,
            verification_steps=verification_steps,
            severity=sev_enum,
            confidence=float(row["confidence"]),
            platform=row["platform"],
            source=row["source"],
            version=int(row["version"]),
            enabled=bool(row["enabled"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def list_articles(
        self,
        category: Optional[str] = None,
        enabled_only: bool = True,
    ) -> List[KnowledgeArticle]:
        """List knowledge articles, optionally filtered by category and enabled status.
        
        Optimized with batched relational fetches inside a single connection.
        """
        query = "SELECT * FROM knowledge_articles WHERE 1=1"
        params: List[Any] = []

        if enabled_only:
            query += " AND enabled = 1"
        if category:
            cat_val = category.value if isinstance(category, KnowledgeCategory) else str(category).upper()
            query += " AND category = ?"
            params.append(cat_val)

        query += " ORDER BY title ASC;"

        with self.db.get_connection() as conn:
            cursor = conn.execute(query, tuple(params))
            article_rows = cursor.fetchall()
            if not article_rows:
                return []

            article_ids = [r["id"] for r in article_rows]
            placeholders = ",".join("?" for _ in article_ids)

            # Batch retrieve symptoms
            symptoms_by_art: Dict[str, List[str]] = {aid: [] for aid in article_ids}
            s_cursor = conn.execute(
                f"SELECT article_id, symptom_text FROM knowledge_symptoms WHERE article_id IN ({placeholders}) ORDER BY id ASC;",
                tuple(article_ids),
            )
            for sr in s_cursor.fetchall():
                symptoms_by_art[sr["article_id"]].append(sr["symptom_text"])

            # Batch retrieve causes
            causes_by_art: Dict[str, List[str]] = {aid: [] for aid in article_ids}
            c_cursor = conn.execute(
                f"SELECT article_id, cause_text FROM knowledge_causes WHERE article_id IN ({placeholders}) ORDER BY id ASC;",
                tuple(article_ids),
            )
            for cr in c_cursor.fetchall():
                causes_by_art[cr["article_id"]].append(cr["cause_text"])

            # Batch retrieve diagnostic steps
            steps_by_art: Dict[str, List[str]] = {aid: [] for aid in article_ids}
            d_cursor = conn.execute(
                f"SELECT article_id, step_text FROM knowledge_diagnostic_steps WHERE article_id IN ({placeholders}) ORDER BY step_order ASC;",
                tuple(article_ids),
            )
            for dr in d_cursor.fetchall():
                steps_by_art[dr["article_id"]].append(dr["step_text"])

            # Batch retrieve tool links
            tools_by_art: Dict[str, List[str]] = {aid: [] for aid in article_ids}
            repairs_by_art: Dict[str, List[str]] = {aid: [] for aid in article_ids}
            t_cursor = conn.execute(
                f"SELECT article_id, tool_id, tool_role FROM knowledge_tool_links WHERE article_id IN ({placeholders});",
                tuple(article_ids),
            )
            for tr in t_cursor.fetchall():
                aid = tr["article_id"]
                if tr["tool_role"] == KnowledgeToolRole.REPAIR.value:
                    repairs_by_art[aid].append(tr["tool_id"])
                else:
                    tools_by_art[aid].append(tr["tool_id"])

            # Batch retrieve verification steps
            verifs_by_art: Dict[str, List[str]] = {aid: [] for aid in article_ids}
            v_cursor = conn.execute(
                f"SELECT article_id, step_text FROM knowledge_verification_steps WHERE article_id IN ({placeholders}) ORDER BY step_order ASC;",
                tuple(article_ids),
            )
            for vr in v_cursor.fetchall():
                verifs_by_art[vr["article_id"]].append(vr["step_text"])

            articles: List[KnowledgeArticle] = []
            for row in article_rows:
                aid = row["id"]
                cat_enum = KnowledgeCategory(row["category"]) if row["category"] in [c.value for c in KnowledgeCategory] else KnowledgeCategory.GENERAL
                sev_enum = KnowledgeSeverity(row["severity"]) if row["severity"] in [s.value for s in KnowledgeSeverity] else KnowledgeSeverity.MEDIUM

                articles.append(
                    KnowledgeArticle(
                        id=aid,
                        title=row["title"],
                        category=cat_enum,
                        summary=row["summary"],
                        symptoms=symptoms_by_art.get(aid, []),
                        possible_causes=causes_by_art.get(aid, []),
                        diagnostic_steps=steps_by_art.get(aid, []),
                        related_tools=tools_by_art.get(aid, []),
                        repair_references=repairs_by_art.get(aid, []),
                        verification_steps=verifs_by_art.get(aid, []),
                        severity=sev_enum,
                        confidence=float(row["confidence"]),
                        platform=row["platform"],
                        source=row["source"],
                        version=int(row["version"]),
                        enabled=bool(row["enabled"]),
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                    )
                )

            return articles

    def update_article(
        self,
        article: KnowledgeArticle,
        validate: bool = True,
    ) -> KnowledgeArticle:
        """Update an existing knowledge article and its related sub-tables atomically."""
        if validate:
            validate_knowledge_article(article, self.valid_tool_ids)

        now_str = datetime.now().isoformat()
        article.updated_at = now_str
        category_str = article.category.value if isinstance(article.category, KnowledgeCategory) else str(article.category)
        severity_str = article.severity.value if isinstance(article.severity, KnowledgeSeverity) else str(article.severity)

        with self.db.get_connection() as conn:
            # Check existence
            cursor = conn.execute("SELECT id FROM knowledge_articles WHERE id = ?;", (article.id,))
            if not cursor.fetchone():
                raise KnowledgeValidationError(f"Cannot update non-existent article '{article.id}'.")

            conn.execute(
                """
                UPDATE knowledge_articles SET
                    title = ?,
                    category = ?,
                    summary = ?,
                    severity = ?,
                    confidence = ?,
                    platform = ?,
                    source = ?,
                    version = ?,
                    enabled = ?,
                    updated_at = ?
                WHERE id = ?;
                """,
                (
                    article.title,
                    category_str,
                    article.summary,
                    severity_str,
                    article.confidence,
                    article.platform,
                    article.source,
                    article.version,
                    1 if article.enabled else 0,
                    article.updated_at,
                    article.id,
                ),
            )

            # Clear sub-records and re-insert (CASCADE delete on foreign keys cleans automatically if needed)
            conn.execute("DELETE FROM knowledge_symptoms WHERE article_id = ?;", (article.id,))
            conn.execute("DELETE FROM knowledge_causes WHERE article_id = ?;", (article.id,))
            conn.execute("DELETE FROM knowledge_diagnostic_steps WHERE article_id = ?;", (article.id,))
            conn.execute("DELETE FROM knowledge_tool_links WHERE article_id = ?;", (article.id,))
            conn.execute("DELETE FROM knowledge_verification_steps WHERE article_id = ?;", (article.id,))

            for idx, sym in enumerate(article.symptoms):
                sym_id = f"sym_{article.id}_{idx}_{uuid.uuid4().hex[:6]}"
                conn.execute(
                    "INSERT INTO knowledge_symptoms (id, article_id, symptom_text, weight) VALUES (?, ?, ?, ?);",
                    (sym_id, article.id, sym, 1.0),
                )

            for idx, cause in enumerate(article.possible_causes):
                cause_id = f"cause_{article.id}_{idx}_{uuid.uuid4().hex[:6]}"
                conn.execute(
                    "INSERT INTO knowledge_causes (id, article_id, cause_text, likelihood) VALUES (?, ?, ?, ?);",
                    (cause_id, article.id, cause, "POSSIBLE"),
                )

            for idx, step in enumerate(article.diagnostic_steps):
                step_id = f"step_{article.id}_{idx}_{uuid.uuid4().hex[:6]}"
                conn.execute(
                    "INSERT INTO knowledge_diagnostic_steps (id, article_id, step_order, step_text) VALUES (?, ?, ?, ?);",
                    (step_id, article.id, idx + 1, step),
                )

            for tool_id in article.related_tools:
                link_id = f"link_diag_{article.id}_{tool_id}_{uuid.uuid4().hex[:6]}"
                conn.execute(
                    "INSERT INTO knowledge_tool_links (id, article_id, tool_id, tool_role) VALUES (?, ?, ?, ?);",
                    (link_id, article.id, tool_id, KnowledgeToolRole.DIAGNOSTIC.value),
                )

            for tool_id in article.repair_references:
                link_id = f"link_rep_{article.id}_{tool_id}_{uuid.uuid4().hex[:6]}"
                conn.execute(
                    "INSERT INTO knowledge_tool_links (id, article_id, tool_id, tool_role) VALUES (?, ?, ?, ?);",
                    (link_id, article.id, tool_id, KnowledgeToolRole.REPAIR.value),
                )

            for idx, vstep in enumerate(article.verification_steps):
                vstep_id = f"vstep_{article.id}_{idx}_{uuid.uuid4().hex[:6]}"
                conn.execute(
                    "INSERT INTO knowledge_verification_steps (id, article_id, step_order, step_text) VALUES (?, ?, ?, ?);",
                    (vstep_id, article.id, idx + 1, vstep),
                )

            self._sync_fts5_article(conn, article)

        logger.debug("Updated knowledge article '%s'", article.id)
        return article

    def disable_article(self, article_id: str) -> bool:
        """Disable a knowledge article without deleting it."""
        with self.db.get_connection() as conn:
            cursor = conn.execute("UPDATE knowledge_articles SET enabled = 0, updated_at = ? WHERE id = ?;", (datetime.now().isoformat(), article_id))
            return cursor.rowcount > 0

    def enable_article(self, article_id: str) -> bool:
        """Enable a knowledge article."""
        with self.db.get_connection() as conn:
            cursor = conn.execute("UPDATE knowledge_articles SET enabled = 1, updated_at = ? WHERE id = ?;", (datetime.now().isoformat(), article_id))
            return cursor.rowcount > 0

    def delete_article(self, article_id: str) -> bool:
        """Delete a knowledge article and its associated cascade records."""
        with self.db.get_connection() as conn:
            cursor = conn.execute("DELETE FROM knowledge_articles WHERE id = ?;", (article_id,))
            if self.is_fts5_available():
                try:
                    conn.execute("DELETE FROM knowledge_articles_fts WHERE article_id = ?;", (article_id,))
                except Exception:
                    pass
            return cursor.rowcount > 0

    def count_articles(self, category: Optional[str] = None, enabled_only: bool = False) -> int:
        """Return total count of knowledge articles in the database."""
        query = "SELECT COUNT(*) AS cnt FROM knowledge_articles WHERE 1=1"
        params: List[Any] = []
        if enabled_only:
            query += " AND enabled = 1"
        if category:
            cat_val = category.value if isinstance(category, KnowledgeCategory) else str(category).upper()
            query += " AND category = ?"
            params.append(cat_val)

        with self.db.get_connection() as conn:
            cursor = conn.execute(query, tuple(params))
            row = cursor.fetchone()
            return int(row["cnt"]) if row else 0

    def get_metadata(self, key: str) -> Optional[str]:
        """Fetch metadata value for a given key."""
        with self.db.get_connection() as conn:
            cursor = conn.execute("SELECT value FROM knowledge_metadata WHERE key = ?;", (key,))
            row = cursor.fetchone()
            return row["value"] if row else None

    def set_metadata(self, key: str, value: str) -> None:
        """Set metadata value for a given key."""
        with self.db.get_connection() as conn:
            conn.execute(
                "INSERT INTO knowledge_metadata (key, value, updated_at) VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at;",
                (key, value, datetime.now().isoformat()),
            )

    def _sync_fts5_article(self, conn: Any, article: KnowledgeArticle) -> None:
        """Helper to keep FTS5 table synchronized if available."""
        if not self.is_fts5_available():
            return
        try:
            conn.execute("DELETE FROM knowledge_articles_fts WHERE article_id = ?;", (article.id,))
            if article.enabled:
                symptoms_text = " ".join(article.symptoms)
                causes_text = " ".join(article.possible_causes)
                steps_text = " ".join(article.diagnostic_steps + article.verification_steps)
                cat_str = article.category.value if isinstance(article.category, KnowledgeCategory) else str(article.category)

                conn.execute(
                    """
                    INSERT INTO knowledge_articles_fts (
                        article_id, title, category, summary, symptoms_text, causes_text, steps_text
                    ) VALUES (?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        article.id,
                        article.title,
                        cat_str,
                        article.summary,
                        symptoms_text,
                        causes_text,
                        steps_text,
                    ),
                )
        except Exception as fts_err:
            logger.debug("Failed to sync FTS5 index for '%s': %s", article.id, fts_err)
