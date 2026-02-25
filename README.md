# Financial Intelligence Agent

A LangGraph multi-agent system that helps System Integrators (like TCS) identify business
opportunities from a target company's latest P&L / annual report.

## Architecture

```
User Input (company name)
        │
        ▼
  ┌─────────────┐
  │  SUPERVISOR │  ◄─── orchestrates & fact-checks
  └──────┬──────┘
         │
    ┌────┴──────────────────────────────┐
    ▼         ▼            ▼            ▼
┌────────┐ ┌────────┐ ┌────────┐ ┌──────────┐
│  WEB   │ │ANALYST │ │PRESENT │ │REVIEWER  │
│DOWNLDR │ │ AGENT  │ │ AGENT  │ │  AGENT   │
└────────┘ └────────┘ └────────┘ └──────────┘
```

**Pipeline:** `supervisor → web_downloader → analyst → presentation → reviewer → supervisor_check`

With an optional revision loop (max 2 retries) if the reviewer returns `NEEDS_REVISION`.

## Setup

```bash
cd /Users/amit/pythongentsbycode
pip install -r requirements.txt
```

Create a `.env` file (or export env vars):

```env
OPENAI_API_KEY=sk-...
TAVILY_API_KEY=tvly-...   # optional — falls back to DuckDuckGo scraping
```

## Usage

```bash
python -m financial_intel_agent.agent "Microsoft"
python -m financial_intel_agent.agent "Walmart"
python -m financial_intel_agent.agent "JPMorgan Chase"
```

### Expected Output

1. Console logs showing each agent handoff with status
2. `presentation_<company>.md` written to the current directory
3. Final supervisor verdict printed to stdout

## File Structure

```
financial_intel_agent/
├── __init__.py       — package marker
├── state.py          — AgentState TypedDict
├── config.py         — LLM initialization (GPT-4o, temp=0)
├── prompts.py        — system prompts for all agents
├── tools.py          — @tool-decorated functions grouped by agent
└── agent.py          — nodes, graph construction, __main__ entry
requirements.txt
README.md
```

## Agents & Responsibilities

| Agent | Node | Key Tools |
|-------|------|-----------|
| Supervisor | `supervisor_node` | LLM-only (routing) |
| Web Downloader | `web_downloader_node` | `search_company_report`, `fetch_page_content`, `extract_financial_tables` |
| Financial Analyst | `analyst_node` | `analyze_financial_health`, `extract_strategic_initiatives`, `generate_opportunity_map` |
| Presentation | `presentation_node` | `create_presentation`, `format_tcs_value_props`, `save_presentation` |
| Reviewer | `reviewer_node` | `verify_financial_facts`, `check_tcs_claims`, `generate_review_report` |
| Supervisor Check | `supervisor_check_node` | LLM-only (verdict + routing) |

## Revision Loop

If the Reviewer returns `VERDICT: NEEDS_REVISION`, the Supervisor Check routes back to the
Presentation agent with the feedback included. Maximum 2 revision iterations before
auto-approving with caveats.

## Output Format

The generated `presentation_<company>.md` follows this structure:

1. Executive Summary
2. Company Financial Health (scorecard table)
3. Strategic Priorities
4. TCS Service Alignment (one slide per initiative)
5. Proposed Engagement Model
6. Next Steps & Call to Action
