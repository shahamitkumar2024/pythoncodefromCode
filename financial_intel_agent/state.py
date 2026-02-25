"""AgentState definition for the Financial Intelligence multi-agent system."""

import operator
from typing import Annotated, Optional, Sequence
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """Shared state passed between all agents in the graph."""

    # Input
    company_name: str

    # Web Search outputs (shown to user for confirmation before fetching)
    search_results: Optional[str]

    # Web Fetch outputs
    raw_report: Optional[str]
    report_url: Optional[str]

    # Analyst Agent output
    analysis: Optional[str]

    # Presentation Agent output
    presentation: Optional[str]

    # Reviewer Agent output
    review_feedback: Optional[str]

    # Supervisor final fact-check verdict
    supervisor_verdict: Optional[str]

    # Routing decision set by supervisor nodes
    next_agent: Optional[str]

    # Loop counter for revision cycles (max 2 retries)
    iteration: int

    # Accumulated conversation messages
    messages: Annotated[Sequence[BaseMessage], operator.add]
