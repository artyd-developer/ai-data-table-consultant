[English](README.md) | [Русский](README.ru.md)

# AI Data Table Consultant

<video src="https://github.com/user-attachments/assets/779dbd5b-3659-4dae-91cc-acab694d05c1" controls width="800"></video>

A web application for analyzing tabular data using local LLM models via Ollama.
The user uploads CSV, XLS or XLSX, selects a model, and can then ask questions about the data in natural language.
AI analyzes data through SQL tools, and the used columns of the table are highlighted visually.

## Project Idea

AI Data Table Consultant turns tabular data analysis into an ordinary dialogue with AI.
Instead of manually writing formulas and complex filters, the user asks a question in natural language.
LangGraph manages the AI Agent, which can independently:

- retrieve the dataset schema;
- retrieve sample data;
- generate SQL;
- execute SQL through a tool;
- process the result or error;
- retry execution if necessary;
- form the final answer.

The user receives not only the AI's answer but also a visual understanding of which data was used to form the answer.
The architecture separates responsibility between components:

- **Frontend** is responsible for the interface and data display.
- **Backend** is responsible for the API, data storage, and AI integration.
- **LangGraph** is responsible for the state and logic of the AI agent.
- **Ollama** is responsible for running the LLM locally.

## Features

- Viewing data as a table.
- Uploading CSV, XLS and XLSX.
- Working with local LLMs via Ollama.
- Synchronization of Ollama models.
- Chat with AI about the selected table.
- Streaming responses via Server-Sent Events (SSE).
- AI agent based on LangGraph.
- Tool calling for working with data.
- Retrieving schema and sample data.
- Generation and execution of SQL queries against the data.
- Highlighting of columns used by AI for calculations.
- Displaying the number of tokens used.
- Displaying the cost of the request (currently $0 unless a tariff is specified).
- Table pagination.
- Markdown support in AI responses.

## Architecture

```
User
 │
 ▼
Next.js / React
 │
 │ POST /api/chat/stream
 ▼
FastAPI Backend
 │
 ▼
LangGraph
 │
 ├── assistant
 │     │
 │     └── LLM (ChatOllama)
 │
 ├── tools
 │     ├── get_dataset_schema
 │     ├── get_dataset_sample
 │     └── execute_sql
 │
 └──────────────┐
                │
                ▼
             Ollama
                │
                ▼
             Local LLM
```

LangGraph manages the state and logic of the AI Agent:

```
START
  ↓
assistant
  ↓
tool_calls?
 ├── Yes → tools
 │         ↓
 │      assistant
 │
 └── No → END
```

This allows the model to sequentially retrieve information about the dataset, execute SQL, process results or errors, and form the final answer.

## LangGraph

LangGraph is used to build the AI Agent and manage its state and execution loop.

Main nodes:

- **assistant** — LLM based on ChatOllama.
- **tools** — execution of available tools.

Available tools allow:

- retrieving the table schema;
- retrieving a data sample;
- executing SQL queries, SQL query

General loop:

```
assistant
   ↓
tool call
   ↓
tools
   ↓
tool result
   ↓
assistant
   ↓
final answer
```

LangGraph separates the logic of the AI Agent from the API and frontend.

## Ollama

Ollama is used as a local inference service for running LLMs.

The main advantage of this approach is the ability to use local models without having to send data to external AI providers.

Example of installing a model:

```bash
ollama pull llama3.1
```

Check installed models:

```bash
ollama list
```

### Synchronization of Ollama models

The application supports synchronization of models installed in Ollama with the models available in the application.

For example, if a new model was installed in Ollama:

```bash
ollama pull llama3.1
```

the user can click the **Sync** button in the application interface.

After successful synchronization, the model will appear in the dropdown list.


## Frontend

Frontend is built on:

- Next.js
- React
- TypeScript
- Tailwind CSS
- react-markdown
- remark-gfm

Frontend is responsible for:

- displaying the list of tables;
- displaying the selected table;
- pagination;
- uploading CSV/XLS/XLSX files;
- selecting the AI model;
- sending questions to AI;
- processing streaming SSE responses;
- displaying chat history;
- displaying the number of tokens used;
- displaying the cost of requests;
- highlighting columns used by AI;
- displaying errors.

## Backend

Backend is an intermediate API layer between the frontend, the database, and Ollama.

Backend is responsible for:

- uploading and processing files;
- storing tables as files;
- providing table rows;
- storing information about models;
- synchronizing models with Ollama;
- processing AI requests;
- managing the AI agent via LangGraph;
- executing tools;
- forming streaming responses;
- transmitting metadata about the used columns;
- transmitting token usage;
- calculating the cost of requests.


## Installation

### Environment variables

Frontend uses:

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

If the variable is not set, the following is used:

```
http://localhost:8000
```

For development, create a file:

```
.env.local
```

**Important:** variables with the `NEXT_PUBLIC_` prefix are available to client code.

Secret keys, passwords, and other sensitive values should not be stored in `NEXT_PUBLIC_*`.

## Docker

Frontend can be launched via Docker.

Example:

```bash
docker compose up --build
```

The current Dockerfile runs Next.js in development mode.


## Markdown in AI responses

Consultant responses are displayed using:

- react-markdown;
- remark-gfm.

AI can return:

- headings;
- lists;
- tables;
- bold text;
- italics;
- code blocks;
- other Markdown elements.

Example:

```markdown
## Result

The total sales amount is **125,430**.

### Top 3 products

1. Product A — 45,000
2. Product B — 32,000
3. Product C — 21,000
```

## Highlighting AI columns

After the AI request is completed, the backend transmits metadata about the used columns.

Frontend uses this information for visual highlighting of the corresponding table columns.

Thus, the user can see not only the AI's answer but also which data was used to form it.

## Example questions

After uploading a dataset, the user can ask questions in natural language.

**Simple questions:**

- What is the total sales amount?
- How many rows are there in the table?
- What is the average check?
- What is the maximum price?
- What is the minimum price?

**Grouping questions:**

- Which product sells best?
- Compare sales by category.
- Which category brings in the most revenue?
- Show the top 10 products by sales.

**Filtering:**

- Show products with above-average sales.
- Which products cost more than 100?
- Find records for the last month.

**Advanced analysis:**

- Which factors influence sales the most?
- Find anomalous values.
- Compare sales by month.
- Which categories have the highest growth?


## Project status

The project is under development.

The main goal of the project is to provide a convenient interface for analyzing tabular data using local LLMs, using LangGraph to manage the AI Agent and maintaining the connection between the AI's answer and the source data.

## License

MIT License
