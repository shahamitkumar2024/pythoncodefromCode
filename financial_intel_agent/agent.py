"""
Financial Intelligence Agent — main graph, agent nodes, and entry point.

Pipeline:
  supervisor → web_search → [human confirmation] → web_fetch
             → analyst → presentation → reviewer → supervisor_check

Run with:
    python -m financial_intel_agent.agent "Microsoft"
"""

import os
import re
import sys
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, StateGraph
from langgraph.types import interrupt, Command

from .config import get_llm, get_llm_with_tools
from .prompts import (
    ANALYST_SYSTEM_PROMPT,
    PRESENTATION_SYSTEM_PROMPT,
    REVIEWER_SYSTEM_PROMPT,
    SUPERVISOR_CHECK_PROMPT,
    SUPERVISOR_SYSTEM_PROMPT,
    WEB_DOWNLOADER_SYSTEM_PROMPT,
)
from .state import AgentState
from .tools import (
    ANALYST_TOOLS,
    PRESENTATION_TOOLS,
    REVIEWER_TOOLS,
    WEB_DOWNLOADER_TOOLS,
    search_company_report,
)

_MAX_ITERATIONS = 2


# ---------------------------------------------------------------------------
# Generic agent node helper (LLM + tool loop)
# ---------------------------------------------------------------------------

def _run_agent_node(
    state: AgentState,
    system_prompt: str,
    tools: list,
    input_content: str,
) -> tuple[str, list]:
    """Call LLM in an agentic loop until no more tool calls. Returns (final_text, messages)."""
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
    print(f"\n[SUPERVISOR] Starting analysis for: {company}")
    llm = get_llm()
    msg = llm.invoke([
        SystemMessage(content=SUPERVISOR_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"We are beginning the financial intelligence workflow for '{company}'. "
                "The pipeline is: web_search → human_confirmation → web_fetch → "
                "analyst → presentation → reviewer → supervisor_check. "
                "Confirm briefly."
            )
        ),
    ])
    return {
        "messages": [
            HumanMessage(content=f"Analyze financial opportunities for {company}"),
            msg,
        ],
        "next_agent": "web_search",
    }


# ---------------------------------------------------------------------------
# Web Search node  (direct tool call — no LLM needed)
# ---------------------------------------------------------------------------

def web_search_node(state: AgentState) -> dict:
    """Search for the company's annual reports. Stores results for user confirmation."""
    company = state["company_name"]
    print(f"\n[WEB SEARCH] Searching for {company} financial reports (FY2024 & FY2023)...")

    results = search_company_report.invoke({"company_name": company})

    # Extract the first URL from the formatted results
    url_match = re.search(r"URL:\s*(https?://[^\s\n]+)", results)
    top_url = url_match.group(1).strip() if url_match else ""

    print(f"[WEB SEARCH] Found results. Top URL: {top_url or '(none)'}")
    return {
        "search_results": results,
        "report_url": top_url,
    }


# ---------------------------------------------------------------------------
# Human Confirmation node  (interrupts — waits for user input)
# ---------------------------------------------------------------------------

def human_confirmation_node(state: AgentState) -> dict:
    """Pause the pipeline and show the user what was found. Resume after confirmation."""
    company = state["company_name"]
    search_results = state.get("search_results") or "No results found."
    top_url = state.get("report_url") or "(none found)"

    # Build the confirmation message shown to the user
    display = (
        f"\n{'='*64}\n"
        f"  REPORT SEARCH RESULTS FOR: {company.upper()}\n"
        f"{'='*64}\n\n"
        f"{search_results}\n\n"
        f"{'─'*64}\n"
        f"  Suggested URL : {top_url}\n"
        f"{'─'*64}\n"
        f"  Press Enter / type 'yes'  →  use the suggested URL above\n"
        f"  Paste a different URL     →  use that specific URL instead\n"
        f"  Type 'no'                 →  cancel and exit\n"
        f"{'='*64}"
    )

    # Pause here — the `run()` loop will print this and collect user input
    user_response = interrupt(display)

    resp = str(user_response).strip()

    if resp.lower() in ("no", "n", "cancel", "exit", "quit"):
        print("\n[CONFIRMATION] Cancelled by user.")
        # Setting report_url to None triggers END via route_after_confirmation
        return {"report_url": None}

    if resp.lower().startswith("http"):
        print(f"\n[CONFIRMATION] Using user-provided URL: {resp}")
        return {"report_url": resp}

    # "yes", empty string, or anything else → proceed with top URL
    print(f"\n[CONFIRMATION] Confirmed. Proceeding with: {top_url}")
    return {}


# ---------------------------------------------------------------------------
# Web Fetch node  (LLM agent — fetches confirmed URL, extracts 2 years of data)
# ---------------------------------------------------------------------------

def web_fetch_node(state: AgentState) -> dict:
    """Fetch and extract financial content from the confirmed URL.

    If the primary URL yields too little content (e.g. failed PDF, blocked page),
    the LLM is given all search results and instructed to try alternative URLs.
    """
    company = state["company_name"]
    report_url = state.get("report_url", "")
    search_results = state.get("search_results", "")
    print(f"\n[WEB FETCH] Fetching financial data from: {report_url}")

    input_content = (
        f"Fetch the financial reports for '{company}' from this confirmed URL: {report_url}\n\n"
        "Steps:\n"
        "1. Call fetch_page_content on the PRIMARY URL above.\n"
        "2. Check the result length and quality:\n"
        "   - If it contains substantial financial data (revenue, profit, etc.) → proceed to step 3.\n"
        "   - If it returned an error, 'cannot extract', or fewer than 1000 chars of useful text\n"
        "     → try the ALTERNATIVE URLS listed in the search results below, one at a time,\n"
        "       until you find a page with actual financial data.\n"
        "3. Call extract_financial_tables on the best content retrieved.\n"
        "4. Look for links to the PRIOR YEAR report (FY2023). If found, fetch that too.\n"
        "5. In your final response, consolidate ALL financial data for BOTH FY2024 and FY2023:\n"
        "   - Revenue, Net Income, EBITDA, margins, EPS, Free Cash Flow, R&D spend per year\n"
        "   - Key MD&A / strategic priorities text\n"
        "   - Every source URL used\n\n"
        f"ALTERNATIVE URLS (from original search — use if primary fails):\n{search_results}"
    )

    output, new_messages = _run_agent_node(
        state, WEB_DOWNLOADER_SYSTEM_PROMPT, WEB_DOWNLOADER_TOOLS, input_content
    )

    # Warn if very little content was retrieved
    if len(output) < 2_000:
        print(
            f"[WEB FETCH] WARNING: Only {len(output)} chars retrieved. "
            "The URL may be an unreadable PDF or a blocked page. "
            "Consider re-running and providing a direct HTML investor relations page URL."
        )
    else:
        print(f"[WEB FETCH] Data retrieved ({len(output)} chars)")

    url_match = re.search(r"https?://[^\s\)\"'>]+", output)
    if url_match:
        report_url = url_match.group(0)

    return {
        "raw_report": output,
        "report_url": report_url,
        "messages": new_messages,
    }


# ---------------------------------------------------------------------------
# Analyst node
# ---------------------------------------------------------------------------

def analyst_node(state: AgentState) -> dict:
    company = state["company_name"]
    raw_report = state.get("raw_report", "")
    print(f"\n[ANALYST] Analysing two-year financial data for {company}...")

    input_content = (
        f"Analyse the following financial data for '{company}' covering the last TWO YEARS.\n\n"
        "Steps:\n"
        "1. Call analyze_financial_health to assess data availability for both FY2024 and FY2023.\n"
        "2. Call extract_strategic_initiatives to detect strategic themes across both years.\n"
        "3. Call generate_opportunity_map with your analysis to map themes to TCS services.\n"
        "4. Write a COMPLETE structured analysis with REAL numbers for BOTH years:\n"
        "   (a) Two-Year Financial Health Scorecard — side-by-side FY2024 vs FY2023 table\n"
        "   (b) 3-5 Strategic Initiatives — note which are new vs ongoing between years\n"
        "   (c) TCS Opportunity Map with urgency ratings\n"
        "Do NOT use placeholders — synthesise all tool outputs into a data-rich analysis.\n\n"
        f"RAW REPORT (two years of data):\n{raw_report[:30_000]}"
    )

    output, new_messages = _run_agent_node(
        state, ANALYST_SYSTEM_PROMPT, ANALYST_TOOLS, input_content
    )
    print(f"[ANALYST] Analysis complete ({len(output)} chars)")
    return {"analysis": output, "messages": new_messages}


# ---------------------------------------------------------------------------
# Presentation node
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
            f"\n\nPREVIOUS REVIEW FEEDBACK (must fix ALL issues):\n{review_feedback}\n\n"
        )

    input_content = (
        f"Write a complete TCS business development presentation for '{company}'.\n\n"
        f"{revision_context}"
        "Instructions:\n"
        "1. Write ALL slide content with REAL DATA from the analysis — no placeholders.\n"
        "2. The Financial Health slide MUST have a table with both FY2024 and FY2023 columns.\n"
        "3. Call format_tcs_value_props with the initiative keywords.\n"
        "4. Incorporate those value props into the relevant TCS Service Alignment slides.\n"
        "5. Call save_as_powerpoint with the COMPLETE Markdown and the company name.\n"
        "   The tool converts your Markdown into a .pptx file automatically.\n\n"
        f"ANALYSIS:\n{analysis}"
    )

    output, new_messages = _run_agent_node(
        state, PRESENTATION_SYSTEM_PROMPT, PRESENTATION_TOOLS, input_content
    )

    # Extract the actual Markdown from the save_as_powerpoint tool call args.
    # If the LLM never called the tool (or it failed), fall back to the response text.
    pres_content = output
    for msg in new_messages:
        if hasattr(msg, "tool_calls"):
            for tc in msg.tool_calls:
                if tc["name"] == "save_as_powerpoint":
                    pres_content = tc["args"].get("content", output)
                    break

    # ── Guarantee the .pptx is always written ─────────────────────────────
    # Don't rely solely on the LLM having called save_as_powerpoint successfully.
    from .tools import save_as_powerpoint as _save_pptx
    safe_name = re.sub(r"[^\w\-]", "_", company.lower())
    pptx_path = os.path.join(os.getcwd(), f"presentation_{safe_name}.pptx")
    save_result = _save_pptx.invoke({"content": pres_content, "company_name": company})
    print(f"[PRESENTATION] {save_result}")

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
        "Use verify_financial_facts to cross-check numbers against the raw report, "
        "check_tcs_claims to validate TCS capability statements, "
        "and generate_review_report to compile the final verdict.\n\n"
        "Pay special attention to: does the presentation include data for BOTH FY2024 and FY2023?\n\n"
        f"PRESENTATION:\n{presentation}\n\n"
        f"RAW REPORT:\n{raw_report[:20_000]}"
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
                f"Iteration: {iteration}\n\n"
                f"REVIEWER FEEDBACK:\n{review_feedback}\n\n"
                f"PRESENTATION EXCERPT:\n{presentation[:3_000]}\n\n"
                f"RAW REPORT EXCERPT:\n{raw_report[:2_000]}\n\n"
                "Output DECISION: APPROVE or DECISION: REVISE, then produce the supervisor_verdict."
            )
        ),
    ])

    verdict_text = response.content if isinstance(response.content, str) else str(response.content)

    if "DECISION: REVISE" in verdict_text and iteration < _MAX_ITERATIONS:
        next_step = "presentation"
        print(f"[SUPERVISOR CHECK] REVISE — retry iteration {iteration + 1}")
    else:
        next_step = END
        status = "APPROVE_WITH_CAVEATS" if iteration >= _MAX_ITERATIONS else "APPROVE"
        print(f"[SUPERVISOR CHECK] {status}")

    return {
        "supervisor_verdict": verdict_text,
        "next_agent": next_step,
        "iteration": iteration + 1,
        "messages": [response],
    }


# ---------------------------------------------------------------------------
# Routing functions
# ---------------------------------------------------------------------------

def route_after_confirmation(state: AgentState) -> Literal["web_fetch", "__end__"]:
    """Proceed to fetch if user confirmed a URL; otherwise end gracefully."""
    return "web_fetch" if state.get("report_url") else END


def route_after_review(state: AgentState) -> Literal["presentation", "__end__"]:
    """Route to presentation for revision or END for approval."""
    return "presentation" if state.get("next_agent") == "presentation" else END


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def construct_graph(checkpointer=None):
    """Build and compile the LangGraph workflow.

    Args:
        checkpointer: A LangGraph checkpointer (required for human-in-the-loop interrupt).
                      Pass MemorySaver() when calling run().
    """
    graph = StateGraph(AgentState)

    graph.add_node("supervisor",       supervisor_node)
    graph.add_node("web_search",       web_search_node)
    graph.add_node("human_confirm",    human_confirmation_node)
    graph.add_node("web_fetch",        web_fetch_node)
    graph.add_node("analyst",          analyst_node)
    graph.add_node("presentation",     presentation_node)
    graph.add_node("reviewer",         reviewer_node)
    graph.add_node("supervisor_check", supervisor_check_node)

    graph.set_entry_point("supervisor")
    graph.add_edge("supervisor",    "web_search")
    graph.add_edge("web_search",    "human_confirm")
    graph.add_edge("web_fetch",     "analyst")
    graph.add_edge("analyst",       "presentation")
    graph.add_edge("presentation",  "reviewer")
    graph.add_edge("reviewer",      "supervisor_check")

    # After user confirmation: proceed to fetch OR cancel
    graph.add_conditional_edges(
        "human_confirm",
        route_after_confirmation,
        {"web_fetch": "web_fetch", END: END},
    )

    # After supervisor review: revise OR approve
    graph.add_conditional_edges(
        "supervisor_check",
        route_after_review,
        {"presentation": "presentation", END: END},
    )

    return graph.compile(checkpointer=checkpointer)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(company_name: str) -> None:
    """Run the full financial intelligence pipeline with human-in-the-loop confirmation."""
    from langgraph.checkpoint.memory import MemorySaver

    print(f"\n{'='*64}")
    print(f"  Financial Intelligence Agent  [GPT + PowerPoint]")
    print(f"  Target: {company_name}")
    print(f"{'='*64}\n")

    checkpointer = MemorySaver()
    app = construct_graph(checkpointer)

    thread_id = re.sub(r"[^\w\-]", "-", company_name.lower())
    config = {"configurable": {"thread_id": thread_id}}

    initial_state: AgentState = {
        "company_name": company_name,
        "search_results": None,
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

    # First run — will pause at the human_confirm interrupt
    app.invoke(initial_state, config=config)

    # Handle interrupts (there is exactly one: the confirmation step)
    while True:
        snapshot = app.get_state(config)
        if not snapshot.next:
            break  # graph completed

        # Collect the interrupt value from the paused task
        interrupt_value = None
        for task in snapshot.tasks:
            for intr in task.interrupts:
                interrupt_value = intr.value
                break
            if interrupt_value is not None:
                break

        # Display the interrupt message to the user
        print(interrupt_value or "[Waiting for confirmation]")
        user_input = input("\n>>> Your response: ").strip()

        # Resume the graph with the user's answer
        app.invoke(Command(resume=user_input), config=config)

    # Retrieve the final state
    final_state = app.get_state(config).values

    print(f"\n{'='*64}")
    print("  PIPELINE COMPLETE")
    print(f"{'='*64}")
    print(f"\nCompany:    {company_name}")
    print(f"Source URL: {final_state.get('report_url', 'N/A')}")
    print(f"Iterations: {final_state.get('iteration', 0)}")
    print(f"\n--- SUPERVISOR VERDICT ---\n")
    print(final_state.get("supervisor_verdict", "No verdict produced."))
    print(f"\n{'='*64}\n")

    safe_name = re.sub(r"[^\w\-]", "_", company_name.lower())
    pptx_file = f"presentation_{safe_name}.pptx"
    if os.path.exists(pptx_file):
        print(f"PowerPoint saved to: {os.path.abspath(pptx_file)}")
    else:
        print("Note: .pptx file not found in current directory.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m financial_intel_agent.agent <company_name>")
        print("Example: python -m financial_intel_agent.agent Microsoft")
        sys.exit(1)

    run(" ".join(sys.argv[1:]))
