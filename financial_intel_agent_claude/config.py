"""LLM configuration — uses Anthropic Claude instead of OpenAI."""

import os
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

if not ANTHROPIC_API_KEY:
    raise EnvironmentError(
        "ANTHROPIC_API_KEY is not set. Export it or add it to a .env file."
    )

_MODEL = "claude-sonnet-4-6"
_TEMPERATURE = 0.0


def get_llm() -> ChatAnthropic:
    """Return a base Claude instance (no tools bound)."""
    return ChatAnthropic(
        model=_MODEL,
        temperature=_TEMPERATURE,
        api_key=ANTHROPIC_API_KEY,  # type: ignore[arg-type]
    )


def get_llm_with_tools(tools: list) -> ChatAnthropic:
    """Return a Claude instance bound to the provided tools."""
    return get_llm().bind_tools(tools)  # type: ignore[return-value]
