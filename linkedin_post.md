I built a multi-agent AI system using Claude Code — with a single prompt and ~$3.

You give it a company name. It researches financials, analyzes strategic priorities, and generates a ready-to-use pitch deck — fully autonomous.

Here's the technical breakdown:

The system is built on LangGraph with a StateGraph architecture. 6 specialized agent nodes share a typed state (TypedDict) with message accumulation via operator.add — so every agent builds on what came before.

The pipeline:

Supervisor → Web Search → Human Confirmation (interrupt) → Web Fetch → Financial Analyst → Presentation Writer → Reviewer → Supervisor Check

Each agent runs in an agentic tool-calling loop — the LLM keeps invoking tools until there are no more tool_calls in the response. 15 custom @tool-decorated functions handle everything from DuckDuckGo/Tavily search fallback, HTML/PDF parsing (BeautifulSoup + pypdf), regex-based financial metric extraction, to programmatic PowerPoint generation using python-pptx with TCS-branded slide templates.

What makes it interesting:

→ Human-in-the-loop: Uses LangGraph's interrupt() for user confirmation before fetching data. The graph pauses, shows search results, waits for input, and resumes via Command(resume=...).

→ Self-correcting loop: The Reviewer agent cross-checks every financial figure against the raw report using regex matching, flags overclaims in TCS capability statements, and verifies all 6 required slide sections exist. If verdict = NEEDS_REVISION, the Supervisor routes back to the Presentation agent with specific feedback. Max 2 revision iterations before auto-approving with caveats.

→ Two model variants: One pipeline uses GPT-4o (temp=0) producing Markdown output. The other uses Claude Sonnet producing .pptx files directly — same graph structure, different LLM backend. Swapping models was a config change.

→ PowerPoint generation: A full Markdown-to-PPTX converter that parses slide separators (---), renders markdown tables as native PPTX table objects with alternating row colors, handles bullet hierarchies, bold labels, checkboxes — all with TCS brand colors (RGB values and everything).

→ Conditional routing: Two conditional_edges in the graph — one for human confirmation (proceed or cancel), one for the review loop (revise or approve). Clean separation of orchestration logic from agent logic.

The total codebase: ~1,200 lines across 10 files. State management, prompts, tools, graph construction, and a __main__ entry point. Claude Code wrote all of it from a single prompt describing what I wanted.

Total investment: ~$3 in API costs.

We've reached the point where one developer + Claude Code can architect, build, and ship production-grade multi-agent systems in hours, not weeks.

#AI #ClaudeCode #Anthropic #LangGraph #MultiAgentSystems #LangChain #BuildInPublic #Automation #GenerativeAI
