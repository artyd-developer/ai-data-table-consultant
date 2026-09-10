from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import select

from app.data.database import DuckDBManager
from app.db.database import SessionLocal
from app.db.models import Dataset


class DatasetService:

    def __init__(self):
        """Initialize the dataset service and DuckDB manager."""
        self.duckdb = DuckDBManager()
        
    def create_dataset(
        self,
        name: str,
        columns: list[str],
        rows: list[list],
        description: str | None = None,
        source_type: str = "manual",
        original_filename: str | None = None,
    ) -> dict:
        """Create a dataset, persist its metadata, and create its DuckDB table.

        Args:
            name: Human-readable dataset name.
            columns: List of dataset column names.
            rows: Dataset rows represented as lists of values.
            description: Optional dataset description.
            source_type: Source type of the dataset.
            original_filename: Optional original uploaded filename.

        Returns:
            Serialized dataset metadata.

        Raises:
            ValueError: If columns or rows are empty, or row lengths differ.
        """

        if not columns:
            raise ValueError(
                "Dataset must contain at least one column"
            )

        if not rows:
            raise ValueError(
                "Dataset must contain at least one row"
            )

        column_count = len(columns)

        normalized_rows = []

        for row in rows:
            if len(row) != column_count:
                raise ValueError(
                    "Every row must contain the same number of columns"
                )

            normalized_rows.append(
                [
                    self._normalize_dataframe_value(
                        None if value == "" else value
                    )
                    for value in row
                ]
            )

        db = SessionLocal()

        try:
            dataset = Dataset(
                name=name,
                description=description,
                source_type=source_type,
                original_filename=original_filename,
                columns_json=json.dumps(
                    columns,
                    ensure_ascii=False,
                ),
                rows_json=json.dumps(
                    normalized_rows,
                    ensure_ascii=False,
                    default=str,
                ),
                row_count=len(normalized_rows),
            )

            db.add(dataset)
            db.commit()
            db.refresh(dataset)

            self._create_duckdb_table(
                dataset_id=str(dataset.id),
                columns=columns,
                rows=normalized_rows,
            )

            return self._serialize_dataset(dataset)

        except Exception:
            db.rollback()
            raise

        finally:
            db.close()

    def get_dataset(
        self,
        dataset_id: int,
    ) -> dict | None:
        """Retrieve a dataset by its ID.

        Args:
            dataset_id: Unique dataset identifier.

        Returns:
            Serialized dataset metadata, or None if the dataset does not exist.
        """

        db = SessionLocal()

        try:
            dataset = db.scalar(
                select(Dataset).where(
                    Dataset.id == dataset_id
                )
            )

            if dataset is None:
                return None

            return self._serialize_dataset(dataset)

        finally:
            db.close()

    def list_datasets(self) -> list[dict]:
        """Retrieve all datasets ordered by creation date.

        Returns:
            List of serialized dataset metadata dictionaries.
        """

        db = SessionLocal()

        try:
            datasets = db.scalars(
                select(Dataset).order_by(
                    Dataset.created_at.desc()
                )
            ).all()

            return [
                self._serialize_dataset(dataset)
                for dataset in datasets
            ]

        finally:
            db.close()

    def get_dataset_schema(
        self,
        dataset_id: int,
    ) -> dict[str, Any]:
        """Retrieve the DuckDB schema for a dataset.

        Args:
            dataset_id: Unique dataset identifier.

        Returns:
            Dictionary containing dataset information, columns, types, and row count.

        Raises:
            ValueError: If the dataset does not exist.
        """

        dataset = self.get_dataset(dataset_id)

        if dataset is None:
            raise ValueError(
                f"Dataset '{dataset_id}' not found"
            )

        connection = self.duckdb.connect(
            str(dataset_id)
        )

        try:
            columns = connection.execute(
                "DESCRIBE data"
            ).fetchall()

            return {
                "dataset_id": dataset_id,
                "name": dataset["name"],
                "columns": [
                    {
                        "name": column[0],
                        "type": column[1],
                    }
                    for column in columns
                ],
                "row_count": dataset["row_count"],
            }

        finally:
            connection.close()

    def get_column_values(
        self,
        dataset_id: int,
        column_name: str,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Retrieve distinct non-null values from a dataset column.

        Args:
            dataset_id: Unique dataset identifier.
            column_name: Name of the column to inspect.
            limit: Maximum number of distinct values to return.

        Returns:
            Dictionary containing the column name, values, count, and applied limit.

        Raises:
            ValueError: If the dataset or column does not exist, or limit is invalid.
        """

        dataset = self.get_dataset(dataset_id)

        if dataset is None:
            raise ValueError(
                f"Dataset '{dataset_id}' not found"
            )

        column_name = column_name.strip()

        if not column_name:
            raise ValueError(
                "column_name cannot be empty"
            )

        if limit < 1:
            raise ValueError(
                "limit must be >= 1"
            )

        limit = min(limit, 500)

        schema = self.get_dataset_schema(
            dataset_id
        )

        dataset_columns = [
            column["name"]
            for column in schema["columns"]
        ]

        if column_name not in dataset_columns:
            raise ValueError(
                f"Column '{column_name}' not found in dataset"
            )

        escaped_column = column_name.replace(
            '"',
            '""',
        )

        sql = f'''
            SELECT DISTINCT
                "{escaped_column}" AS value
            FROM data
            WHERE "{escaped_column}" IS NOT NULL
            ORDER BY value
            LIMIT {limit}
        '''

        connection = self.duckdb.connect(
            str(dataset_id)
        )

        try:
            cursor = connection.execute(sql)

            rows = cursor.fetchall()

            values = [
                row[0]
                for row in rows
            ]

            return {
                "dataset_id": dataset_id,
                "column": column_name,
                "values": values,
                "count": len(values),
                "limit": limit,
            }

        finally:
            connection.close()

    def get_rows(
        self,
        dataset_id: int,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        """Retrieve a paginated subset of dataset rows.

        Args:
            dataset_id: Unique dataset identifier.
            limit: Maximum number of rows to return.
            offset: Number of rows to skip before returning results.

        Returns:
            Dictionary containing columns, selected rows, total row count,
            limit, and offset.

        Raises:
            ValueError: If the dataset does not exist.
        """

        db = SessionLocal()

        try:
            dataset = db.scalar(
                select(Dataset).where(
                    Dataset.id == dataset_id
                )
            )

            if dataset is None:
                raise ValueError(
                    "Dataset not found"
                )

            columns = json.loads(
                dataset.columns_json
            )

            rows = json.loads(
                dataset.rows_json
            )

            selected_rows = rows[
                offset: offset + limit
            ]

            return {
                "dataset_id": dataset.id,
                "columns": columns,
                "rows": selected_rows,
                "row_count": dataset.row_count,
                "limit": limit,
                "offset": offset,
            }

        finally:
            db.close()

    def execute_query(
        self,
        dataset_id: int,
        sql: str,
    ) -> dict[str, Any]:
        """Execute a single read-only SELECT query against a dataset.

        Args:
            dataset_id: Unique dataset identifier.
            sql: DuckDB SELECT query to execute.

        Returns:
            Dictionary containing result columns, rows, and row count.

        Raises:
            ValueError: If the dataset does not exist, SQL is empty,
                the query is not a SELECT statement, or multiple statements
                are provided.
        """

        dataset = self.get_dataset(dataset_id)

        if dataset is None:
            raise ValueError(
                "Dataset not found"
            )

        sql = sql.strip()

        if not sql:
            raise ValueError(
                "SQL query cannot be empty"
            )

        normalized_sql = sql.lower()

        if not normalized_sql.startswith("select"):
            raise ValueError(
                "Only SELECT queries are allowed"
            )

        statements = [
            statement.strip()
            for statement in sql.split(";")
            if statement.strip()
        ]

        if len(statements) != 1:
            raise ValueError(
                "Multiple SQL statements are not allowed"
            )

        connection = self.duckdb.connect(
            str(dataset_id)
        )

        try:
            cursor = connection.execute(sql)

            rows = cursor.fetchall()

            columns = [
                column[0]
                for column in cursor.description
            ]

            return {
                "dataset_id": dataset_id,
                "columns": columns,
                "rows": [
                    list(row)
                    for row in rows
                ],
                "row_count": len(rows),
            }

        finally:
            connection.close()

    def get_sql_columns(
        self,
        dataset_id: int,
        sql: str,
    ) -> list[str]:
        """Determine which dataset columns are referenced by a SQL query.

        Args:
            dataset_id: Unique dataset identifier.
            sql: SQL query to inspect for column references.

        Returns:
            List of dataset column names referenced by the SQL query,
            preserving the order defined by the dataset schema.

        Raises:
            ValueError: If the dataset does not exist.
        """

        dataset = self.get_dataset(dataset_id)

        if dataset is None:
            raise ValueError(
                "Dataset not found"
            )

        schema = self.get_dataset_schema(
            dataset_id
        )

        dataset_columns = [
            column["name"]
            for column in schema["columns"]
        ]

        if not dataset_columns:
            return []

        sql_text = str(sql)

        used_columns: list[str] = []

        for column in dataset_columns:

            column_text = str(column)

            escaped_column = re.escape(
                column_text
            )

            pattern = (
                rf'(?<![A-Za-z0-9_])'
                rf'(?:'
                rf'"{escaped_column}"'
                rf'|'
                rf"'{escaped_column}'"
                rf'|'
                rf'{escaped_column}'
                rf')'
                rf'(?![A-Za-z0-9_])'
            )

            if re.search(
                pattern,
                sql_text,
                flags=re.IGNORECASE,
            ):
                used_columns.append(
                    column_text
                )

        return used_columns

    def delete_dataset(
        self,
        dataset_id: int,
    ) -> bool:
        """Delete a dataset and its associated DuckDB database.

        Args:
            dataset_id: Unique dataset identifier.

        Returns:
            True if the dataset was deleted, otherwise False.
        """

        db = SessionLocal()

        try:
            dataset = db.scalar(
                select(Dataset).where(
                    Dataset.id == dataset_id
                )
            )

            if dataset is None:
                return False

            db.delete(dataset)
            db.commit()

            duckdb_path = self.duckdb.database_path(
                str(dataset_id)
            )

            if duckdb_path.exists():
                duckdb_path.unlink()

            return True

        except Exception:
            db.rollback()
            raise

        finally:
            db.close()

    def _create_duckdb_table(
        self,
        dataset_id: str,
        columns: list[str],
        rows: list[list],
    ) -> None:
        """Create and populate the DuckDB table for a dataset.

        Args:
            dataset_id: Dataset identifier used to locate the DuckDB database.
            columns: Dataset column names.
            rows: Dataset rows to insert into DuckDB.

        Returns:
            None.
        """

        connection = self.duckdb.connect(
            dataset_id
        )

        try:
            safe_columns = [
                self._normalize_column_name(
                    column,
                    index,
                )
                for index, column
                in enumerate(columns)
            ]

            normalized_rows = [
                [
                    self._normalize_dataframe_value(value)
                    for value in row
                ]
                for row in rows
            ]

            column_types = [
                self._infer_column_type(
                    [row[index] for row in normalized_rows]
                )
                for index in range(len(columns))
            ]

            column_sql = ", ".join(
                f'"{column}" {column_type}'
                for column, column_type
                in zip(
                    safe_columns,
                    column_types,
                )
            )

            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS data (
                    {column_sql}
                )
                """
            )

            placeholders = ", ".join(
                ["?"] * len(safe_columns)
            )

            for row in normalized_rows:
                converted_row = [
                    self._convert_value(
                        value,
                        column_type,
                    )
                    for value, column_type
                    in zip(
                        row,
                        column_types,
                    )
                ]

                connection.execute(
                    f"""
                    INSERT INTO data
                    VALUES ({placeholders})
                    """,
                    converted_row,
                )

        finally:
            connection.close()

    @classmethod
    def _infer_column_type(
        cls,
        values: list[Any],
    ) -> str:
        """Infer the DuckDB column type from a collection of values.

        Args:
            values: Values belonging to a single dataset column.

        Returns:
            Inferred DuckDB type name.
        """

        non_empty_values = [
            value
            for value in values
            if value is not None
            and value != ""
        ]

        if not non_empty_values:
            return "VARCHAR"

        if all(
            isinstance(value, bool)
            for value in non_empty_values
        ):
            return "BOOLEAN"

        if all(
            isinstance(value, int)
            and not isinstance(value, bool)
            for value in non_empty_values
        ):
            return "BIGINT"

        if all(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            for value in non_empty_values
        ):
            return "DOUBLE"

        if all(
            isinstance(value, datetime)
            for value in non_empty_values
        ):
            return "TIMESTAMP"

        if all(
            isinstance(value, date)
            and not isinstance(value, datetime)
            for value in non_empty_values
        ):
            return "DATE"

        if all(
            cls._is_date_string(value)
            for value in non_empty_values
        ):
            return "DATE"

        if all(
            cls._is_integer_string(value)
            for value in non_empty_values
        ):
            return "BIGINT"

        if all(
            cls._is_float_string(value)
            for value in non_empty_values
        ):
            return "DOUBLE"

        return "VARCHAR"

    @staticmethod
    def _is_integer_string(
        value: Any,
    ) -> bool:
        """Check whether a value is a valid integer string.

        Args:
            value: Value to validate.

        Returns:
            True if the value is a string representing an integer,
            otherwise False.
        """

        if not isinstance(value, str):
            return False

        value = value.strip()

        return bool(
            re.fullmatch(
                r"[+-]?\d+",
                value,
            )
        )

    @staticmethod
    def _is_float_string(
        value: Any,
    ) -> bool:
        """Check whether a value is a valid floating-point string.

        Args:
            value: Value to validate.

        Returns:
            True if the value represents a floating-point number,
            otherwise False.
        """

        if not isinstance(value, str):
            return False

        value = value.strip()

        try:
            float(value)
            return (
                "." in value
                or "e" in value.lower()
            )
        except ValueError:
            return False

    @staticmethod
    def _is_date_string(
        value: Any,
    ) -> bool:
        """Check whether a value is a date string in YYYY-MM-DD format.

        Args:
            value: Value to validate.

        Returns:
            True if the value is a valid date string, otherwise False.
        """

        if not isinstance(value, str):
            return False

        value = value.strip()

        try:
            datetime.strptime(
                value,
                "%Y-%m-%d",
            )

            return True

        except ValueError:
            return False

    @staticmethod
    def _convert_value(
        value: Any,
        column_type: str,
    ) -> Any:
        """Convert a value to the target DuckDB-compatible type.

        Args:
            value: Value to convert.
            column_type: Target DuckDB column type.

        Returns:
            Converted Python value suitable for insertion into DuckDB.

        Raises:
            ValueError: If the value cannot be converted to the requested type.
        """

        if value is None or value == "":
            return None

        if column_type == "DATE":

            if isinstance(value, date):
                return value

            return datetime.strptime(
                str(value).strip(),
                "%Y-%m-%d",
            ).date()

        if column_type == "TIMESTAMP":

            if isinstance(value, datetime):
                return value

            return datetime.fromisoformat(
                str(value).strip()
            )

        if column_type == "BOOLEAN":

            if isinstance(value, bool):
                return value

            normalized = str(
                value
            ).strip().lower()

            if normalized in {
                "true",
                "1",
                "yes",
                "y",
            }:
                return True

            if normalized in {
                "false",
                "0",
                "no",
                "n",
            }:
                return False

            raise ValueError(
                f"Cannot convert '{value}' to BOOLEAN"
            )

        if column_type == "BIGINT":
            return int(value)

        if column_type == "DOUBLE":
            return float(value)

        return str(value)

    @staticmethod
    def _normalize_column_name(
        name: str,
        index: int,
    ) -> str:
        """Normalize a dataset column name.

        Args:
            name: Original column name.
            index: Zero-based column index used for fallback naming.

        Returns:
            Normalized column name.
        """

        name = str(name).strip()

        if not name:
            return f"column_{index + 1}"

        return name

    @staticmethod
    def _serialize_dataset(
        dataset: Dataset,
    ) -> dict:
        """Serialize a Dataset ORM object into a dictionary.

        Args:
            dataset: SQLAlchemy Dataset model instance.

        Returns:
            Dictionary containing serialized dataset metadata.
        """

        return {
            "id": dataset.id,
            "name": dataset.name,
            "description": dataset.description,
            "source_type": dataset.source_type,
            "original_filename": dataset.original_filename,
            "columns": json.loads(
                dataset.columns_json
            ),
            "row_count": dataset.row_count,
            "created_at": dataset.created_at,
            "updated_at": dataset.updated_at,
        }

    @staticmethod
    def _normalize_dataframe_value(
        value: Any,
    ) -> Any:
        """Normalize pandas, NumPy, and datetime values into Python values.

        Args:
            value: Value to normalize.

        Returns:
            Normalized Python value, preserving supported date and datetime types.
        """

        if value is None:
            return None

        if isinstance(value, float):
            if value != value:
                return None

        if hasattr(value, "item"):
            try:
                value = value.item()
            except (ValueError, TypeError):
                pass

        if hasattr(value, "to_pydatetime"):
            try:
                value = value.to_pydatetime()
            except (ValueError, TypeError):
                pass

        if isinstance(value, datetime):
            return value

        if isinstance(value, date):
            return value

        return value
