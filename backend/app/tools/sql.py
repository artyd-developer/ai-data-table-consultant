from __future__ import annotations

from typing import Any

from langchain_core.tools import tool

from app.data.service import DatasetService


def create_sql_tool(
    dataset_id: int,
):
    """
    Create a LangChain tool for executing read-only SQL queries
    against a specific dataset.

    Args:
        dataset_id: Unique identifier of the dataset against which
            SQL queries will be executed.

    Returns:
        A LangChain tool that executes read-only DuckDB SELECT
        queries and returns the query results together with
        the columns used in the SQL query.
    """

    dataset_service = DatasetService()

    @tool
    def execute_sql(
        sql: str,
    ) -> dict[str, Any]:
        """
        Execute a read-only DuckDB SELECT query against the current dataset.

        The SQL must contain exactly one SELECT statement.

        Use this tool for filtering, aggregation, sorting,
        calculations and other dataset queries.

        Args:
            sql: SQL SELECT query to execute against the current
                dataset. The query must contain exactly one SELECT
                statement.

        Returns:
            A dictionary containing the executed SQL query,
            result columns, result rows, result row count,
            and the dataset columns referenced by the SQL query.

        Raises:
            ValueError: If the dataset does not exist, the SQL query
                is empty, the query is not a SELECT statement,
                or multiple SQL statements are provided.
        """

        result = dataset_service.execute_query(
            dataset_id=dataset_id,
            sql=sql,
        )

        used_columns = dataset_service.get_sql_columns(
            dataset_id=dataset_id,
            sql=sql,
        )

        return {
            "sql": sql,
            "columns": result["columns"],
            "rows": result["rows"],
            "row_count": result["row_count"],
            "used_columns": used_columns,
        }

    return execute_sql
