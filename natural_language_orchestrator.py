"""Natural-Language Query Engine (Phase 6) - SKYFALL v1.0.1

This module implements:
- Intent classification for natural language queries
- Context-aware conversation handling  
- Multi-step instruction understanding
- Dynamic capability selection based on user intent
- Conversation history management
- Suggested next actions
- Error interpretation and recovery
- Follow-up question understanding

Integration points:
- LLM-based classifier uses existing Copilot SDK session
- Routes to MCP capability registry
- Stores context in conversation_store.py SQLite database
from __future__ import annotations
import re
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum
import sqlite3

# Type stubs for async (filled at runtime by Copilot SDK)
from PySide6.QtCore import QObject, Signal, Slot

# Import existing SKYFALL components (available after Phase 1-5 completion)
try:
    from memory.conversation_store import ConversationRecord, MessageRecord, ConversationStore
    from integrations.copilot.copilot_service import CopilotWorker
    from skyfall_mcp.registry import CapabilityRegistry
except ImportError as e:
    # Allow importing even if some components aren't fully ready yet
    ConversationRecord = MessageRecord = ConversationStore = None
    CopilotWorker = CapabilityRegistry = None
# Intent Classification Enums (LLM-assisted)
class QueryIntent(Enum):
    CAPABILITY_DISCOVERY = "capability_discovery"  # List/categorize capabilities
    WORKSPACE_OPERATION = "workspace_operation"  # Workspace search, file metadata
    AZURE_DISCOVERY = "azure_discovery"  # Tenants, subscriptions, resource inventory
    POWER_PLATFORM_INVENTORY = "power_platform_inventory"  # Environments, cloud flows
    AUTHENTICATION_HELP = "authentication_help"  # Sign-in, profile management
    EXECUTION_PLANNING = "execution_planning"  # Multi-step task planning
    REPORTING_QUERY = "reporting_query"  # Report generation requests
    SETTINGS_INQUIRY = "settings_inquiry"  # Configuration changes
    OTHER = "other"  # Unclassified queries

class ErrorType(Enum):
    AUTH_REQUIRED = "authentication_required"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"  
    PERMISSION_DENIED = "permission_denied"
    NO_DATA_FOUND = "no_data_found"
    INVALID_INPUT = "invalid_input"
    NETWORK_ERROR = "network_error"
    UNKNOWN = "unknown"
@dataclass 
class QueryContext:
    """Tracks conversation state for multi-turn interactions."""
    session_id: str
    conversation_id: str
    intent: QueryIntent = field(default=None)
    entities: Dict[str, Any] = field(default_factory=dict)  # Extracted entities (tenants, regions, etc.)
    capabilities_needed: List[str] = field(default_factory=list)
    error_history: List[Dict[str, Any]] = field(default_factory=list)
    context_window: List[Dict[str, Any]] = field(default_factory=list)  # Last N messages for follow-ups

@dataclass 
class ClassificationResult:
    """LLM classification output with confidence scores."""
    intent: QueryIntent
    confidence: float
    entities: Dict[str, Any]
    suggested_actions: List[str]
    error_interpretation: Optional[ErrorType] = None
    follow_up_questions: List[str] = field(default_factory=list)
class NaturalLanguageOrchestrator:
    """LLM-based natural language query engine for SKYFALL v1.0.1."""

    # Intent prompt injected into Copilot session
    INTENT_PROMPT = """"Analyze this user query and classify it into one of these intents:
    
{intent_options}

User Query: {query_text}

Classify and extract any entities, suggested actions, and potential follow-up questions.
Return JSON with structure: {{
    "intent": <one of the above>, 
    "confidence": 0.0-1.0,
    "entities": {{...}},
    "suggested_actions": [...],
    "follow_up_questions": [...]
}}"""

    def __init__(
        self,
        copilot_worker: Optional[CopilotWorker] = None,
        conversation_store: Optional[ConversationStore] = None,
    ):
        """Initialize with Copilot SDK connection and optional conversation storage."""
        self._copilot_worker = copilot_worker
        self._conversation_store = conversation_store or ConversationStore()
        self._registry: Optional[CapabilityRegistry] = None  # Will be initialized when available
        self._context_window_size = 8  # Messages to retain for follow-up understanding
        
        # Pattern-based quick classification fallbacks (when Copilot is unavailable)
        self._quick_intent_patterns = {
            "capability": [r"list\s+(?:capabilities|tools|features)", r"what can you do", r"show me capabilities"],
            "azure": [r"azure.*tenant", r"subscription", r"function app", r"resource inventory"],
            "power_platform": [r"environment", r"cloud flow", r"dataverse", r"power automate"],
            "authentication": [r"sign.*in", r"log.*in", r"account", r"profile"],
            "reporting": [r"export.*excel", r"generate.*report", r"create.*chart", r"download.*csv"],
            "workspace": [r"search\s+file", r"find\s+[^\s]*\.py", r"workspace", r"folder.*metadata"],
        }
