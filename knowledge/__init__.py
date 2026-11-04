"""Knowledge subsystem package for WinFix AI (Phase 19).

Provides local SQLite-backed troubleshooting articles, deterministic search,
diagnostic guidance mapping, and seed data.
"""

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
from knowledge.knowledge_service import KnowledgeService, default_knowledge_service
from knowledge.seed_data import KNOWLEDGE_VERSION, get_seed_articles, seed_default_knowledge

__all__ = [
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
    "KnowledgeService",
    "default_knowledge_service",
    "seed_default_knowledge",
    "get_seed_articles",
    "KNOWLEDGE_VERSION",
]
