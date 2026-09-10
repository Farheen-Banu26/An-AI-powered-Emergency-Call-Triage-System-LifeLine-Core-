"""
LangGraph workflow for emergency call triage.

Graph:
  START → analyst → fake_call_check → completeness_checker → summarizer
    ├─ (gathering_info)  → question_generator → END
    └─ (ready_to_dispatch) → service_router → guidance → END
"""

from langgraph.graph import StateGraph, END

from app.ai.state import IncidentState
from app.ai.nodes import (
    analyst_node,
    completeness_node,
    fake_call_node,
    guidance_node,
    question_node,
    router_node,
    summarizer_node,
)


def _should_ask_or_dispatch(state: IncidentState) -> str:
    """Conditional edge: route based on completeness check result."""
    if state.get("status") == "ready_to_dispatch":
        return "service_router"
    return "question_generator"


def build_workflow():
    """Build and compile the full emergency triage LangGraph workflow."""

    graph = StateGraph(IncidentState)

    # ── Add all 7 nodes ──────────────────────────────────────────
    graph.add_node("analyst", analyst_node)
    graph.add_node("fake_call_check", fake_call_node)
    graph.add_node("completeness_checker", completeness_node)
    graph.add_node("question_generator", question_node)
    graph.add_node("service_router", router_node)
    graph.add_node("summarizer", summarizer_node)
    graph.add_node("guidance", guidance_node)

    # ── Set entry point ──────────────────────────────────────────
    graph.set_entry_point("analyst")

    # ── Edges ────────────────────────────────────────────────────
    # analyst → fake_call_check → completeness_checker (always)
    graph.add_edge("analyst", "fake_call_check")
    graph.add_edge("fake_call_check", "completeness_checker")
    
    # completeness_checker → summarizer (always, to provide real-time updates)
    graph.add_edge("completeness_checker", "summarizer")

    # summarizer → (conditional)
    #   gathering_info     → question_generator → END
    #   ready_to_dispatch  → service_router → guidance → END
    graph.add_conditional_edges(
        "summarizer",
        _should_ask_or_dispatch,
        {
            "question_generator": "question_generator",
            "service_router": "service_router",
        },
    )

    graph.add_edge("question_generator", END)
    graph.add_edge("service_router", "guidance")
    graph.add_edge("guidance", END)

    return graph.compile()


# Compiled workflow singleton — import this
emergency_workflow = build_workflow()
