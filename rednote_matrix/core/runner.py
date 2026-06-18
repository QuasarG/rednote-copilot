from __future__ import annotations

from rednote_matrix.core.graph import build_graph
from rednote_matrix.core.models import AgentInput, AgentResult


def run_agent(user_input: dict | AgentInput) -> AgentResult:
    validated_input = user_input if isinstance(user_input, AgentInput) else AgentInput.model_validate(user_input)
    app = build_graph()
    state = app.invoke(
        {
            "user_input": validated_input.model_dump(),
            "loop_count": 0,
            "revision_history": [],
        }
    )
    return AgentResult.model_validate(state["final_output"])
