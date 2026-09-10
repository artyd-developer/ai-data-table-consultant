from __future__ import annotations

from typing import Any

from langchain_core.tools import tool

from app.data.service import DatasetService


def create_dataset_tools(
    dataset_id: int,
):
    """
    Create LangChain tools for working with a specific dataset.

    Args:
        dataset_id: Unique identifier of the dataset for which
            the tools will be created.

    Returns:
        A list of LangChain tools for retrieving dataset schema,
        sample rows, and distinct column values.
    """

    dataset_service = DatasetService()

    @tool
    def get_dataset_schema() -> dict[str, Any]:
        """
        Get the schema and metadata of the current dataset.

        Returns:
            A dictionary containing the dataset name, column names,
            DuckDB data types, and row count.
        """

        return dataset_service.get_dataset_schema(
            dataset_id=dataset_id,
        )

    @tool
    def get_dataset_sample(
        limit: int = 10,
    ) -> dict[str, Any]:
        """
        Get sample rows from the current dataset.

        Use this tool when the schema alone is not enough
        and real example values are needed.

        Args:
            limit: Maximum number of rows to return.
                The value must be at least 1 and is limited
                to a maximum of 50 rows.

        Returns:
            A dictionary containing the dataset columns,
            sample rows, total row count, limit, and offset.

        Raises:
            ValueError: If limit is less than 1.
        """

        if limit < 1:
            raise ValueError("limit must be >= 1")

        if limit > 50:
            limit = 50

        return dataset_service.get_rows(
            dataset_id=dataset_id,
            limit=limit,
            offset=0,
        )

    @tool
    def get_column_values(
        column_name: str,
        limit: int = 100,
    ) -> dict[str, Any]:
        """
        Get distinct real values from a dataset column.

        Use this tool when a question refers to a specific
        value or category and the exact value stored in the
        dataset is unknown.

        Args:
            column_name: Name of the dataset column from which
                distinct values should be retrieved.
            limit: Maximum number of distinct values to return.
                The value must be at least 1 and is limited
                to a maximum of 500 values.

        Returns:
            A dictionary containing the dataset ID, column name,
            distinct non-null values, number of returned values,
            and applied limit.

        Raises:
            ValueError: If column_name is empty or limit is less than 1.
        """

        if not column_name.strip():
            raise ValueError(
                "column_name must not be empty"
            )

        if limit < 1:
            raise ValueError(
                "limit must be >= 1"
            )

        limit = min(limit, 500)

        return dataset_service.get_column_values(
            dataset_id=dataset_id,
            column_name=column_name,
            limit=limit,
        )

    return [
        get_dataset_schema,
        get_dataset_sample,
        get_column_values,
    ]
