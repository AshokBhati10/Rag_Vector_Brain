const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

/**
 * Upload a PDF file to the backend under a specific notebook.
 * @param {File} file
 * @param {number|null} notebookId
 * @returns {Promise<{ id: number, filename: string, total_pages: number, chunk_count: number }>}
 */
export async function uploadDocument(file, notebookId = null) {
  const form = new FormData();
  form.append('file', file);
  if (notebookId !== null) {
    form.append('notebook_id', notebookId.toString());
  }

  const response = await fetch(`${BASE_URL}/api/upload`, {
    method: 'POST',
    body: form,
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Upload failed' }));
    throw new Error(err.detail ?? 'Upload failed');
  }

  return response.json();
}

/**
 * Fetch all documents, optionally filtered by notebookId.
 * @param {number|null} notebookId
 * @returns {Promise<Array<{ id: number, filename: string, total_pages: number, file_size_kb: number, notebook_id: number }>>}
 */
export async function fetchDocuments(notebookId = null) {
  let url = `${BASE_URL}/api/documents`;
  if (notebookId !== null) {
    url += `?notebook_id=${notebookId}`;
  }
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error('Failed to fetch documents');
  }
  return response.json();
}

/**
 * Delete a document by ID.
 * @param {number} docId
 */
export async function deleteDocument(docId) {
  const response = await fetch(`${BASE_URL}/api/documents/${docId}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Failed to delete document' }));
    throw new Error(err.detail ?? 'Failed to delete document');
  }
  return response.json();
}

/**
 * Fetch all chat messages, optionally filtered by notebookId.
 * @param {number|null} notebookId
 */
export async function fetchMessages(notebookId = null) {
  let url = `${BASE_URL}/api/messages`;
  if (notebookId !== null) {
    url += `?notebook_id=${notebookId}`;
  }
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error('Failed to fetch messages');
  }
  return response.json();
}

/**
 * Fetch all notebooks.
 */
export async function fetchNotebooks() {
  const response = await fetch(`${BASE_URL}/api/notebooks`);
  if (!response.ok) {
    throw new Error('Failed to fetch notebooks');
  }
  return response.json();
}

/**
 * Create a new notebook.
 * @param {string} name
 */
export async function createNotebook(name) {
  const response = await fetch(`${BASE_URL}/api/notebooks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Failed to create notebook' }));
    throw new Error(err.detail ?? 'Failed to create notebook');
  }
  return response.json();
}

/**
 * Send a chat question to the backend streaming RAG endpoint.
 * @param {string} question
 * @param {number|null} notebookId
 * @param {Array<number>|null} documentIds
 * @param {Function} onToken - called for every text chunk (token)
 * @param {Function} onSources - called when the final sources event arrives
 * @param {Function} onCached - called when the cache status event arrives
 */
export async function sendMessageStream(question, notebookId = null, documentIds = null, onToken, onSources, onCached = () => {}) {
  const response = await fetch(`${BASE_URL}/api/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question,
      notebook_id: notebookId,
      document_ids: documentIds && documentIds.length > 0 ? documentIds : null
    }),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Chat failed' }));
    throw new Error(err.detail ?? 'Chat failed');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    
    // The last line might be incomplete, so keep it in the buffer
    buffer = lines.pop() ?? '';
    
    let currentEvent = 'message';
    for (const line of lines) {
      if (line.startsWith('event: ')) {
        currentEvent = line.slice(7).trim();
      } else if (line.startsWith('data: ')) {
        const data = line.slice(6);
        if (currentEvent === 'cached') {
          onCached(data === 'true');
        } else if (currentEvent === 'sources') {
          onSources(JSON.parse(data));
        } else if (currentEvent === 'error') {
          throw new Error(data);
        } else {
          onToken(decodeURIComponent(data));
        }
      } else if (line === '') {
        currentEvent = 'message'; // reset after blank line
      }
    }
  }
}
