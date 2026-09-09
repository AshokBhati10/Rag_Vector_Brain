# VectorBrain

VectorBrain is a multi-document RAG (Retrieval-Augmented Generation) application for asking questions about uploaded PDF files. It combines document parsing, semantic embeddings, vector similarity search, and LLM generation to produce answers grounded in the selected documents with source references.

## How It Works

The application follows a simple retrieval-to-generation workflow:

### 1. PDF Processing

Uploaded PDFs are processed with **Docling** to extract their text and page information. The current implementation targets digital, text-based PDFs, so OCR is disabled.

### 2. Text Chunking and Embeddings

Extracted content is divided into chunks of roughly **400 tokens**, using a **50-token overlap** between neighboring chunks.

Each chunk is converted into a **384-dimensional vector embedding** using the `multi-qa-MiniLM-L6-cos-v1` model from Sentence Transformers.

### 3. Vector Search

The chunk embeddings, along with document and page metadata, are stored in **PostgreSQL with pgvector**.

When a user asks a question, the question is embedded using the same model. A cosine-similarity search then identifies the **top 5 relevant chunks** across the selected documents.

### 4. Answer Generation

The retrieved passages are supplied as context to the **Groq API**, using `llama-3.3-70b-versatile` by default.

The generated response is streamed to the Vue frontend through **Server-Sent Events (SSE)**, with document and page references included alongside the answer.

---

## Application Flow

### Document Ingestion

```text
PDF
 │
 ▼
Docling
 │
 ▼
Text + Page Extraction
 │
 ▼
Chunking
 │
 ▼
384-Dimensional Embeddings
 │
 ▼
PostgreSQL + pgvector
```

### Question Answering

```text
User Question
 │
 ▼
Question Embedding
 │
 ▼
Cosine Similarity Search
 │
 ▼
Top 5 Relevant Chunks
 │
 ▼
Context + Question
 │
 ▼
Groq LLM
 │
 ▼
Streaming Answer + Citations
```

---

## Main Features

- Upload and query multiple PDF documents
- Search across multiple documents using semantic similarity
- Select which documents should be considered for a question
- Store vectors and page metadata in PostgreSQL with pgvector
- Generate answers using an LLM through Groq
- Stream responses to the frontend using SSE
- Display document and page references with generated answers
- Process PDFs through Docling
- Vue-based web interface for document management and chat

---

## Technology Stack

### Backend

- **FastAPI** — API layer
- **PostgreSQL** — persistent data storage
- **pgvector** — vector similarity search
- **SQLAlchemy** — database interaction
- **Docling** — PDF parsing and text extraction
- **Sentence Transformers** — text embeddings
- **Groq API** — LLM-based response generation

### Frontend

- **Vue 3**
- **Vite**
- **JavaScript**

### Infrastructure

- **Docker / Docker Compose**
- PostgreSQL with pgvector

---

## Repository Layout

```text
VectorBrain/
│
├── backend/
│   ├── app/
│   │   ├── db/
│   │   ├── routers/
│   │   ├── services/
│   │   └── main.py
│   ├── Dockerfile
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   ├── public/
│   └── package.json
│
├── docker-compose.yml
├── README.md
└── .env.example
```

---

## Running the Project Locally

### 1. Clone the repository

```bash
git clone <repository-url>
cd VectorBrain
```

### 2. Set up environment variables

Create local environment files from the provided examples:

```bash
cp .env.example .env
cp backend/.env.example backend/.env
```

Add your own Groq API key and the database configuration to the appropriate environment file.

Example:

```env
DATABASE_URL=postgresql://vectorbrain:vectorbrain@db:5432/vectorbrain
GROQ_API_KEY=your_api_key
```

Never commit real API keys or `.env` files to the repository.

### 3. Start the backend and database

```bash
docker compose up --build -d
```

The backend runs on port **8000**, while PostgreSQL uses port **5432**.

### 4. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open the local Vite address shown in the terminal, normally:

```text
http://localhost:5173
```

If that port is occupied, Vite will select another available port.

---

## API Overview

### Upload a PDF

```http
POST /api/upload
```

The endpoint accepts a PDF through multipart form data and returns information such as the document ID, filename, number of pages, and generated chunk count.

### Chat

```http
POST /api/chat
```

A typical request contains a question:

```json
{
  "question": "Summarize this document"
}
```

A response contains the generated answer and associated source metadata:

```json
{
  "answer": "...",
  "sources": [
    {
      "filename": "sample.pdf",
      "page": 2
    }
  ]
}
```

The application also supports the streaming chat flow used by the frontend through Server-Sent Events.

---

## Current Constraints

- The embedding pipeline currently uses `multi-qa-MiniLM-L6-cos-v1`.
- Chunk size and overlap are fixed in the implementation.
- Authentication and authorization are not currently implemented.
- Documents are not isolated between different users.
- OCR is disabled, so scanned/image-only PDFs are outside the current target workflow.
- Groq API rate limits can affect frequent requests when using a free-tier account.

---

## Possible Future Extensions

Potential areas for further development include:

- User authentication and per-user document isolation
- Configurable chunking strategies
- OCR support for scanned PDFs
- Additional document formats
- Hybrid keyword and semantic retrieval
- Support for multiple embedding models
- Expanded conversation-history features
