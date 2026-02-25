"""LLM initialization and environment configuration."""

import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

# Validate required keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

if not OPENAI_API_KEY:
    raise EnvironmentError(
        "OPENAI_API_KEY is not set. Export it or add it to a .env file."
    )

# Default model for all agents
_MODEL = "gpt-5.1"
_TEMPERATURE = 0.0


def get_llm() -> ChatOpenAI:
    """Return a base LLM instance (no tools bound)."""
    return ChatOpenAI(
        model=_MODEL,
        temperature=_TEMPERATURE,
        api_key=OPENAI_API_KEY,  # type: ignore[arg-type]
    )


def get_llm_with_tools(tools: list) -> ChatOpenAI:
    """Return an LLM instance bound to the provided tools."""
    return get_llm().bind_tools(tools)  # type: ignore[return-value]
