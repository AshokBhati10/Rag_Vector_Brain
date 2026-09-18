<template>
  <div v-if="authLoading" class="auth-loading">Loading VectorBrain…</div>
  <LoginView v-else-if="!currentUser" @authenticated="handleAuthenticated" />
  <div v-else class="app-container">
    <HeaderBar
      ref="headerRef"
      :notebooks="notebooks"
      :currentNotebookId="currentNotebookId"
      :username="currentUser.username"
      @select-notebook="handleSelectNotebook"
      @create-notebook="handleCreateNotebook"
      @logout="handleLogout"
      @new-chat="handleNewChat"
      @nav-chat="handleNavChat"
      @nav-notebook="handleNavNotebook"
      @nav-documents="handleNavDocuments"
    />

    <div class="app-layout" ref="appRef">
      <aside class="sidebar" :class="{ 'is-collapsed': sidebarCollapsed }">
        <DocumentManager
          :documents="documents"
          v-model:selectedIds="selectedDocumentIds"
          :collapsed="sidebarCollapsed"
          :notebookId="currentNotebookId"
          @document-added="handleDocumentAdded"
          @delete-document="handleDelete"
          @toggle-collapse="sidebarCollapsed = !sidebarCollapsed"
        />
      </aside>
      <main class="chat-main">
        <ChatInterface
          ref="chatRef"
          :messages="messages"
          :selectedIds="selectedDocumentIds"
          :notebookId="currentNotebookId"
          :documents-count="documents.length"
          @message-added="handleMessageAdded"
          @message-resolved="handleMessageResolved"
          @remove-message="handleRemoveMessage"
        />
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue';
import HeaderBar from './components/HeaderBar.vue';
import DocumentManager from './components/DocumentManager.vue';
import ChatInterface from './components/ChatInterface.vue';
import LoginView from './components/Login.vue';
import {
  fetchNotebooks,
  createNotebook,
  fetchDocuments,
  fetchMessages,
  getMe,
  logoutUser
} from './services/api.js';

const appRef = ref(null);
const headerRef = ref(null);
const chatRef = ref(null);
const sidebarCollapsed = ref(false);

// State
const currentUser = ref(null);
const authLoading = ref(true);
const notebooks = ref([]);
const currentNotebookId = ref(null);
const documents = ref([]);
const messages = ref([]);
const selectedDocumentIds = ref([]);

// Keyboard focus trap
function handleKeydown(e) {
  if (e.key === 'Tab' && appRef.value) {
    const focusableElements = appRef.value.querySelectorAll(
      'a[href], button, textarea, input, select, [tabindex]:not([tabindex="-1"])'
    );
    if (focusableElements.length === 0) return;

    const first = focusableElements[0];
    const last = focusableElements[focusableElements.length - 1];

    if (e.shiftKey) {
      if (document.activeElement === first) {
        last.focus();
        e.preventDefault();
      }
    } else {
      if (document.activeElement === last) {
        first.focus();
        e.preventDefault();
      }
    }
  }
}

// Lifecycle
onMounted(async () => {
  document.addEventListener('keydown', handleKeydown);
  try {
    const me = await getMe();
    if (me) {
      currentUser.value = me;
      await loadNotebooks();
    }
  } catch (err) {
    console.error('Error checking session:', err);
  } finally {
    authLoading.value = false;
  }
});

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown);
  stopPolling();
});

// Auth
async function handleAuthenticated(user) {
  currentUser.value = user;
  await loadNotebooks();
}

function clearState() {
  stopPolling();
  notebooks.value = [];
  currentNotebookId.value = null;
  documents.value = [];
  messages.value = [];
  selectedDocumentIds.value = [];
}

// Background-ingestion status polling (RabbitMQ + Celery pipeline).
// After an upload returns, the document sits in "processing" until a worker
// marks it completed/failed. We simply re-read GET /documents every few
// seconds — no websocket/event system needed.
let pollTimer = null;
let pollTries = 0;
const POLL_INTERVAL_MS = 3000;
const POLL_MAX_TRIES = 100; // ~5 minutes, then stop quietly

function isTerminalStatus(doc) {
  return !doc || doc.status === 'completed' || doc.status === 'failed' || !doc.status;
}

function stopPolling() {
  if (pollTimer !== null) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  pollTries = 0;
}

function maybePollProcessing() {
  stopPolling();
  if (!documents.value.some((d) => !isTerminalStatus(d))) return;
  pollTimer = setInterval(async () => {
    const nbId = currentNotebookId.value;
    if (nbId === null) {
      stopPolling();
      return;
    }
    try {
      const fresh = await fetchDocuments(nbId);
      if (!Array.isArray(fresh)) return;
      // Notebook switched mid-poll, or a stale empty read: keep local state.
      if (nbId !== currentNotebookId.value) return;
      if (fresh.length === 0 && documents.value.length > 0) return;
      documents.value = fresh;
      const ids = new Set(fresh.map((d) => d.id));
      selectedDocumentIds.value = selectedDocumentIds.value.filter((id) => ids.has(id));
      pollTries += 1;
      if (pollTries >= POLL_MAX_TRIES || fresh.every(isTerminalStatus)) {
        stopPolling();
      }
    } catch (err) {
      if (err.status === 401) {
        stopPolling();
        goToLogin();
      }
    }
  }, POLL_INTERVAL_MS);
}

function goToLogin() {
  clearState();
  currentUser.value = null;
}

async function handleLogout() {
  try {
    await logoutUser();
  } catch (err) {
    console.error('Error logging out:', err);
  } finally {
    goToLogin();
  }
}

// Per-browser notebook memory (NOT a security mechanism — the server always
// re-validates ownership; a stored id that isn't in the user's own list is
// ignored). Keyed per username so two accounts sharing one browser never
// restore each other's selection.
function notebookStorageKey() {
  return `vectorbrain.notebookId:${currentUser.value?.username ?? 'anon'}`;
}

function readStoredNotebookId() {
  try {
    const raw = localStorage.getItem(notebookStorageKey());
    if (!raw) return null;
    const id = Number(raw);
    return Number.isInteger(id) ? id : null;
  } catch {
    return null;
  }
}

function storeNotebookId(id) {
  try {
    localStorage.setItem(notebookStorageKey(), String(id));
  } catch {
    // storage unavailable — app still works for this session
  }
}

// Load Notebooks & Bootstrap
// The API already scopes notebooks to the logged-in user, so selecting from
// this list can never leak another user's data. A fresh account gets an
// auto-created "My Notebook" (empty chat, no documents).
async function loadNotebooks() {
  try {
    const nbs = await fetchNotebooks();
    notebooks.value = nbs;
    if (nbs.length === 0) {
      // Auto-create a default notebook if none exist
      const defaultNb = await createNotebook('My Notebook');
      notebooks.value = [defaultNb];
      currentNotebookId.value = defaultNb.id;
      return;
    }
    // Restore the browser's last selection only if it is still owned.
    const storedId = readStoredNotebookId();
    if (storedId !== null && nbs.some((n) => n.id === storedId)) {
      currentNotebookId.value = storedId;
    } else {
      currentNotebookId.value = nbs[0].id;
    }
  } catch (err) {
    if (err.status === 401) {
      goToLogin();
      return;
    }
    console.error('Error loading notebooks:', err);
  }
}

// Immediately drop the previous notebook's documents/messages so a switch
// can never flash stale data while the new notebook hydrates.
function beginNotebookSwitch() {
  stopPolling();
  documents.value = [];
  messages.value = [];
  selectedDocumentIds.value = [];
}

// Watch current notebook changes to hydrate state
watch(currentNotebookId, async (newId) => {
  if (newId !== null) {
    storeNotebookId(newId);
    await hydrateNotebook(newId);
  }
});

async function hydrateNotebook(notebookId) {
  try {
    const docs = await fetchDocuments(notebookId);
    // Guard: never replace good state with a malformed payload.
    if (!Array.isArray(docs)) return;
    documents.value = docs;
    // Auto-select all documents on initial load
    selectedDocumentIds.value = docs.map(d => d.id);

    const msgs = await fetchMessages(notebookId);
    messages.value = msgs.map(m => ({
      id: m.id,
      role: m.role,
      content: m.content,
      citations: m.sources.map(s => `${s.filename}, p.${s.page}`),
      sources: m.sources,
      createdAt: m.created_at ?? null,
      isLoading: false,
      isError: false
    }));
    // If we landed (e.g. after refresh) while a worker is still ingesting,
    // resume polling so the row flips to Completed/Failed on its own.
    maybePollProcessing();
  } catch (err) {
    if (err.status === 401) {
      goToLogin();
      return;
    }
    console.error('Error hydrating notebook:', err);
  }
}

// Handlers
async function handleSelectNotebook(id) {
  if (id == null || id === currentNotebookId.value) return;
  beginNotebookSwitch();
  currentNotebookId.value = id;
}

async function handleCreateNotebook(name) {
  try {
    const newNb = await createNotebook(name);
    if (!notebooks.value.some((n) => n.id === newNb.id)) {
      notebooks.value.push(newNb);
    }
    beginNotebookSwitch();
    currentNotebookId.value = newNb.id;
  } catch (err) {
    if (err.status === 401) {
      goToLogin();
      return;
    }
    alert('Failed to create notebook: ' + err.message);
  }
}

async function handleDocumentAdded(doc) {
  // 1. Optimistic update: show the new document immediately. Uploads now
  // return { status: 'processing' } (heavy work happens in Celery workers),
  // so the row first appears with a Processing badge until polling below
  // observes the terminal completed/failed state from the server.
  // Dedupe by id so retries/double-emits can't create duplicates.
  if (doc && doc.id != null) {
    const normalized = {
      ...doc,
      total_pages: doc.total_pages ?? 0,
      file_size_kb: doc.file_size_kb ?? 0,
      status: doc.status ?? 'completed',
      error_message: doc.error_message ?? null,
    };
    if (!documents.value.some((d) => d.id === doc.id)) {
      documents.value.push(normalized);
    }
    if (!selectedDocumentIds.value.includes(doc.id)) {
      selectedDocumentIds.value = [...selectedDocumentIds.value, doc.id];
    }
  }
  // 2. Reconcile with the authoritative server list (bypasses
  // browser/Cloudflare HTTP cache via cache:'no-store' in api.js).
  // On any failure — or a stale empty read right after a successful
  // write — keep the existing + optimistic state instead of wiping
  // the list to "No documents yet".
  try {
    const fresh = await fetchDocuments(currentNotebookId.value);
    if (!Array.isArray(fresh)) return;
    if (fresh.length === 0 && documents.value.length > 0) {
      console.warn('Post-upload refresh returned empty; keeping existing documents.');
      return;
    }
    const seen = new Set(fresh.map((d) => d.id));
    const merged = [...fresh];
    for (const d of documents.value) {
      if (doc && d.id === doc.id && !seen.has(d.id)) {
        merged.push(d); // read-your-write lag: keep optimistic row
      }
    }
    documents.value = merged;
    // Preserve selection; ensure the newly uploaded doc stays selected.
    const ids = new Set(merged.map((d) => d.id));
    const kept = selectedDocumentIds.value.filter((id) => ids.has(id));
    if (doc && doc.id != null && ids.has(doc.id) && !kept.includes(doc.id)) {
      kept.push(doc.id);
    }
    selectedDocumentIds.value = kept;
  } catch (err) {
    if (err.status === 401) {
      goToLogin();
      return;
    }
    console.error('Error refreshing documents after upload:', err);
  }
  // 3. If the new row is still processing, poll until the worker finishes.
  maybePollProcessing();
}

function handleDelete(id) {
  documents.value = documents.value.filter((d) => d.id !== id);
}

function handleMessageAdded(msg) {
  messages.value.push(msg);
}

function handleMessageResolved(update) {
  const msg = messages.value.find((m) => m.id === update.id);
  if (!msg) return;
  Object.assign(msg, update);
}

function handleRemoveMessage(id) {
  messages.value = messages.value.filter((m) => m.id !== id);
}

// "New Chat" clears the local chat view only. Persisted backend history
// is left untouched and will re-hydrate on notebook switch/refresh.
function handleNewChat() {
  messages.value = [];
}

// Top-nav shortcuts (UI only — no behavior changes)
function handleNavChat() {
  chatRef.value?.focusInput();
}

function handleNavNotebook() {
  headerRef.value?.focusNotebookSelect();
}

function handleNavDocuments() {
  sidebarCollapsed.value = false;
}
</script>

<style scoped>
.auth-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  width: 100%;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-md);
}

.app-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  overflow: hidden;
  background-color: var(--color-surface-base);
}

.app-layout {
  display: flex;
  flex: 1;
  min-height: 0;
  width: 100%;
  gap: 14px;
  padding: 14px 18px 18px 18px;
}

.sidebar {
  width: 330px;
  flex-shrink: 0;
  /* Transparent wrapper: the Document Library panel paints its own
     18px card surface, border and shadow. */
  background: transparent;
  border: none;
  box-shadow: none;
  transition: width var(--motion-normal) ease;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.sidebar.is-collapsed {
  width: 64px;
}

.chat-main {
  flex-grow: 1;
  background-color: var(--color-surface-raised);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md);
  display: flex;
  flex-direction: column;
  position: relative;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}
</style>
