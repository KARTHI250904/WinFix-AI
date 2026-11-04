"""Database module for WinFix AI (SQLite connection, schema, repositories, knowledge)."""

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
from database.knowledge_repository import KnowledgeRepository
from database.knowledge_search import KnowledgeSearchEngine

__all__ = [
    "DatabaseManager",
    "db_manager",
    "KnowledgeArticle",
    "KnowledgeCategory",
    "KnowledgeSeverity",
    "KnowledgeSymptom",
    "KnowledgeCause",
    "KnowledgeDiagnosticStep",
    "KnowledgeToolLink",
    "KnowledgeToolRole",
    "KnowledgeVerificationStep",
    "KnowledgeSearchResult",
    "KnowledgeValidationError",
    "validate_knowledge_article",
    "KnowledgeRepository",
    "KnowledgeSearchEngine",
]
