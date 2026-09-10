from fastapi.responses import StreamingResponse
import json
from pathlib import Path
import shutil
import uuid

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.chat.service import ChatService
from app.config import settings
from app.data.loader import DatasetLoader
from app.data.service import DatasetService
from app.db.database import SessionLocal
from app.llm.model_registry import ModelRegistry
from app.llm.ollama import OllamaClient


app = FastAPI(
    title="AI Data Table Consultant",
    version="0.1.0",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class DatasetCreateRequest(BaseModel):
    name: str
    columns: list[str]
    rows: list[list]
    description: str | None = None
    source_type: str = "manual"
    original_filename: str | None = None


class ChatRequest(BaseModel):
    model: str
    question: str
    dataset: dict | None = None


class DatasetQueryRequest(BaseModel):
    sql: str


@app.get("/")
def root():
    """
    Return basic information about the application.

    Returns:
        A dictionary containing the application name, version,
        and current running status.
    """

    return {
        "name": "AI Data Table Consultant",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/health")
def health():
    """
    Check the basic health status of the application.

    Returns:
        A dictionary containing the application health status.
    """

    return {
        "status": "ok",
    }

@app.get("/health/ollama")
def ollama_health():
    """
    Check the connection to the Ollama service.

    Returns:
        A dictionary containing the Ollama connection status,
        configured Ollama URL, and number of available models.

    Raises:
        HTTPException: If the Ollama service cannot be reached
            or the request fails.
    """

    try:
        client = OllamaClient()

        models = client.list_models()

        return {
            "status": "ok",
            "ollama_url": settings.ollama_base_url,
            "models_count": len(models),
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Ollama connection failed: {exc}",
        )


@app.get("/api/models")
def get_models():
    """
    Return all active LLM models registered in the database.

    Returns:
        A dictionary containing a list of active models and
        the total number of returned models.

    Raises:
        HTTPException: If the models cannot be retrieved.
    """

    try:
        registry = ModelRegistry()

        models = registry.get_active_models()

        return {
            "models": [
                {
                    "id": model.id,
                    "name": model.name,
                    "provider": model.provider,
                    "display_name": model.display_name,
                    "active": model.active,
                    "context_length": model.context_length,
                    "input_price_per_1m": model.input_price_per_1m,
                    "output_price_per_1m": model.output_price_per_1m,
                    "capabilities": model.capabilities,
                    "parameter_size": model.parameter_size,
                    "quantization_level": model.quantization_level,
                }
                for model in models
            ],
            "count": len(models),
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


@app.post("/api/models/sync")
def sync_models():
    """
    Synchronize available Ollama models with the model registry.

    Returns:
        A dictionary containing the synchronization status,
        number of synchronized models, and model information.

    Raises:
        HTTPException: If model synchronization fails.
    """

    try:
        registry = ModelRegistry()

        models = registry.sync_ollama_models()

        return {
            "status": "ok",
            "count": len(models),
            "models": models,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


@app.post("/api/chat")
def chat(request: ChatRequest):
    """
    Process a chat request using the selected LLM model.

    Args:
        request: Chat request containing the model name,
            user question, and optional dataset information.

    Returns:
        The result returned by the ChatService.

    Raises:
        HTTPException: If the dataset ID is invalid, required
            dataset information is missing, or chat processing fails.
    """

    try:
        dataset_id = None

        if request.dataset is not None:
            dataset_id = request.dataset.get("id")

            if dataset_id is None:
                raise ValueError(
                    "dataset.id is required"
                )

            try:
                dataset_id = int(dataset_id)
            except (TypeError, ValueError):
                raise ValueError(
                    "dataset.id must be an integer"
                )

        service = ChatService()

        result = service.chat(
            model_name=request.model,
            question=request.question,
            dataset_id=dataset_id,
        )

        return result

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    Stream chat events for the selected LLM model.

    Args:
        request: Chat request containing the model name,
            user question, and optional dataset information.

    Returns:
        A StreamingResponse that sends chat events using
        the Server-Sent Events format.

    Raises:
        HTTPException: If an unexpected error occurs while
            creating the streaming response.
    """

    try:
        chat_service = ChatService()

        async def generate():
            """
            Generate Server-Sent Events for the chat response.

            Yields:
                JSON-encoded chat events formatted as
                Server-Sent Events messages.

            Raises:
                ValueError: If the dataset ID is missing or invalid.
            """

            try:
                dataset_id = None

                if request.dataset is not None:

                    dataset_id = request.dataset.get(
                        "id"
                    )

                    if dataset_id is None:
                        raise ValueError(
                            "dataset.id is required"
                        )

                    try:
                        dataset_id = int(
                            dataset_id
                        )

                    except (
                        TypeError,
                        ValueError,
                    ):
                        raise ValueError(
                            "dataset.id must be an integer"
                        )

                async for event in chat_service.chat_stream(
                    model_name=request.model,
                    question=request.question,
                    dataset_id=dataset_id,
                ):

                    yield (
                        "data: "
                        + json.dumps(
                            event,
                            ensure_ascii=False,
                        )
                        + "\n\n"
                    )

            except Exception as exc:

                yield (
                    "data: "
                    + json.dumps(
                        {
                            "type": "error",
                            "message": str(exc),
                        },
                        ensure_ascii=False,
                    )
                    + "\n\n"
                )

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


@app.post("/api/datasets")
def create_dataset(request: DatasetCreateRequest):
    """
    Create a new dataset from manually provided data.

    Args:
        request: Dataset creation request containing the dataset
            name, columns, rows, description, source type,
            and optional original filename.

    Returns:
        A serialized representation of the newly created dataset.

    Raises:
        HTTPException: If the dataset data is invalid or creation
            fails unexpectedly.
    """

    try:
        service = DatasetService()

        return service.create_dataset(
            name=request.name,
            columns=request.columns,
            rows=request.rows,
            description=request.description,
            source_type=request.source_type,
            original_filename=request.original_filename,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


@app.get("/api/datasets")
def get_datasets():
    """
    Return all datasets registered in the database.

    Returns:
        A dictionary containing a list of available datasets.

    Raises:
        HTTPException: If the datasets cannot be retrieved.
    """

    try:
        service = DatasetService()

        return {
            "datasets": service.list_datasets(),
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


@app.get("/api/datasets/{dataset_id}")
def get_dataset(dataset_id: int):
    """
    Return a dataset by its unique identifier.

    Args:
        dataset_id: Unique identifier of the dataset.

    Returns:
        The serialized dataset information.

    Raises:
        HTTPException: If the dataset does not exist or cannot
            be retrieved.
    """

    try:
        service = DatasetService()

        dataset = service.get_dataset(dataset_id)

        if dataset is None:
            raise HTTPException(
                status_code=404,
                detail="Dataset not found",
            )

        return dataset

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


@app.get("/api/datasets/{dataset_id}/rows")
def get_dataset_rows(
    dataset_id: int,
    limit: int = 100,
    offset: int = 0,
):
    """
    Return a paginated subset of rows from a dataset.

    Args:
        dataset_id: Unique identifier of the dataset.
        limit: Maximum number of rows to return. Must be
            between 1 and 1000.
        offset: Number of rows to skip before returning results.
            Must be greater than or equal to 0.

    Returns:
        A dictionary containing dataset columns, selected rows,
        total row count, limit, and offset.

    Raises:
        HTTPException: If limit or offset is invalid, the dataset
            does not exist, or an unexpected error occurs.
    """

    try:
        if limit < 1 or limit > 1000:
            raise HTTPException(
                status_code=400,
                detail="limit must be between 1 and 1000",
            )

        if offset < 0:
            raise HTTPException(
                status_code=400,
                detail="offset must be >= 0",
            )

        service = DatasetService()

        return service.get_rows(
            dataset_id=dataset_id,
            limit=limit,
            offset=offset,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        )

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


@app.delete("/api/datasets/{dataset_id}")
def delete_dataset(dataset_id: int):
    """
    Delete a dataset and its associated DuckDB database.

    Args:
        dataset_id: Unique identifier of the dataset to delete.

    Returns:
        A dictionary containing the deletion status and dataset ID.

    Raises:
        HTTPException: If the dataset does not exist or deletion fails.
    """

    try:
        service = DatasetService()

        deleted = service.delete_dataset(dataset_id)

        if not deleted:
            raise HTTPException(
                status_code=404,
                detail="Dataset not found",
            )

        return {
            "status": "ok",
            "deleted": True,
            "dataset_id": dataset_id,
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


@app.post("/api/datasets/{dataset_id}/query")
def dataset_query(
    dataset_id: int,
    request: DatasetQueryRequest,
):
    """
    Execute a SQL query against a dataset.

    Args:
        dataset_id: Unique identifier of the dataset against
            which the query will be executed.
        request: Request containing the SQL query to execute.

    Returns:
        A dictionary containing the query result columns,
        rows, and row count.

    Raises:
        HTTPException: If the SQL query is invalid or an unexpected
            error occurs while executing it.
    """

    try:
        service = DatasetService()

        return service.execute_query(
            dataset_id=dataset_id,
            sql=request.sql,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


@app.post("/api/datasets/upload")
def upload_dataset(
    file: UploadFile = File(...),
):
    """
    Upload a CSV or Excel file and create a dataset from it.

    Args:
        file: Uploaded dataset file. Supported formats are
            CSV, XLSX, and XLS.

    Returns:
        A dictionary containing the upload status and information
        about the created dataset.

    Raises:
        HTTPException: If the filename is missing, the file format
            is unsupported, the uploaded file cannot be processed,
            or dataset creation fails.
    """

    upload_dir = Path("/app/storage/uploads")

    upload_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="Filename is required",
        )

    suffix = Path(
        file.filename
    ).suffix.lower()

    if suffix not in {
        ".csv",
        ".xlsx",
        ".xls",
    }:
        raise HTTPException(
            status_code=400,
            detail="Supported formats: CSV, XLSX, XLS",
        )

    temp_filename = (
        f"{uuid.uuid4()}{suffix}"
    )

    file_path = (
        upload_dir / temp_filename
    )

    try:
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(
                file.file,
                buffer,
            )

        loader = DatasetLoader()

        result = loader.create_dataset_from_file(
            name=Path(
                file.filename
            ).stem,
            file_path=str(file_path),
            original_filename=file.filename,
        )

        return {
            "status": "ok",
            **result,
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )

    finally:
        try:
            file.file.close()
        except Exception:
            pass

        try:
            if file_path.exists():
                file_path.unlink()
        except Exception:
            pass
