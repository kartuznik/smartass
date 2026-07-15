"""Week 2: multi-agent workflow with reviewer loop."""

from __future__ import annotations

import time
from typing import Literal, TypedDict, cast

from langgraph.graph import END, START, StateGraph

RouteLabel = Literal["writer_node", "__end__"]


class MultiAgentState(TypedDict):
    """Shared state for Researcher -> Writer -> Reviewer workflow."""

    user_id: int
    topic: str
    research_data: str
    draft: str
    feedback: str
    revision_count: int


def research_node(state: MultiAgentState) -> dict[str, str]:
    """Simulate collecting research artifacts for a topic."""
    time.sleep(0.02)
    topic = state["topic"]
    return {
        "research_data": (
            f"Исследование по теме '{topic}': "
            "ключевые идеи, риски, примеры и рекомендации."
        )
    }


def writer_node(state: MultiAgentState) -> dict[str, str]:
    """Produce a draft using research data and reviewer feedback."""
    # Week 2/3 use deterministic mock logic.
    # Future extension: replace this block with LLMConfig.create_chat_model(...)
    # and prompt-based generation while keeping the same state contract.
    time.sleep(0.02)
    topic = state["topic"]
    research_data = state["research_data"]
    feedback = state["feedback"].strip()

    # First attempt can be intentionally weak for loop demonstration.
    if not feedback and "плохой" in topic.lower():
        return {
            "draft": (
                f"Черновик по теме '{topic}'. "
                f"Основа: {research_data}. Требуется доработка."
            )
        }

    if feedback:
        return {
            "draft": (
                f"Улучшенный материал по теме '{topic}': {research_data}. "
                f"Учтена обратная связь: {feedback}. Итог отлично."
            )
        }

    return {
        "draft": (
            f"Черновик по теме '{topic}': {research_data}. "
            "Качество: отлично."
        )
    }


def reviewer_node(state: MultiAgentState) -> dict[str, str | int]:
    """Review draft quality; request revision if needed."""
    time.sleep(0.02)
    draft = state["draft"].lower()
    revision_count = state["revision_count"]

    if "отлично" not in draft:
        return {
            "feedback": "Добавь четкие выводы и сформулируй финальную версию лучше.",
            "revision_count": revision_count + 1,
        }
    return {"feedback": ""}


def route_after_review(state: MultiAgentState) -> RouteLabel:
    """Route back to writer while revision limit is not reached."""
    has_feedback = bool(state["feedback"].strip())
    if state["revision_count"] < 2 and has_feedback:
        return "writer_node"
    return "__end__"


def build_multi_agent_graph():
    """Build and compile Researcher -> Writer -> Reviewer loop graph."""
    graph = StateGraph(MultiAgentState)

    graph.add_node("research_node", research_node)
    graph.add_node("writer_node", writer_node)
    graph.add_node("reviewer_node", reviewer_node)

    graph.add_edge(START, "research_node")
    graph.add_edge("research_node", "writer_node")
    graph.add_edge("writer_node", "reviewer_node")
    graph.add_conditional_edges(
        "reviewer_node",
        route_after_review,
        {"writer_node": "writer_node", "__end__": END},
    )

    return graph.compile()


def build_initial_multi_agent_state(topic: str, user_id: int) -> MultiAgentState:
    """Create a fresh state for one user/topic run."""
    return {
        "user_id": user_id,
        "topic": topic,
        "research_data": "",
        "draft": "",
        "feedback": "",
        "revision_count": 0,
    }


def run_multi_agent(topic: str, user_id: int = 0) -> MultiAgentState:
    """Run workflow with initial state."""
    graph = build_multi_agent_graph()
    initial_state = build_initial_multi_agent_state(topic=topic, user_id=user_id)
    return cast(MultiAgentState, graph.invoke(initial_state))
