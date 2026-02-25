"""
Financial Intelligence Agent — Claude + PowerPoint variant.

Uses Anthropic Claude (claude-sonnet-4-6) instead of GPT-4o and produces
a .pptx PowerPoint file instead of Markdown.

Run with:
    python -m financial_intel_agent_claude.agent "SPAR UK"
"""

import re
import sys
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, StateGraph

# ── Claude-specific imports (only these three differ from the base variant) ──
from .config import get_llm, get_llm_with_tools
from .prompts import (
    ANALYST_SYSTEM_PROMPT,
    PRESENTATION_SYSTEM_PROMPT,
    REVIEWER_SYSTEM_PROMPT,
    SUPERVISOR_CHECK_PROMPT,
    SUPERVISOR_SYSTEM_PROMPT,
    WEB_DOWNLOADER_SYSTEM_PROMPT,
)
from .tools import (
    ANALYST_TOOLS,
    PRESENTATION_TOOLS,
    REVIEWER_TOOLS,
    WEB_DOWNLOADER_TOOLS,
)

from financial_intel_agent.state import AgentState

_MAX_ITERATIONS = 2


# ---------------------------------------------------------------------------
# Generic agent node helper
# ---------------------------------------------------------------------------

def _run_agent_node(
    state: AgentState,
    system_prompt: str,
    tools: list,
    input_content: str,
) -> tuple[str, list]:
    """Call LLM in an agentic loop until no more tool calls, return (final_text, messages)."""
    llm_with_tools = get_llm_with_tools(tools)
    tool_map = {t.name: t for t in tools}

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=input_content),
    ]

    while True:
        response = llm_with_tools.invoke(messages)
        messages.append(response)

        if not response.tool_calls:
            break

        for tc in response.tool_calls:
            tool_fn = tool_map.get(tc["name"])
            if tool_fn is None:
                result = f"Error: unknown tool '{tc['name']}'"
            else:
                try:
                    result = tool_fn.invoke(tc["args"])
                except Exception as exc:
                    result = f"Tool error: {exc}"
            messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))

    final_content = response.content if isinstance(response.content, str) else str(response.content)
    return final_content, messages[1:]  # skip system message


# ---------------------------------------------------------------------------
# Supervisor node
# ---------------------------------------------------------------------------

def supervisor_node(state: AgentState) -> dict:
    company = state["company_name"]
    print(f"\n[SUPERVISOR] Starting Claude analysis for: {company}")
    llm = get_llm()
    msg = llm.invoke([
        SystemMessage(content=SUPERVISOR_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"We are beginning the financial intelligence workflow for '{company}'. "
                "Confirm you understand and will orchestrate the agents in order: "
                "web_downloader → analyst → presentation → reviewer → supervisor_check. "
                "Respond briefly."
            )
        ),
    ])
    return {
        "messages": [
            HumanMessage(content=f"Analyze financial opportunities for {company}"),
            msg,
        ],
        "next_agent": "web_downloader",
    }


# ---------------------------------------------------------------------------
# Web Downloader node
# ---------------------------------------------------------------------------

def web_downloader_node(state: AgentState) -> dict:
    company = state["company_name"]
    print(f"\n[WEB DOWNLOADER] Searching for {company} annual report...")

    input_content = (
        f"Find and retrieve the latest annual report and P&L data for '{company}'.\n\n"
        "Steps:\n"
        "1. Call search_company_report to find the best investor relations URL.\n"
        "2. Call fetch_page_content on the most promising URL to get the full page text.\n"
        "3. Call extract_financial_tables on the page content to pull out key metrics.\n"
        "4. In your final response, include: the source URL, ALL financial figures found "
        "(revenue, profit, EBITDA, margins, YoY changes, EPS, cash flow, R&D spend), "
        "AND any strategic/operational text about the company's priorities. "
        "Include as much raw detail as possible — the analyst depends on this data."
    )

    output, new_messages = _run_agent_node(
        state, WEB_DOWNLOADER_SYSTEM_PROMPT, WEB_DOWNLOADER_TOOLS, input_content
    )

    url_match = re.search(r"https?://[^\s\)\"'>]+", output)
    report_url = url_match.group(0) if url_match else "URL not captured"

    print(f"[WEB DOWNLOADER] Report retrieved ({len(output)} chars). URL: {report_url}")
    return {"raw_report": output, "report_url": report_url, "messages": new_messages}


# ---------------------------------------------------------------------------
# Analyst node
# ---------------------------------------------------------------------------

def analyst_node(state: AgentState) -> dict:
    company = state["company_name"]
    raw_report = state.get("raw_report", "")
    print(f"\n[ANALYST] Analyzing financial data for {company}...")

    input_content = (
        f"Analyze the following financial report for '{company}'.\n\n"
        "Steps:\n"
        "1. Call analyze_financial_health with the raw report.\n"
        "2. Call extract_strategic_initiatives with the raw report.\n"
        "3. Call generate_opportunity_map with your analysis text.\n"
        "4. Write a COMPLETE structured analysis with: (a) Financial Health Scorecard with REAL "
        "numbers, (b) 3-5 Strategic Initiatives with names and descriptions, "
        "(c) TCS Opportunity Map. Synthesise — don't just relay tool outputs.\n\n"
        f"RAW REPORT:\n{raw_report[:30_000]}"
    )

    output, new_messages = _run_agent_node(
        state, ANALYST_SYSTEM_PROMPT, ANALYST_TOOLS, input_content
    )
    print(f"[ANALYST] Analysis complete ({len(output)} chars)")
    return {"analysis": output, "messages": new_messages}


# ---------------------------------------------------------------------------
# Presentation node  (key difference: looks for save_as_powerpoint tool call)
# ---------------------------------------------------------------------------

def presentation_node(state: AgentState) -> dict:
    company = state["company_name"]
    analysis = state.get("analysis", "")
    review_feedback = state.get("review_feedback", "")
    iteration = state.get("iteration", 0)

    print(f"\n[PRESENTATION] Generating PowerPoint for {company} (iteration {iteration})...")

    revision_context = ""
    if review_feedback and iteration > 0:
        revision_context = (
            f"\n\nPREVIOUS REVIEW FEEDBACK (must fix all issues listed):\n{review_feedback}\n\n"
        )

    input_content = (
        f"Write a complete TCS business development presentation for '{company}'.\n\n"
        f"{revision_context}"
        "Instructions:\n"
        "1. Write ALL slide content using REAL DATA from the analysis below — no placeholders.\n"
        "2. Call format_tcs_value_props with the initiative keywords.\n"
        "3. Incorporate those value props into the relevant slides.\n"
        "4. Call save_as_powerpoint with the COMPLETE Markdown and the company name.\n"
        "   The tool converts your Markdown into a .pptx file automatically.\n\n"
        f"ANALYSIS:\n{analysis}"
    )

    output, new_messages = _run_agent_node(
        state, PRESENTATION_SYSTEM_PROMPT, PRESENTATION_TOOLS, input_content
    )

    # Extract actual presentation content from save_as_powerpoint tool call args
    pres_content = output
    for msg in new_messages:
        if hasattr(msg, "tool_calls"):
            for tc in msg.tool_calls:
                if tc["name"] == "save_as_powerpoint":
                    pres_content = tc["args"].get("content", output)
                    break

    print(f"[PRESENTATION] PowerPoint created ({len(pres_content)} chars of source Markdown)")
    return {"presentation": pres_content, "messages": new_messages}


# ---------------------------------------------------------------------------
# Reviewer node
# ---------------------------------------------------------------------------

def reviewer_node(state: AgentState) -> dict:
    company = state["company_name"]
    presentation = state.get("presentation", "")
    raw_report = state.get("raw_report", "")
    print(f"\n[REVIEWER] Reviewing presentation for {company}...")

    input_content = (
        f"Review the following TCS presentation for '{company}'.\n\n"
        "Use verify_financial_facts to cross-check all numbers against the raw report, "
        "check_tcs_claims to validate TCS capability statements, "
        "and generate_review_report to compile the final verdict.\n\n"
        f"PRESENTATION:\n{presentation}\n\n"
        f"RAW REPORT (for fact-checking):\n{raw_report[:20_000]}"
    )

    output, new_messages = _run_agent_node(
        state, REVIEWER_SYSTEM_PROMPT, REVIEWER_TOOLS, input_content
    )

    verdict = "NEEDS_REVISION" if "NEEDS_REVISION" in output else "PASS"
    print(f"[REVIEWER] Review complete. Verdict: {verdict}")
    return {"review_feedback": output, "messages": new_messages}


# ---------------------------------------------------------------------------
# Supervisor check node
# ---------------------------------------------------------------------------

def supervisor_check_node(state: AgentState) -> dict:
    company = state["company_name"]
    review_feedback = state.get("review_feedback", "")
    presentation = state.get("presentation", "")
    raw_report = state.get("raw_report", "")
    iteration = state.get("iteration", 0)

    print(f"\n[SUPERVISOR CHECK] Evaluating review (iteration {iteration})...")

    llm = get_llm()
    response = llm.invoke([
        SystemMessage(content=SUPERVISOR_CHECK_PROMPT),
        HumanMessage(
            content=(
                f"Company: {company}\n"
                f"Current iteration: {iteration}\n\n"
                f"REVIEWER FEEDBACK:\n{review_feedback}\n\n"
                f"PRESENTATION EXCERPT:\n{presentation[:3_000]}\n\n"
                f"RAW REPORT EXCERPT:\n{raw_report[:2_000]}\n\n"
                "Make your routing decision (DECISION: APPROVE or DECISION: REVISE) "
                "and produce the supervisor_verdict."
            )
        ),
    ])

    verdict_text = response.content if isinstance(response.content, str) else str(response.content)

    if "DECISION: REVISE" in verdict_text and iteration < _MAX_ITERATIONS:
        next_step = "presentation"
        print(f"[SUPERVISOR CHECK] Decision: REVISE — retry iteration {iteration + 1}")
    else:
        next_step = END
        status = "APPROVE_WITH_CAVEATS" if iteration >= _MAX_ITERATIONS else "APPROVE"
        print(f"[SUPERVISOR CHECK] Decision: {status}")

    return {
        "supervisor_verdict": verdict_text,
        "next_agent": next_step,
        "iteration": iteration + 1,
        "messages": [response],
    }


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def route_after_review(state: AgentState) -> Literal["presentation", "__end__"]:
    return "presentation" if state.get("next_agent") == "presentation" else END


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def construct_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("supervisor",       supervisor_node)
    graph.add_node("web_downloader",   web_downloader_node)
    graph.add_node("analyst",          analyst_node)
    graph.add_node("presentation",     presentation_node)
    graph.add_node("reviewer",         reviewer_node)
    graph.add_node("supervisor_check", supervisor_check_node)

    graph.set_entry_point("supervisor")
    graph.add_edge("supervisor",       "web_downloader")
    graph.add_edge("web_downloader",   "analyst")
    graph.add_edge("analyst",          "presentation")
    graph.add_edge("presentation",     "reviewer")
    graph.add_edge("reviewer",         "supervisor_check")

    graph.add_conditional_edges(
        "supervisor_check",
        route_after_review,
        {"presentation": "presentation", END: END},
    )

    return graph.compile()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(company_name: str) -> None:
    print(f"\n{'='*60}")
    print(f"  Financial Intelligence Agent  [Claude + PowerPoint]")
    print(f"  Target: {company_name}")
    print(f"{'='*60}\n")

    app = construct_graph()

    initial_state: AgentState = {
        "company_name": company_name,
        "raw_report": None,
        "report_url": None,
        "analysis": None,
        "presentation": None,
        "review_feedback": None,
        "supervisor_verdict": None,
        "next_agent": None,
        "iteration": 0,
        "messages": [],
    }

    final_state = app.invoke(initial_state)

    print(f"\n{'='*60}")
    print("  PIPELINE COMPLETE")
    print(f"{'='*60}")
    print(f"\nCompany:    {company_name}")
    print(f"Source URL: {final_state.get('report_url', 'N/A')}")
    print(f"Iterations: {final_state.get('iteration', 0)}")
    print(f"\n--- SUPERVISOR VERDICT ---\n")
    print(final_state.get("supervisor_verdict", "No verdict produced."))
    print(f"\n{'='*60}\n")

    import os
    safe_name = re.sub(r"[^\w\-]", "_", company_name.lower())
    pptx_file = f"presentation_{safe_name}.pptx"
    if os.path.exists(pptx_file):
        print(f"PowerPoint saved to: {os.path.abspath(pptx_file)}")
    else:
        print("Note: .pptx file not found in current directory — check the verdict for the path.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m financial_intel_agent_claude.agent <company_name>")
        print("Example: python -m financial_intel_agent_claude.agent 'SPAR UK'")
        sys.exit(1)

    run(" ".join(sys.argv[1:]))
