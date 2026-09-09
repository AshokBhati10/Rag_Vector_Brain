<template>
  <div class="app-container">
    <HeaderBar
      ref="headerRef"
      :notebooks="notebooks"
      :currentNotebookId="currentNotebookId"
      @select-notebook="handleSelectNotebook"
      @create-notebook="handleCreateNotebook"
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
import {
  fetchNotebooks,
  createNotebook,
  fetchDocuments,
  fetchMessages
} from './services/api.js';

const appRef = ref(null);
const headerRef = ref(null);
const chatRef = ref(null);
const sidebarCollapsed = ref(false);

// State
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
  await loadNotebooks();
});

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown);
});

// Load Notebooks & Bootstrap
async function loadNotebooks() {
  try {
    const nbs = await fetchNotebooks();
    notebooks.value = nbs;
    if (nbs.length === 0) {
      // Auto-create a default notebook if none exist
      const defaultNb = await createNotebook('My Notebook');
      notebooks.value = [defaultNb];
      currentNotebookId.value = defaultNb.id;
    } else {
      currentNotebookId.value = nbs[0].id;
    }
  } catch (err) {
    console.error('Error loading notebooks:', err);
  }
}

// Watch current notebook changes to hydrate state
watch(currentNotebookId, async (newId) => {
  if (newId !== null) {
    await hydrateNotebook(newId);
  }
});

async function hydrateNotebook(notebookId) {
  try {
    const docs = await fetchDocuments(notebookId);
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
  } catch (err) {
    console.error('Error hydrating notebook:', err);
  }
}

// Handlers
async function handleSelectNotebook(id) {
  currentNotebookId.value = id;
}

async function handleCreateNotebook(name) {
  try {
    const newNb = await createNotebook(name);
    notebooks.value.push(newNb);
    currentNotebookId.value = newNb.id;
  } catch (err) {
    alert('Failed to create notebook: ' + err.message);
  }
}

function handleDocumentAdded(doc) {
  documents.value.push(doc);
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
