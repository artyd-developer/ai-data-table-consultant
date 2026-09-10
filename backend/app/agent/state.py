from __future__ import annotations

from typing import Any, Annotated

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict, total=False):
    """
    Runtime state of the data analysis agent.

    The state is intentionally explicit: every important step of
    the agent execution is represented here.
    """

    messages: Annotated[list[AnyMessage], add_messages]

    dataset_id: int
    question: str

    schema: dict[str, Any]
    sample: list[dict[str, Any]]

    sql: str
    sql_error: str | None

    result: dict[str, Any] | None

    answer: str

    input_tokens: int
    output_tokens: int
