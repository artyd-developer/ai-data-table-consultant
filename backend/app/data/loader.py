from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from app.data.database import DuckDBManager
from app.db.database import SessionLocal
from app.db.models import Dataset


class DatasetLoader:

    def __init__(self):
        """Initialize the dataset loader and DuckDB manager."""

        self.db = DuckDBManager()

    def _detect_delimiter(
        self,
        sample: str,
    ) -> str:
        """Detect the most likely CSV delimiter from a text sample.

        Args:
            sample: Text sample read from the CSV file.

        Returns:
            The detected CSV delimiter. Comma is returned if no
            supported delimiter is detected.
        """

        candidates = [",", ";", "\t", "|"]

        first_line = sample.splitlines()[0] if sample else ""

        scores = {
            delimiter: first_line.count(delimiter)
            for delimiter in candidates
        }

        delimiter, score = max(
            scores.items(),
            key=lambda item: item[1],
        )

        if score == 0:
            return ","

        return delimiter

    def _read_csv(
        self,
        path: Path,
    ) -> pd.DataFrame:
        """Read a CSV file while detecting its encoding and delimiter.

        Args:
            path: Path to the CSV file.

        Returns:
            A pandas DataFrame containing the CSV data.

        Raises:
            ValueError: If the file encoding cannot be detected or
                the CSV content cannot be parsed.
        """

        encodings = (
            "utf-8-sig",
            "utf-8",
            "cp1251",
            "cp1252",
        )

        last_decode_error: UnicodeDecodeError | None = None

        encoding: str | None = None
        sample = ""

        for candidate in encodings:
            try:
                with path.open(
                    "r",
                    encoding=candidate,
                    newline="",
                ) as file:
                    sample = file.read(64 * 1024)

                encoding = candidate
                break

            except UnicodeDecodeError as exc:
                last_decode_error = exc

        if encoding is None:
            raise ValueError(
                f"Cannot detect CSV-file encoding: {path}"
            ) from last_decode_error

        delimiter = self._detect_delimiter(sample)

        try:
            return pd.read_csv(
                path,
                encoding=encoding,
                sep=delimiter,
            )

        except pd.errors.ParserError as exc:
            raise ValueError(
                f"Cannot parse CSV file: {path}. "
                f"encoding={encoding!r}, "
                f"delimiter={delimiter!r}"
            ) from exc

    def load(
        self,
        dataset_id: str | int,
        file_path: str,
        table_name: str = "data",
    ) -> dict:
        """Load a CSV or Excel file and store it as a DuckDB table.

        Args:
            dataset_id: Identifier of the dataset used for the DuckDB database.
            file_path: Path to the source CSV or Excel file.
            table_name: Name of the DuckDB table to create or replace.

        Returns:
            A dictionary containing the dataset ID, table name,
            row count, and column names.

        Raises:
            FileNotFoundError: If the source file does not exist.
            ValueError: If the file format is unsupported or the dataset is empty.
        """

        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(path)

        suffix = path.suffix.lower()

        if suffix == ".csv":
            df = self._read_csv(path)

        elif suffix in {".xlsx", ".xls"}:
            df = pd.read_excel(path)

        else:
            raise ValueError(
                "Supported formats: CSV, XLSX, XLS"
            )

        if df.empty:
            raise ValueError(
                "Dataset is empty"
            )

        df = self._normalize_dataframe(df)

        connection = self.db.connect(
            str(dataset_id)
        )

        try:
            connection.register(
                "_uploaded_dataframe",
                df,
            )

            connection.execute(
                f"""
                CREATE OR REPLACE TABLE "{table_name}" AS
                SELECT *
                FROM "_uploaded_dataframe"
                """
            )

        finally:
            connection.close()

        return {
            "dataset_id": dataset_id,
            "table": table_name,
            "rows": len(df),
            "columns": [
                str(column)
                for column in df.columns
            ],
        }

    def create_dataset_from_file(
        self,
        name: str,
        file_path: str,
        description: str | None = None,
        original_filename: str | None = None,
        table_name: str = "data",
    ) -> dict:
        """Create a dataset record and store uploaded data in DuckDB.

        Args:
            name: Name of the dataset.
            file_path: Path to the source CSV or Excel file.
            description: Optional description of the dataset.
            original_filename: Original name of the uploaded file.
            table_name: Name of the DuckDB table to create.

        Returns:
            A dictionary containing dataset metadata, columns,
            row count, and the generated DuckDB schema.

        Raises:
            FileNotFoundError: If the source file does not exist.
            ValueError: If the file format is unsupported or the dataset is empty.
        """

        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(path)

        suffix = path.suffix.lower()

        if suffix == ".csv":
            df = self._read_csv(path)

        elif suffix in {".xlsx", ".xls"}:
            df = pd.read_excel(path)

        else:
            raise ValueError(
                "Supported formats: CSV, XLSX, XLS"
            )

        if df.empty:
            raise ValueError(
                "Dataset is empty"
            )

        df = self._normalize_dataframe(df)

        columns = [
            str(column)
            for column in df.columns
        ]

        rows: list[list[Any]] = []

        for row in df.itertuples(
            index=False,
            name=None,
        ):
            rows.append(
                [
                    self._normalize_dataframe_value(
                        value
                    )
                    for value in row
                ]
            )

        db = SessionLocal()

        try:
            dataset = Dataset(
                name=name,
                description=description,
                source_type="upload",
                original_filename=original_filename,
                columns_json=json.dumps(
                    columns,
                    ensure_ascii=False,
                ),
                rows_json=json.dumps(
                    rows,
                    ensure_ascii=False,
                    default=str,
                ),
                row_count=len(rows),
            )

            db.add(dataset)
            db.commit()
            db.refresh(dataset)

            dataset_id = dataset.id

        except Exception:
            db.rollback()
            raise

        finally:
            db.close()

        try:
            self._write_dataframe(
                dataset_id=dataset_id,
                df=df,
                table_name=table_name,
            )

        except Exception:
            cleanup_db = SessionLocal()

            try:
                broken_dataset = cleanup_db.get(
                    Dataset,
                    dataset_id,
                )

                if broken_dataset is not None:
                    cleanup_db.delete(
                        broken_dataset
                    )
                    cleanup_db.commit()

            except Exception:
                cleanup_db.rollback()

            finally:
                cleanup_db.close()

            raise

        return {
            "id": dataset_id,
            "dataset_id": dataset_id,
            "name": name,
            "filename": original_filename,
            "table": table_name,
            "rows": len(df),
            "columns": columns,
            "schema": self.schema(
                str(dataset_id),
                table_name,
            ),
        }

    def _write_dataframe(
        self,
        dataset_id: int | str,
        df: pd.DataFrame,
        table_name: str = "data",
    ) -> None:
        """Write a pandas DataFrame to a DuckDB table.

        Args:
            dataset_id: Identifier of the dataset used for the DuckDB database.
            df: DataFrame containing the data to write.
            table_name: Name of the DuckDB table to create or replace.

        Returns:
            None.
        """

        connection = self.db.connect(
            str(dataset_id)
        )

        try:
            connection.register(
                "_uploaded_dataframe",
                df,
            )

            connection.execute(
                f"""
                CREATE OR REPLACE TABLE "{table_name}" AS
                SELECT *
                FROM "_uploaded_dataframe"
                """
            )

        finally:
            connection.close()

    def _normalize_dataframe(
        self,
        df: pd.DataFrame,
    ) -> pd.DataFrame:
        """Normalize the data types of all DataFrame columns.

        Args:
            df: DataFrame whose column types should be normalized.

        Returns:
            A copy of the DataFrame with normalized column types.
        """

        result = df.copy()

        for column in result.columns:
            result[column] = (
                self._normalize_dataframe_column(
                    result[column]
                )
            )

        return result

    def _normalize_dataframe_column(
        self,
        series: pd.Series,
    ) -> pd.Series:
        """Detect and normalize the type of a single DataFrame column.

        Args:
            series: Pandas Series containing the column values.

        Returns:
            The Series with a normalized boolean, date, numeric,
            or original data type.
        """

        if (
            pd.api.types.is_bool_dtype(series)
            or pd.api.types.is_integer_dtype(series)
            or pd.api.types.is_float_dtype(series)
            or pd.api.types.is_datetime64_any_dtype(series)
        ):
            return series

        non_null = series.dropna()

        if non_null.empty:
            return series

        values = [
            str(value).strip()
            for value in non_null.tolist()
        ]

        normalized_values = {
            value.lower()
            for value in values
        }

        if normalized_values.issubset(
            {
                "true",
                "false",
                "1",
                "0",
                "yes",
                "no",
                "y",
                "n",
            }
        ):
            return series.map(
                self._normalize_boolean_value
            ).astype("boolean")

        parsed_datetime = pd.to_datetime(
            series,
            format="mixed",
            errors="coerce",
        )

        if (
            parsed_datetime.notna().sum()
            == series.notna().sum()
        ):
            has_time = any(
                value.time() != datetime.min.time()
                for value in parsed_datetime.dropna()
            )

            if has_time:
                return parsed_datetime

            return parsed_datetime.dt.date

        parsed_numeric = pd.to_numeric(
            series,
            errors="coerce",
        )

        if (
            parsed_numeric.notna().sum()
            == series.notna().sum()
        ):
            if all(
                float(value).is_integer()
                for value in parsed_numeric.dropna()
            ):
                return parsed_numeric.astype("Int64")

            return parsed_numeric.astype("Float64")

        return series

    @staticmethod
    def _normalize_boolean_value(
        value: Any,
    ) -> bool | None:
        """Convert a value to a normalized Python boolean or None.

        Args:
            value: Value to normalize as a boolean.

        Returns:
            True or False for recognized boolean values, otherwise None.
        """

        if pd.isna(value):
            return None

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

        return None

    @staticmethod
    def _normalize_dataframe_value(
        value: Any,
    ) -> Any:
        """Convert pandas and NumPy values into standard Python values.

        Args:
            value: Value to normalize.

        Returns:
            A normalized Python value, with missing values converted
            to None and pandas/NumPy scalar types converted where possible.
        """

        if value is None:
            return None

        # NaN / NA
        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass

        # numpy scalar -> Python scalar
        if hasattr(value, "item"):
            try:
                value = value.item()
            except (ValueError, TypeError):
                pass

        # pandas Timestamp -> datetime
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

    def schema(
        self,
        dataset_id: str | int,
        table_name: str = "data",
    ) -> list[dict[str, str]]:
        """Return the DuckDB schema of the specified dataset table.

        Args:
            dataset_id: Identifier of the dataset used for the DuckDB database.
            table_name: Name of the DuckDB table whose schema should be returned.

        Returns:
            A list of dictionaries containing column names and DuckDB types.
        """

        connection = self.db.connect(
            str(dataset_id)
        )

        try:
            rows = connection.execute(
                f'DESCRIBE "{table_name}"'
            ).fetchall()

            return [
                {
                    "name": row[0],
                    "type": row[1],
                }
                for row in rows
            ]

        finally:
            connection.close()

    def sample(
        self,
        dataset_id: str | int,
        table_name: str = "data",
        limit: int = 10,
    ) -> list[dict]:
        """Return a limited sample of rows from a dataset table.

        Args:
            dataset_id: Identifier of the dataset used for the DuckDB database.
            table_name: Name of the DuckDB table to sample.
            limit: Maximum number of rows to return. The value is
                constrained to the range from 1 to 1000.

        Returns:
            A list of dictionaries representing sampled dataset rows.
        """

        if limit < 1:
            limit = 1

        if limit > 1000:
            limit = 1000

        connection = self.db.connect(
            str(dataset_id)
        )

        try:
            result = connection.execute(
                f'''
                SELECT *
                FROM "{table_name}"
                LIMIT {int(limit)}
                '''
            ).fetchdf()

            records = result.to_dict(
                orient="records"
            )

            return [
                {
                    str(key): self._normalize_dataframe_value(
                        value
                    )
                    for key, value in record.items()
                }
                for record in records
            ]

        finally:
            connection.close()
