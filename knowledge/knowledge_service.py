"""High-level Knowledge Service for WinFix AI (Phase 19).

Coordinates structured troubleshooting knowledge search, diagnostic guidance retrieval,
auditing, and graceful fallback handling across all agent modes.
Strictly adheres to: LLM != Windows Shell and Knowledge != Windows Command.
"""

from datetime import datetime
import logging
from typing import Any, Dict, List, Optional, Set

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from agent.tool_registry import ToolRegistry

from database.db import DatabaseManager, db_manager
from database.knowledge_models import (
    KnowledgeArticle,
    KnowledgeCategory,
    KnowledgeSearchResult,
)
from database.knowledge_repository import KnowledgeRepository
from database.knowledge_search import KnowledgeSearchEngine
from knowledge.seed_data import seed_default_knowledge

logger = logging.getLogger(__name__)


class KnowledgeService:
    """Provides high-level knowledge queries, diagnostic guidance lookup, and audit trail."""

    def __init__(
        self,
        repository: Optional[KnowledgeRepository] = None,
        search_engine: Optional[KnowledgeSearchEngine] = None,
        tool_registry: Optional[Any] = None,
        db: Optional[DatabaseManager] = None,
        auto_seed: bool = True,
    ) -> None:
        self.db = db or db_manager
        if tool_registry is not None:
            self.tool_registry = tool_registry
        else:
            from agent.tool_registry import default_tool_registry
            self.tool_registry = default_tool_registry
        self.repository = repository or KnowledgeRepository(db=self.db, tool_registry=self.tool_registry)
        self.search_engine = search_engine or KnowledgeSearchEngine(self.repository)

        if auto_seed:
            try:
                seed_default_knowledge(self.repository, force=False)
            except Exception as seed_err:
                logger.warning("Knowledge automatic seeding failed: %s", seed_err)

    def search(
        self,
        query: str,
        category: Optional[str] = None,
        limit: int = 10,
        session_id: Optional[str] = None,
    ) -> List[KnowledgeSearchResult]:
        """Search knowledge articles by symptom, cause, tool, or keyword query.

        Fails gracefully without throwing exceptions.
        """
        from modes.tutor_context import sanitize_tutor_text
        sanitized_query = sanitize_tutor_text(query) if query else ""
        self._record_knowledge_audit(
            session_id=session_id,
            event_type="KNOWLEDGE_SEARCH_STARTED",
            details={"query_len": len(sanitized_query), "category": category, "limit": limit},
        )

        try:
            results = self.search_engine.search(
                query=sanitized_query,
                category=category,
                limit=limit,
                enabled_only=True,
                load_full_article=True,
            )
            self._record_knowledge_audit(
                session_id=session_id,
                event_type="KNOWLEDGE_SEARCH_COMPLETED",
                details={"result_count": len(results), "top_matches": [r.article_id for r in results[:3]]},
            )
            return results
        except Exception as exc:
            logger.error("Knowledge search failed: %s", exc)
            self._record_knowledge_audit(
                session_id=session_id,
                event_type="KNOWLEDGE_SEARCH_FAILED",
                details={"error": str(exc)},
            )
            return []

    def get_article(self, article_id: str) -> Optional[KnowledgeArticle]:
        """Retrieve a specific knowledge article by ID."""
        try:
            return self.repository.get_article(article_id)
        except Exception as exc:
            logger.error("Failed to get knowledge article '%s': %s", article_id, exc)
            return None

    def list_articles(self, category: Optional[str] = None) -> List[KnowledgeArticle]:
        """List all active knowledge articles, optionally filtered by category."""
        try:
            return self.repository.list_articles(category=category, enabled_only=True)
        except Exception as exc:
            logger.error("Failed to list knowledge articles: %s", exc)
            return []

    def get_guidance_for_diagnostic(
        self,
        tool_name: str,
        diagnostic_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[KnowledgeArticle]:
        """Find the most relevant knowledge article for a given diagnostic tool inspection."""
        if not tool_name:
            return None

        # 1. Direct tool-reference match
        articles = self.list_articles()
        for art in articles:
            if tool_name in art.related_tools or tool_name in art.repair_references:
                return art

        # 2. Tool domain fallback lookup
        tool_def = self.tool_registry.get(tool_name)
        if tool_def and tool_def.domain:
            domain_map = {
                "network": KnowledgeCategory.NETWORK,
                "storage": KnowledgeCategory.STORAGE,
                "performance": KnowledgeCategory.PERFORMANCE,
                "services": KnowledgeCategory.SERVICES,
                "bluetooth": KnowledgeCategory.BLUETOOTH,
                "windows_update": KnowledgeCategory.WINDOWS_UPDATE,
                "defender": KnowledgeCategory.DEFENDER,
                "applications": KnowledgeCategory.APPLICATION_CRASH,
                "system": KnowledgeCategory.GENERAL,
            }
            target_cat = domain_map.get(tool_def.domain)
            if target_cat:
                cat_articles = self.repository.list_articles(category=target_cat.value, enabled_only=True)
                if cat_articles:
                    return cat_articles[0]

        return None

    def get_guidance_for_category(self, category: str) -> List[KnowledgeArticle]:
        """Fetch all knowledge articles belonging to a specific diagnostic category."""
        return self.list_articles(category=category)

    def get_stats(self) -> Dict[str, Any]:
        """Return knowledge base statistics and operational status."""
        try:
            total_articles = self.repository.count_articles(enabled_only=False)
            enabled_articles = self.repository.count_articles(enabled_only=True)
            version_str = self.repository.get_metadata("knowledge_version") or "1"
            fts5_active = self.repository.is_fts5_available()

            categories_represented = len(
                {art.category for art in self.repository.list_articles(enabled_only=False)}
            )

            return {
                "total_articles": total_articles,
                "enabled_articles": enabled_articles,
                "categories_count": categories_represented,
                "version": int(version_str),
                "fts5_enabled": fts5_active,
                "status": "HEALTHY",
            }
        except Exception as exc:
            logger.error("Failed to collect knowledge base stats: %s", exc)
            return {
                "total_articles": 0,
                "enabled_articles": 0,
                "categories_count": 0,
                "version": 0,
                "fts5_enabled": False,
                "status": f"ERROR: {exc}",
            }

    def _record_knowledge_audit(
        self,
        session_id: Optional[str],
        event_type: str,
        details: Dict[str, Any],
    ) -> None:
        """Record knowledge access events in the SQLite audit log."""
        try:
            sid = session_id or "system_knowledge_event"
            now_str = datetime.now().isoformat()
            with self.db.get_connection() as conn:
                # Ensure foreign key parent session exists
                conn.execute(
                    "INSERT OR IGNORE INTO sessions (id, mode, status, created_at, updated_at) VALUES (?, 'knowledge', 'active', ?, ?);",
                    (sid, now_str, now_str),
                )
                conn.execute(
                    """
                    INSERT INTO feedback (id, session_id, resolved, rating, comments, created_at)
                    VALUES (?, ?, 0, 0, ?, ?);
                    """,
                    (
                        f"audit_{event_type.lower()}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
                        sid,
                        f"{event_type}: {details}",
                        now_str,
                    ),
                )
        except Exception:
            # Audit logging failure should not crash the knowledge service
            pass


# Lazy singleton instance for default knowledge services
_default_service: Optional[KnowledgeService] = None


def get_default_knowledge_service() -> KnowledgeService:
    """Retrieve or lazily instantiate default KnowledgeService singleton."""
    global _default_service
    if _default_service is None:
        _default_service = KnowledgeService()
    return _default_service


class _LazyDefaultKnowledgeService:
    def __getattr__(self, name: str) -> Any:
        return getattr(get_default_knowledge_service(), name)


default_knowledge_service: Any = _LazyDefaultKnowledgeService()

