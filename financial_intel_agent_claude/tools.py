"""Tools for the Claude + PowerPoint variant.

Re-uses ALL tools from the base package (including the PowerPoint builder).
No tool code is duplicated here.
"""

# Re-export everything from base — including save_as_powerpoint which now lives there
from financial_intel_agent.tools import (
    search_company_report,
    fetch_page_content,
    extract_financial_tables,
    analyze_financial_health,
    extract_strategic_initiatives,
    generate_opportunity_map,
    format_tcs_value_props,
    save_as_powerpoint,
    verify_financial_facts,
    check_tcs_claims,
    generate_review_report,
    WEB_DOWNLOADER_TOOLS,
    ANALYST_TOOLS,
    REVIEWER_TOOLS,
)

__all__ = [
    "search_company_report",
    "fetch_page_content",
    "extract_financial_tables",
    "analyze_financial_health",
    "extract_strategic_initiatives",
    "generate_opportunity_map",
    "format_tcs_value_props",
    "save_as_powerpoint",
    "verify_financial_facts",
    "check_tcs_claims",
    "generate_review_report",
    "WEB_DOWNLOADER_TOOLS",
    "ANALYST_TOOLS",
    "PRESENTATION_TOOLS",
    "REVIEWER_TOOLS",
]

PRESENTATION_TOOLS = [format_tcs_value_props, save_as_powerpoint]
