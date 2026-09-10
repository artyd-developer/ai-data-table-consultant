from __future__ import annotations

from typing import Any

from langchain_core.messages import SystemMessage
from langchain_ollama import ChatOllama
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from app.agent.state import AgentState
from app.tools import (
    create_dataset_tools,
    create_sql_tool,
)


SYSTEM_PROMPT = """
You are an AI business data analyst.

You answer questions about the current user's dataset.

Available tools:

- get_dataset_schema
- get_dataset_sample
- execute_sql

Important:
- All tools operate on the current dataset automatically.
- Never try to specify or change dataset_id.
- Never invent columns.
- Never invent tables.
- The dataset table is always named "data".
- Use DuckDB SQL syntax.
- Only SELECT queries are allowed.
- Use get_dataset_schema before generating SQL when schema is unknown.
- Use get_dataset_sample when actual values are needed.
- Use execute_sql for filtering, aggregation, sorting and calculations.
- Do not calculate dataset results yourself when SQL can calculate them.
- If execute_sql fails, inspect the error and generate corrected SQL.
- After receiving SQL results, answer the user directly.
- Do not expose hidden reasoning.
- Do not invent facts.
- Answer in the same language as the user.

DATE rules:

- For DATE columns use DuckDB DATE literals.
- Example:
  date >= DATE '2026-01-11'

BOOLEAN rules:

- For BOOLEAN columns use TRUE or FALSE.

SQL naming rules:

- Calculated and aggregated expressions should have meaningful aliases.
- Example:
  SUM(price * quantity) AS total_revenue
""".strip()


def create_llm(
    model_name: str,
) -> ChatOllama:
    """
    Create and configure the Ollama chat model used by the agent.

    The model is configured with zero temperature for deterministic
    analytical responses and streaming enabled for token-by-token
    output.

    Args:
        model_name: Name of the Ollama model to use.

    Returns:
        Configured ChatOllama instance.
    """

    return ChatOllama(
        model=model_name,
        temperature=0.0,
        base_url="http://host.docker.internal:11434",
        streaming=True,
    )


async def assistant_node(
    state: AgentState,
    *,
    model_name: str,
    tools: list,
) -> dict[str, Any]:
    """
    Run the AI assistant for the current graph state.

    Creates the selected Ollama model, binds the available dataset
    and SQL tools, adds the system prompt when necessary, and invokes
    the model with the current conversation messages.

    Args:
        state: Current LangGraph agent state containing conversation messages.
        model_name: Name of the Ollama model that should process the request.
        tools: Tools available to the assistant, such as dataset inspection
            and SQL execution tools.

    Returns:
        A dictionary containing the assistant's generated message.
    """

    llm = create_llm(model_name)

    llm_with_tools = llm.bind_tools(tools)

    messages = state.get("messages", [])

    if not messages or not isinstance(
        messages[0],
        SystemMessage,
    ):
        messages = [
            SystemMessage(
                content=SYSTEM_PROMPT,
            ),
            *messages,
        ]

    response = await llm_with_tools.ainvoke(
        messages,
    )

    return {
        "messages": [response],
    }


def should_continue(
    state: AgentState,
) -> str:
    """
    Determine whether the agent should execute tools or finish.

    The function inspects the latest assistant message. If the model
    requested one or more tool calls, execution is redirected to the
    ToolNode. Otherwise, the graph terminates and the assistant response
    is returned to the user.

    Args:
        state: Current LangGraph agent state.

    Returns:
        "tools" when the assistant requested tool execution,
        otherwise END.
    """

    messages = state.get("messages", [])

    if not messages:
        return END

    last_message = messages[-1]

    tool_calls = getattr(
        last_message,
        "tool_calls",
        None,
    )

    if tool_calls:
        return "tools"

    return END


def build_graph(
    model_name: str,
    dataset_id: int,
):
    """
    Build and compile the dataset analysis agent graph.

    Creates dataset-specific tools and an SQL tool, registers them
    with LangGraph, and connects the assistant and tool execution
    nodes into an agent loop.

    The resulting graph follows this flow:

        START -> assistant -> tools -> assistant -> END

    The assistant may repeatedly call tools until it has enough
    information to answer the user's question.

    Args:
        model_name: Name of the Ollama model used by the assistant.
        dataset_id: ID of the dataset that the tools should operate on.

    Returns:
        A compiled LangGraph agent ready to process AgentState.
    """

    dataset_tools = create_dataset_tools(
        dataset_id=dataset_id,
    )

    sql_tool = create_sql_tool(
        dataset_id=dataset_id,
    )

    tools = [
        *dataset_tools,
        sql_tool,
    ]

    graph = StateGraph(
        AgentState,
    )

    async def assistant(
        state: AgentState,
    ) -> dict[str, Any]:
        """
        Execute the assistant node with the configured model and tools.

        This wrapper allows the graph to call assistant_node while
        keeping the model name and dataset-specific tools captured
        from build_graph().
        """

        return await assistant_node(
            state,
            model_name=model_name,
            tools=tools,
        )

    graph.add_node(
        "assistant",
        assistant,
    )

    graph.add_node(
        "tools",
        ToolNode(
            tools,
            handle_tool_errors=(
                "SQL execution failed. "
                "Inspect the error and generate corrected SQL. "
                "Remember that VARCHAR columns must be explicitly "
                "cast to numeric types before arithmetic."
            ),
        ),
    )

    graph.add_edge(
        START,
        "assistant",
    )

    graph.add_conditional_edges(
        "assistant",
        should_continue,
        {
            "tools": "tools",
            END: END,
        },
    )

    graph.add_edge(
        "tools",
        "assistant",
    )

    return graph.compile()
