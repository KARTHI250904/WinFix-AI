"""Repository package for WinFix AI SQLite persistence layer.

Provides clean, parameterized data access objects for all core database tables:
sessions, problems, diagnostics, tool_executions, solutions, feedback, and settings.
"""

from database.repositories.diagnostics import DiagnosticRepository
from database.repositories.feedback import FeedbackRepository
from database.repositories.problems import ProblemRepository
from database.repositories.sessions import SessionRepository
from database.repositories.settings import SettingsRepository
from database.repositories.solutions import SolutionRepository
from database.repositories.tool_executions import ToolExecutionRepository

__all__ = [
    "SessionRepository",
    "ProblemRepository",
    "DiagnosticRepository",
    "ToolExecutionRepository",
    "SolutionRepository",
    "FeedbackRepository",
    "SettingsRepository",
]
