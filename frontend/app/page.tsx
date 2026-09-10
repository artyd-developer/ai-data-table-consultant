"use client";

import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const PAGE_SIZE = 100;

type Model = {
  id: number;
  name: string;
  display_name: string;
  provider: string;
  active: boolean;
  parameter_size?: string | null;
  quantization_level?: string | null;
};

type Dataset = {
  id: number;
  name: string;
  description: string | null;
  source_type: string;
  original_filename: string | null;
  columns: string[] | { name: string; dtype: string }[];
  row_count: number;
};

type DatasetRows = {
  columns: string[] | { name: string; dtype: string }[];
  rows: unknown[][];
  row_count?: number;
  total?: number;
  limit?: number;
  offset?: number;
};

type Message = {
  role: "user" | "assistant";
  content: string;
  model?: string;
  model_display_name?: string;
  input_tokens?: number;
  output_tokens?: number;
  total_tokens?: number;
  cost?: number;
};

export default function Home() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selectedDataset, setSelectedDataset] = useState<Dataset | null>(null);
  const [table, setTable] = useState<DatasetRows | null>(null);

  const [currentPage, setCurrentPage] = useState(1);

  const [models, setModels] = useState<Model[]>([]);
  const [selectedModel, setSelectedModel] = useState("");

  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);

  const [usedColumns, setUsedColumns] = useState<string[]>([]);

  const [loadingDatasets, setLoadingDatasets] = useState(true);
  const [loadingModels, setLoadingModels] = useState(true);
  const [syncingModels, setSyncingModels] = useState(false);
  const [loadingTable, setLoadingTable] = useState(false);
  const [sending, setSending] = useState(false);
  const [uploading, setUploading] = useState(false);

  const [error, setError] = useState("");
  const [uploadError, setUploadError] = useState("");

  useEffect(() => {
    loadModels();
    loadDatasets();
  }, []);

  async function loadModels() {
    try {
      setLoadingModels(true);

      const response = await fetch(`${API_URL}/api/models`);

      if (!response.ok) {
        throw new Error("Failed to load models");
      }

      const data = await response.json();

      const loadedModels: Model[] = data.models || [];

      setModels(loadedModels);

      if (loadedModels.length > 0) {
        setSelectedModel((current) => current || loadedModels[0].name);
      }
    } catch {
      setError("Failed to load model list");
    } finally {
      setLoadingModels(false);
    }
  }

  async function syncModels() {
    try {
      setSyncingModels(true);
      setError("");

      const response = await fetch(`${API_URL}/api/models/sync`, {
        method: "POST",
      });

      if (!response.ok) {
        let message = "Failed to sync Ollama models";

        try {
          const data = await response.json();
          message = data.detail || data.message || message;
        } catch {}

        throw new Error(message);
      }

      await loadModels();
    } catch (error) {
      setError(
        error instanceof Error ? error.message : "Failed to sync Ollama models",
      );
    } finally {
      setSyncingModels(false);
    }
  }

  async function loadDatasets(selectFirst = true) {
    try {
      setLoadingDatasets(true);

      const response = await fetch(`${API_URL}/api/datasets`);

      if (!response.ok) {
        throw new Error("Failed to load datasets");
      }

      const data = await response.json();

      const loadedDatasets: Dataset[] = data.datasets || [];

      setDatasets(loadedDatasets);

      if (selectFirst && loadedDatasets.length > 0) {
        await selectDataset(loadedDatasets[0]);
      }
    } catch {
      setError("Failed to load datasets");
    } finally {
      setLoadingDatasets(false);
    }
  }

  /*
   * Полностью выбирает новый dataset.
   *
   * Здесь чат и usedColumns сбрасываются,
   * потому что это уже действительно другой dataset.
   */
  async function selectDataset(dataset: Dataset) {
    setSelectedDataset(dataset);

    setTable(null);

    setCurrentPage(1);

    setMessages([]);
    setUsedColumns([]);

    await loadTablePage(dataset.id, 1);
  }

  /*
   * Загружает конкретную страницу таблицы.
   *
   * ВАЖНО:
   * здесь НЕТ setMessages([])
   * и НЕТ setUsedColumns([])
   *
   * поэтому при переключении страниц:
   * - чат остается;
   * - выделенные AI-колонки остаются.
   */
  async function loadTablePage(datasetId: number, page: number) {
    try {
      setLoadingTable(true);
      setError("");

      const offset = (page - 1) * PAGE_SIZE;

      const response = await fetch(
        `${API_URL}/api/datasets/${datasetId}/rows?limit=${PAGE_SIZE}&offset=${offset}`,
      );

      if (!response.ok) {
        throw new Error("Failed to load table");
      }

      const data: DatasetRows = await response.json();

      setTable(data);
      setCurrentPage(page);
    } catch {
      setError("Failed to load table");
    } finally {
      setLoadingTable(false);
    }
  }

  async function changePage(page: number) {
    if (!selectedDataset) {
      return;
    }

    const totalRows =
      table?.row_count ?? table?.total ?? selectedDataset.row_count;

    const totalPages = Math.max(1, Math.ceil(totalRows / PAGE_SIZE));

    if (page < 1 || page > totalPages || page === currentPage) {
      return;
    }

    await loadTablePage(selectedDataset.id, page);
  }

  async function handleFileUpload(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];

    if (!file) {
      return;
    }

    setUploadError("");
    setError("");
    setUploading(true);

    try {
      const formData = new FormData();

      formData.append("file", file);

      const name = file.name.replace(/\.[^/.]+$/, "");

      formData.append("name", name);

      const response = await fetch(`${API_URL}/api/datasets/upload`, {
        method: "POST",
        body: formData,
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Failed to upload file");
      }

      const datasetsResponse = await fetch(`${API_URL}/api/datasets`);

      if (!datasetsResponse.ok) {
        throw new Error("File uploaded, but failed to refresh datasets");
      }

      const datasetsData = await datasetsResponse.json();

      const loadedDatasets: Dataset[] = datasetsData.datasets || [];

      setDatasets(loadedDatasets);

      const newDataset = loadedDatasets.find(
        (dataset) => dataset.id === Number(data.dataset_id),
      );

      if (newDataset) {
        await selectDataset(newDataset);
      } else {
        await loadDatasets(false);
      }
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Failed to upload file";

      setUploadError(message);
    } finally {
      setUploading(false);

      event.target.value = "";
    }
  }

  function getColumnName(
    column:
      | string
      | {
          name: string;
          dtype: string;
        },
  ) {
    if (typeof column === "string") {
      return column;
    }

    return column.name;
  }

  function isColumnUsed(
    column:
      | string
      | {
          name: string;
          dtype: string;
        },
  ) {
    const columnName = getColumnName(column);

    return usedColumns.some((usedColumn) => usedColumn === columnName);
  }

  async function sendMessage() {
    const text = question.trim();

    if (!text || sending) {
      return;
    }

    if (!selectedDataset) {
      setError("Please select a dataset first");
      return;
    }

    if (!selectedModel) {
      setError("Please select a model first");
      return;
    }

    setError("");
    setUploadError("");
    setQuestion("");

    /*
     * Только новый вопрос сбрасывает старое выделение.
     *
     * После ответа metadata снова заполнит usedColumns.
     */
    setUsedColumns([]);

    setMessages((current) => [
      ...current,
      {
        role: "user",
        content: text,
        model: selectedModel,
      },
      {
        role: "assistant",
        content: "",
        model: selectedModel,
      },
    ]);

    try {
      setSending(true);

      const response = await fetch(`${API_URL}/api/chat/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        body: JSON.stringify({
          model: selectedModel,
          question: text,
          dataset: {
            id: selectedDataset.id,
          },
        }),
      });

      if (!response.ok) {
        let message = "Request error";

        try {
          const data = await response.json();

          message = data.detail || data.message || message;
        } catch {
          // Response is not JSON.
        }

        throw new Error(message);
      }

      if (!response.body) {
        throw new Error("Server did not return a data stream");
      }

      const reader = response.body.getReader();

      const decoder = new TextDecoder();

      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();

        if (done) {
          break;
        }

        buffer += decoder.decode(value, {
          stream: true,
        });

        const events = buffer.split("\n\n");

        buffer = events.pop() || "";

        for (const event of events) {
          const lines = event.split("\n");

          for (const line of lines) {
            if (!line.startsWith("data:")) {
              continue;
            }

            const rawData = line.slice(5).trim();

            if (!rawData) {
              continue;
            }

            let data: any;

            try {
              data = JSON.parse(rawData);
            } catch (error) {
              console.error("Invalid SSE JSON:", rawData, error);

              continue;
            }

            // ====================================================
            // TOKEN
            // ====================================================

            if (data.type === "token") {
              const content = data.content || "";

              if (!content) {
                continue;
              }

              setMessages((current) => {
                if (current.length === 0) {
                  return current;
                }

                const updated = [...current];

                const lastIndex = updated.length - 1;

                const lastMessage = updated[lastIndex];

                if (lastMessage.role !== "assistant") {
                  return [
                    ...updated,
                    {
                      role: "assistant",
                      content,
                    },
                  ];
                }

                updated[lastIndex] = {
                  ...lastMessage,
                  content: lastMessage.content + content,
                };

                return updated;
              });
            }

            // ====================================================
            // METADATA
            // ====================================================
            else if (data.type === "metadata") {
              const columns = Array.isArray(data.used_columns)
                ? data.used_columns
                : [];

              setUsedColumns(columns);
            }

            // ====================================================
            // ERROR
            // ====================================================
            else if (data.type === "error") {
              throw new Error(data.message || "AI error");
            }

            // ====================================================
            // DONE
            // ====================================================
            else if (data.type === "done") {
              const usage = data.usage || {};

              setMessages((current) => {
                if (current.length === 0) {
                  return current;
                }

                const updated = [...current];

                const lastIndex = updated.length - 1;

                if (updated[lastIndex].role !== "assistant") {
                  return updated;
                }

                updated[lastIndex] = {
                  ...updated[lastIndex],

                  input_tokens: usage.input_tokens || 0,

                  output_tokens: usage.output_tokens || 0,

                  total_tokens: usage.total_tokens || 0,

                  cost: data.cost || 0,
                };

                return updated;
              });
            }
          }
        }
      }

      // Flush decoder
      buffer += decoder.decode();

      if (buffer.trim()) {
        const events = buffer.split("\n\n");

        for (const event of events) {
          const lines = event.split("\n");

          for (const line of lines) {
            if (!line.startsWith("data:")) {
              continue;
            }

            const rawData = line.slice(5).trim();

            if (!rawData) {
              continue;
            }

            try {
              const data = JSON.parse(rawData);

              if (data.type === "error") {
                throw new Error(data.message || "AI error");
              }
            } catch (error) {
              if (error instanceof Error) {
                throw error;
              }
            }
          }
        }
      }
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Failed to get a response from AI.";

      setMessages((current) => {
        if (current.length === 0) {
          return [
            {
              role: "assistant",
              content: `Error: ${message}`,
            },
          ];
        }

        const updated = [...current];

        const lastIndex = updated.length - 1;

        if (updated[lastIndex].role === "assistant") {
          updated[lastIndex] = {
            ...updated[lastIndex],
            content: `Error: ${message}`,
          };
        } else {
          updated.push({
            role: "assistant",
            content: `Error: ${message}`,
          });
        }

        return updated;
      });

      setUsedColumns([]);
    } finally {
      setSending(false);
    }
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();

      sendMessage();
    }
  }

  /*
   * Pagination calculations
   */

  const totalRows =
    table?.row_count ?? table?.total ?? selectedDataset?.row_count ?? 0;

  const totalPages = Math.max(1, Math.ceil(totalRows / PAGE_SIZE));

  const startRow = totalRows === 0 ? 0 : (currentPage - 1) * PAGE_SIZE + 1;

  const endRow =
    totalRows === 0 ? 0 : Math.min(currentPage * PAGE_SIZE, totalRows);

  /*
   * Создаем компактный список страниц.
   *
   * Например:
   *
   * 1 2 3 ... 20
   *
   * или:
   *
   * 1 ... 9 10 11 ... 20
   */

  function getPageNumbers(): (number | string)[] {
    if (totalPages <= 7) {
      return Array.from({ length: totalPages }, (_, index) => index + 1);
    }

    if (currentPage <= 4) {
      return [1, 2, 3, 4, 5, "...", totalPages];
    }

    if (currentPage >= totalPages - 3) {
      return [
        1,
        "...",
        totalPages - 4,
        totalPages - 3,
        totalPages - 2,
        totalPages - 1,
        totalPages,
      ];
    }

    return [
      1,
      "...",
      currentPage - 1,
      currentPage,
      currentPage + 1,
      "...",
      totalPages,
    ];
  }

  return (
    <main className="h-screen bg-slate-100 text-slate-900">
      <div className="flex h-full flex-col">
        {/* ======================================================
            Header
        ====================================================== */}

        <header className="flex h-16 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-6">
          <div>
            <h1 className="text-lg font-semibold">AI Data Table Consultant</h1>

            <p className="text-xs text-slate-500">AI-powered data analysis</p>
          </div>

          <div className="flex items-center gap-3">
            {/* Model */}

            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-500">Model</span>

              <select
                value={selectedModel}
                onChange={(event) => setSelectedModel(event.target.value)}
                disabled={loadingModels || syncingModels || models.length === 0}
                className="max-w-[320px] rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 disabled:bg-slate-100"
              >
                {loadingModels && <option>Loading models...</option>}

                {!loadingModels && models.length === 0 && (
                  <option>No models available</option>
                )}

                {!loadingModels &&
                  models.map((model) => (
                    <option key={model.id} value={model.name}>
                      {model.display_name}
                    </option>
                  ))}
              </select>

              <button
                type="button"
                onClick={syncModels}
                disabled={syncingModels || loadingModels}
                title="Synchronize Ollama models"
                className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <svg
                  className={`h-4 w-4 ${syncingModels ? "animate-spin" : ""}`}
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M4 4v5h5"
                  />

                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M20 20v-5h-5"
                  />

                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M5.5 9A7.5 7.5 0 0118 6.5L20 9"
                  />

                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M18.5 15A7.5 7.5 0 016 17.5L4 15"
                  />
                </svg>

                {syncingModels ? "Syncing..." : "Sync"}
              </button>
            </div>

            {/* Dataset */}

            <select
              value={selectedDataset?.id ?? ""}
              onChange={(event) => {
                const dataset = datasets.find(
                  (item) => item.id === Number(event.target.value),
                );

                if (dataset) {
                  selectDataset(dataset);
                }
              }}
              className="max-w-[220px] rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500"
              disabled={loadingDatasets}
            >
              {loadingDatasets && <option>Loading...</option>}

              {!loadingDatasets && datasets.length === 0 && (
                <option>No datasets</option>
              )}

              {!loadingDatasets &&
                datasets.map((dataset) => (
                  <option key={dataset.id} value={dataset.id}>
                    {dataset.name}
                  </option>
                ))}
            </select>
          </div>
        </header>

        {/* ======================================================
            Errors
        ====================================================== */}

        {(error || uploadError) && (
          <div className="border-b border-red-200 bg-red-50 px-6 py-2 text-sm text-red-700">
            {uploadError || error}
          </div>
        )}

        {/* ======================================================
            Main
        ====================================================== */}

        <div className="flex min-h-0 flex-1">
          {/* ====================================================
              Chat
          ==================================================== */}

          <section className="flex w-[38%] min-w-[360px] flex-col border-r border-slate-200 bg-white">
            <div className="border-b border-slate-200 px-5 py-4">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="font-semibold">Chat</h2>

                  <p className="mt-1 text-xs text-slate-500">
                    Ask questions about the selected table
                  </p>
                </div>

                {selectedModel && (
                  <span className="max-w-[180px] truncate rounded-md bg-blue-50 px-2 py-1 text-[11px] text-blue-700">
                    {selectedModel}
                  </span>
                )}
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-5">
              {messages.length === 0 && (
                <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-5">
                  <p className="text-sm font-medium">What can you ask?</p>

                  <div className="mt-3 space-y-2 text-sm text-slate-600">
                    <p>• Show the total sales amount</p>

                    <p>• Which product sells the best?</p>

                    <p>• Calculate the average price</p>

                    <p>• Compare the products</p>
                  </div>
                </div>
              )}

              <div className="space-y-4">
                {messages.map((message, index) => (
                  <div
                    key={index}
                    className={
                      message.role === "user"
                        ? "flex justify-end"
                        : "flex justify-start"
                    }
                  >
                    <div
                      className={
                        message.role === "user"
                          ? "max-w-[85%] rounded-2xl rounded-br-md bg-blue-600 px-4 py-3 text-sm text-white"
                          : "max-w-[85%] rounded-2xl rounded-bl-md bg-slate-100 px-4 py-3 text-sm text-slate-800"
                      }
                    >
                      <div className="text-sm leading-6">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {message.content}
                        </ReactMarkdown>
                      </div>

                      {message.role === "assistant" && (
                        <div className="mt-3 border-t border-slate-200 pt-3">
                          <div className="flex flex-wrap items-center gap-2">
                            {message.model && (
                              <span className="inline-flex items-center gap-1.5 rounded-md bg-white px-2.5 py-1 text-[11px] font-medium text-slate-700 ring-1 ring-slate-200">
                                <span className="h-1.5 w-1.5 rounded-full bg-blue-500" />

                                {message.model}
                              </span>
                            )}

                            {message.total_tokens !== undefined && (
                              <span className="inline-flex items-center gap-1 rounded-md bg-violet-50 px-2.5 py-1 text-[11px] font-semibold text-violet-700 ring-1 ring-violet-200">
                                <span>Tokens</span>

                                <span>
                                  {message.total_tokens.toLocaleString()}
                                </span>
                              </span>
                            )}

                            {message.input_tokens !== undefined && (
                              <span className="inline-flex items-center gap-1 rounded-md bg-emerald-50 px-2.5 py-1 text-[11px] font-semibold text-emerald-700 ring-1 ring-emerald-200">
                                <span>↑</span>

                                <span>
                                  {message.input_tokens.toLocaleString()}
                                </span>
                              </span>
                            )}

                            {message.output_tokens !== undefined && (
                              <span className="inline-flex items-center gap-1 rounded-md bg-orange-50 px-2.5 py-1 text-[11px] font-semibold text-orange-700 ring-1 ring-orange-200">
                                <span>↓</span>

                                <span>
                                  {message.output_tokens.toLocaleString()}
                                </span>
                              </span>
                            )}

                            {message.cost !== undefined && (
                              <span className="inline-flex items-center rounded-md bg-slate-50 px-2.5 py-1 text-[11px] font-semibold text-slate-700 ring-1 ring-slate-200">
                                ${message.cost.toFixed(6)}
                              </span>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                ))}

                {sending && (
                  <div className="flex justify-start">
                    <div className="rounded-2xl rounded-bl-md bg-slate-100 px-4 py-3 text-sm text-slate-500">
                      Consultant is thinking...
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Chat input */}

            <div className="border-t border-slate-200 p-4">
              <div className="flex items-end gap-2 rounded-xl border border-slate-300 bg-white p-2 focus-within:border-blue-500">
                <textarea
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={
                    selectedDataset
                      ? "Ask a question about the table..."
                      : "Select a dataset first..."
                  }
                  rows={2}
                  disabled={!selectedDataset}
                  className="min-h-[44px] flex-1 resize-none border-0 bg-transparent px-2 py-2 text-sm outline-none disabled:text-slate-400"
                />

                <button
                  onClick={sendMessage}
                  disabled={
                    !question.trim() ||
                    sending ||
                    !selectedDataset ||
                    !selectedModel
                  }
                  className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300"
                >
                  {sending ? "..." : "Send"}
                </button>
              </div>

              <p className="mt-2 px-1 text-[11px] text-slate-400">
                Enter — send · Shift + Enter — new line
              </p>
            </div>
          </section>

          {/* ====================================================
              Table
          ==================================================== */}

          <section className="flex min-w-0 flex-1 flex-col bg-slate-50">
            {/* Table header */}

            <div className="flex h-16 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-5">
              <div>
                <h2 className="font-semibold">
                  {selectedDataset?.name || "Table"}
                </h2>

                {selectedDataset && (
                  <p className="text-xs text-slate-500">
                    {selectedDataset.row_count} rows
                    {selectedDataset.original_filename
                      ? ` · ${selectedDataset.original_filename}`
                      : ""}
                  </p>
                )}
              </div>

              {selectedDataset && (
                <span className="rounded-md bg-slate-100 px-3 py-1 text-xs text-slate-600">
                  Dataset #{selectedDataset.id}
                </span>
              )}
            </div>

            {/* ==================================================
                TABLE SCROLL AREA

                Именно здесь вертикальный scroll.

                Пагинатор находится НИЖЕ этого блока,
                поэтому он не прокручивается вместе с таблицей.
            ================================================== */}

            <div className="min-h-0 flex-1 overflow-y-auto p-5">
              {loadingTable && (
                <div className="flex h-full items-center justify-center text-sm text-slate-500">
                  Loading table...
                </div>
              )}

              {!loadingTable && table && (
                <div className="rounded-lg border border-slate-300 bg-white shadow-sm">
                  {/* Horizontal scroll ONLY for table */}

                  <div
                    className="w-full overflow-x-auto"
                    style={{ maxHeight: "calc(100vh - 300px)" }}
                  >
                    <table className="min-w-max border-collapse text-sm">
                      <thead>
                        <tr>
                          <th className="sticky left-0 top-0 z-20 w-12 border-b border-r border-slate-300 bg-slate-100 px-3 py-2 text-center text-xs font-semibold text-slate-500">
                            #
                          </th>

                          {table.columns.map((column, index) => {
                            const used = isColumnUsed(column);

                            return (
                              <th
                                key={index}
                                className={`sticky top-0 z-10 border-b border-r px-4 py-2 text-left text-xs font-semibold ${
                                  used
                                    ? "ai-column-pulse border-blue-300 text-blue-800"
                                    : "border-slate-300 bg-slate-100 text-slate-700"
                                }`}
                              >
                                <div className="flex items-center gap-2">
                                  {used && (
                                    <span
                                      className="h-2 w-2 shrink-0 rounded-full bg-blue-600"
                                      title="Column used by AI"
                                    />
                                  )}

                                  {getColumnName(column)}
                                </div>
                              </th>
                            );
                          })}
                        </tr>
                      </thead>

                      <tbody>
                        {table.rows.map((row, rowIndex) => {
                          /*
                           * rowIndex теперь локальный для страницы.
                           *
                           * Поэтому добавляем offset,
                           * чтобы номер был глобальным:
                           *
                           * page 1: 1..100
                           * page 2: 101..200
                           * page 3: 201..300
                           */

                          const globalRowIndex =
                            (currentPage - 1) * PAGE_SIZE + rowIndex + 1;

                          return (
                            <tr key={rowIndex} className="hover:bg-blue-50">
                              <td className="sticky left-0 border-b border-r border-slate-200 bg-slate-50 px-3 py-2 text-center text-xs text-slate-400">
                                {globalRowIndex}
                              </td>

                              {row.map((value, columnIndex) => {
                                const column = table.columns[columnIndex];

                                const used = column
                                  ? isColumnUsed(column)
                                  : false;

                                return (
                                  <td
                                    key={columnIndex}
                                    className={`border-b border-r px-4 py-2 whitespace-nowrap ${
                                      used
                                        ? "ai-column-pulse border-blue-200 text-blue-950"
                                        : "border-slate-200"
                                    }`}
                                  >
                                    {value === null || value === undefined
                                      ? ""
                                      : String(value)}
                                  </td>
                                );
                              })}
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {!loadingTable && !table && (
                <div className="flex h-full items-center justify-center text-sm text-slate-500">
                  Select a dataset
                </div>
              )}
            </div>

            {/* ==================================================
                PAGINATION

                Отдельный fixed-height блок.

                Он НЕ находится внутри overflow-y контейнера.
            ================================================== */}

            {selectedDataset && table && (
              <div className="shrink-0 border-t border-slate-200 bg-white px-5 py-3">
                <div className="flex items-center justify-between gap-4">
                  {/* Rows info */}

                  <div className="whitespace-nowrap text-xs text-slate-500">
                    {startRow}–{endRow} of {totalRows.toLocaleString()}
                  </div>

                  {/* Pagination */}

                  <div className="flex items-center gap-1">
                    {/* Previous */}

                    <button
                      type="button"
                      onClick={() => changePage(currentPage - 1)}
                      disabled={currentPage === 1 || loadingTable}
                      className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      ←
                    </button>

                    {/* Pages */}

                    {getPageNumbers().map((page, index) => {
                      if (page === "...") {
                        return (
                          <span
                            key={`ellipsis-${index}`}
                            className="px-2 text-xs text-slate-400"
                          >
                            ...
                          </span>
                        );
                      }

                      const pageNumber = page as number;

                      const active = pageNumber === currentPage;

                      return (
                        <button
                          type="button"
                          key={pageNumber}
                          onClick={() => changePage(pageNumber)}
                          disabled={loadingTable}
                          className={
                            active
                              ? "min-w-[32px] rounded-md bg-blue-600 px-2.5 py-1.5 text-xs font-semibold text-white"
                              : "min-w-[32px] rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                          }
                        >
                          {pageNumber}
                        </button>
                      );
                    })}

                    {/* Next */}

                    <button
                      type="button"
                      onClick={() => changePage(currentPage + 1)}
                      disabled={currentPage >= totalPages || loadingTable}
                      className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      →
                    </button>
                  </div>

                  {/* Page indicator */}

                  <div className="hidden whitespace-nowrap text-xs text-slate-500 sm:block">
                    Page{" "}
                    <span className="font-medium text-slate-700">
                      {currentPage}
                    </span>{" "}
                    of{" "}
                    <span className="font-medium text-slate-700">
                      {totalPages}
                    </span>
                  </div>
                </div>
              </div>
            )}

            {/* ==================================================
                Upload
            ================================================== */}

            <div className="shrink-0 border-t border-slate-200 bg-white px-5 py-3">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium">Upload data</p>

                  <p className="text-xs text-slate-500">CSV, XLS or XLSX</p>
                </div>

                <label
                  className={
                    uploading
                      ? "cursor-not-allowed rounded-lg bg-slate-300 px-4 py-2 text-sm font-medium text-white"
                      : "cursor-pointer rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-700"
                  }
                >
                  {uploading ? "Uploading..." : "Choose file"}

                  <input
                    type="file"
                    accept=".csv,.xls,.xlsx,text/csv,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    className="hidden"
                    disabled={uploading}
                    onChange={handleFileUpload}
                  />
                </label>
              </div>
            </div>
          </section>
        </div>
      </div>
    </main>
  );
}
