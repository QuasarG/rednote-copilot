from __future__ import annotations

from langgraph.graph import END, StateGraph

from rednote_matrix.agents.compliance_agent import run_compliance_agent
from rednote_matrix.agents.final_packager import run_final_packager
from rednote_matrix.agents.humanizer_agent import run_humanizer_agent
from rednote_matrix.agents.market_research_agent import run_market_research_agent
from rednote_matrix.agents.memory_retriever import run_memory_retriever
from rednote_matrix.agents.structure_agent import run_structure_agent
from rednote_matrix.agents.trend_agent import run_trend_agent
from rednote_matrix.core.models import AgentState

MAX_REVISION_LOOPS = 2


def _mark_revision_loop(state: AgentState) -> AgentState:
    route_reason = state.get("route_reason", "pass")
    if route_reason == "pass":
        return state
    return {**state, "loop_count": int(state.get("loop_count", 0)) + 1}


def route_after_compliance(state: AgentState) -> str:
    route_reason = state.get("route_reason", "pass")
    loop_count = int(state.get("loop_count", 0))
    if route_reason == "pass" or loop_count >= MAX_REVISION_LOOPS:
        return "final_packager"
    if route_reason == "structure_reject":
        return "structure_agent"
    return "humanizer_agent"


def build_graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("memory_retriever", run_memory_retriever)
    workflow.add_node("market_research_agent", run_market_research_agent)
    workflow.add_node("trend_agent", run_trend_agent)
    workflow.add_node("structure_agent", run_structure_agent)
    workflow.add_node("humanizer_agent", run_humanizer_agent)
    workflow.add_node("compliance_agent", run_compliance_agent)
    workflow.add_node("revision_router", _mark_revision_loop)
    workflow.add_node("final_packager", run_final_packager)

    workflow.set_entry_point("memory_retriever")
    workflow.add_edge("memory_retriever", "market_research_agent")
    workflow.add_edge("market_research_agent", "trend_agent")
    workflow.add_edge("trend_agent", "structure_agent")
    workflow.add_edge("structure_agent", "humanizer_agent")
    workflow.add_edge("humanizer_agent", "compliance_agent")
    workflow.add_edge("compliance_agent", "revision_router")
    workflow.add_conditional_edges(
        "revision_router",
        route_after_compliance,
        {
            "structure_agent": "structure_agent",
            "humanizer_agent": "humanizer_agent",
            "final_packager": "final_packager",
        },
    )
    workflow.add_edge("final_packager", END)
    return workflow.compile()
