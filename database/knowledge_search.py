"""Deterministic local knowledge search engine for WinFix AI (Phase 19).

Provides offline, transparent, deterministic relevance scoring and candidate retrieval
without external vector databases, remote APIs, or arbitrary query execution.
Enforces strict parameterization, bounded queries, and SQL injection protection.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from database.knowledge_models import (
    MAX_QUERY_LENGTH,
    MAX_RESULTS_LIMIT,
    KnowledgeArticle,
    KnowledgeCategory,
    KnowledgeSearchResult,
)
from database.knowledge_repository import KnowledgeRepository

logger = logging.getLogger(__name__)

# Standard English stop words to filter out of keyword queries
STOP_WORDS: Set[str] = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "can't", "cannot", "could",
    "couldn't", "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down",
    "during", "each", "few", "for", "from", "further", "had", "hadn't", "has",
    "hasn't", "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her",
    "here", "here's", "hers", "herself", "him", "himself", "his", "how", "how's",
    "i", "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it",
    "it's", "its", "itself", "let's", "me", "more", "most", "mustn't", "my",
    "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or",
    "other", "ought", "our", "ours", "ourselves", "out", "over", "own", "same",
    "shan't", "she", "she'd", "she'll", "she's", "should", "shouldn't", "so",
    "some", "such", "than", "that", "that's", "the", "their", "theirs", "them",
    "themselves", "then", "there", "there's", "these", "they", "they'd", "they'll",
    "they're", "they've", "this", "those", "through", "to", "too", "under", "until",
    "up", "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were",
    "weren't", "what", "what's", "when", "when's", "where", "where's", "which",
    "while", "who", "who's", "whom", "why", "why's", "with", "won't", "would",
    "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours",
    "yourself", "yourselves", "please", "help", "windows", "issue", "problem"
}

# Deterministic Score Constants
SCORE_EXACT_TITLE = 10.0
SCORE_PARTIAL_TITLE = 6.0
SCORE_SYMPTOM_MATCH = 7.0
SCORE_CATEGORY_MATCH = 5.0
SCORE_CAUSE_MATCH = 4.0
SCORE_DIAGNOSTIC_STEP_MATCH = 3.0
SCORE_TOOL_MATCH = 2.0


def normalize_query_text(query: str) -> str:
    """Safely bound, trim, and normalize query string."""
    if not query or not isinstance(query, str):
        return ""
    bounded = query[:MAX_QUERY_LENGTH].strip().lower()
    return bounded


def extract_keywords(query: str) -> List[str]:
    """Extract clean keywords from normalized text while discarding punctuation and stop words."""
    normalized = normalize_query_text(query)
    if not normalized:
        return []

    tokens = re.findall(r"[a-z0-9_\-]+", normalized)
    keywords = [t for t in tokens if len(t) > 2 and t not in STOP_WORDS]
    return keywords


class KnowledgeSearchEngine:
    """Deterministic local search engine for troubleshooting knowledge base."""

    def __init__(self, repository: KnowledgeRepository) -> None:
        self.repository = repository

    def search(
        self,
        query: str,
        category: Optional[str] = None,
        limit: int = 10,
        enabled_only: bool = True,
        load_full_article: bool = True,
    ) -> List[KnowledgeSearchResult]:
        """Perform deterministic keyword-ranked search over knowledge articles.

        Args:
            query: User search query or symptom description.
            category: Optional category filter.
            limit: Maximum number of search results to return.
            enabled_only: Filter only enabled articles.
            load_full_article: Whether to attach the full KnowledgeArticle to results.

        Returns:
            List of KnowledgeSearchResult sorted by deterministic relevance score.
        """
        bounded_limit = max(1, min(limit, MAX_RESULTS_LIMIT))
        norm_query = normalize_query_text(query)
        keywords = extract_keywords(norm_query)

        # Retrieve candidate articles from repository
        candidate_articles = self.repository.list_articles(
            category=category,
            enabled_only=enabled_only,
        )

        if not candidate_articles:
            return []

        results: List[KnowledgeSearchResult] = []
        target_category = category.upper() if category else None

        for article in candidate_articles:
            score, matched_terms = self._score_article(
                article=article,
                norm_query=norm_query,
                keywords=keywords,
                target_category=target_category,
            )

            # Only include if score > 0 or if empty query and category match
            if score > 0 or (not norm_query and target_category):
                if not norm_query and target_category:
                    score = SCORE_CATEGORY_MATCH * article.confidence
                    matched_terms.append(f"category:{target_category}")

                results.append(
                    KnowledgeSearchResult(
                        article_id=article.id,
                        title=article.title,
                        category=article.category.value if isinstance(article.category, KnowledgeCategory) else str(article.category),
                        summary=article.summary,
                        matched_terms=sorted(list(set(matched_terms))),
                        relevance_score=round(score, 2),
                        article=article if load_full_article else None,
                    )
                )

        # Sort by relevance_score descending, then by title ascending for deterministic stability
        results.sort(key=lambda r: (-r.relevance_score, r.title))
        return results[:bounded_limit]

    def _score_article(
        self,
        article: KnowledgeArticle,
        norm_query: str,
        keywords: List[str],
        target_category: Optional[str],
    ) -> Tuple[float, List[str]]:
        """Calculate deterministic relevance score for a given article."""
        raw_score = 0.0
        matched_terms: List[str] = []

        art_title_lower = article.title.lower()
        art_cat_str = article.category.value if isinstance(article.category, KnowledgeCategory) else str(article.category)

        # 1. Exact / Partial Title Match
        if norm_query and norm_query in art_title_lower:
            raw_score += SCORE_EXACT_TITLE
            matched_terms.append(f"exact_title:{norm_query}")
        else:
            title_kw_matches = [kw for kw in keywords if kw in art_title_lower]
            if title_kw_matches:
                raw_score += SCORE_PARTIAL_TITLE * len(title_kw_matches)
                for kw in title_kw_matches:
                    matched_terms.append(f"title_kw:{kw}")

        # 2. Category Match
        if target_category and target_category == art_cat_str.upper():
            raw_score += SCORE_CATEGORY_MATCH
            matched_terms.append(f"category:{art_cat_str}")
        elif norm_query and art_cat_str.lower() in norm_query:
            raw_score += SCORE_CATEGORY_MATCH
            matched_terms.append(f"category:{art_cat_str}")

        # 3. Symptom Matches
        for sym in article.symptoms:
            sym_lower = sym.lower()
            if norm_query and norm_query in sym_lower:
                raw_score += SCORE_SYMPTOM_MATCH
                matched_terms.append(f"symptom_phrase:{sym}")
            else:
                for kw in keywords:
                    if kw in sym_lower:
                        raw_score += SCORE_SYMPTOM_MATCH * 0.5
                        matched_terms.append(f"symptom_kw:{kw}")

        # 4. Cause Matches
        for cause in article.possible_causes:
            cause_lower = cause.lower()
            for kw in keywords:
                if kw in cause_lower:
                    raw_score += SCORE_CAUSE_MATCH * 0.5
                    matched_terms.append(f"cause_kw:{kw}")

        # 5. Diagnostic Step Matches
        for step in article.diagnostic_steps:
            step_lower = step.lower()
            for kw in keywords:
                if kw in step_lower:
                    raw_score += SCORE_DIAGNOSTIC_STEP_MATCH * 0.5
                    matched_terms.append(f"step_kw:{kw}")

        # 6. Tool Reference Matches
        all_tools = article.related_tools + article.repair_references
        for tool_id in all_tools:
            tool_id_lower = tool_id.lower()
            if norm_query and tool_id_lower in norm_query:
                raw_score += SCORE_TOOL_MATCH * 2.0
                matched_terms.append(f"tool:{tool_id}")
            else:
                for kw in keywords:
                    if kw in tool_id_lower:
                        raw_score += SCORE_TOOL_MATCH
                        matched_terms.append(f"tool_kw:{kw}")

        final_score = raw_score * article.confidence
        return final_score, matched_terms
