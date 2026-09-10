from pathlib import Path

import duckdb


class DuckDBManager:

    def __init__(self, storage_path: str = "/app/storage"):
        """Initialize the DuckDB manager and ensure the storage directory exists."""

        self.storage_path = Path(storage_path)

        self.storage_path.mkdir(
            parents=True,
            exist_ok=True,
        )

    def database_path(self, dataset_id: str) -> Path:
        """Return the path to the DuckDB database for the specified dataset.

        Args:
            dataset_id: Identifier of the dataset.

        Returns:
            Path to the DuckDB database file associated with the dataset.
        """

        return self.storage_path / f"dataset_{dataset_id}.duckdb"

    def connect(self, dataset_id: str):
        """Open and return a DuckDB connection for the specified dataset.

        Args:
            dataset_id: Identifier of the dataset.

        Returns:
            An active DuckDB database connection.
        """

        path = self.database_path(dataset_id)

        return duckdb.connect(str(path))

    def execute(
        self,
        dataset_id: str,
        sql: str,
        parameters: list | None = None,
    ) -> list[tuple]:
        """Execute a SQL query for the specified dataset and return all rows.

        Args:
            dataset_id: Identifier of the dataset.
            sql: SQL query to execute.
            parameters: Optional list of parameters to bind to the SQL query.

        Returns:
            A list of tuples containing all rows returned by the query.
        """

        connection = self.connect(dataset_id)

        try:
            if parameters:
                result = connection.execute(
                    sql,
                    parameters,
                )
            else:
                result = connection.execute(sql)

            return result.fetchall()

        finally:
            connection.close()
