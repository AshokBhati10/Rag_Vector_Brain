<template>
  <div class="doc-library" :class="{ 'is-collapsed': collapsed }">
    <div class="lib-header">
      <span class="lib-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" width="19" height="19" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
          <polyline points="14 2 14 8 20 8"></polyline>
          <line x1="16" y1="13" x2="8" y2="13"></line>
          <line x1="16" y1="17" x2="8" y2="17"></line>
        </svg>
      </span>
      <h2 v-if="!collapsed" class="lib-title">Documents{{ documents.length > 0 ? ` (${documents.length})` : '' }}</h2>
      <button
        class="icon-btn lib-collapse"
        @click="$emit('toggle-collapse')"
        :aria-label="collapsed ? 'Expand panel' : 'Collapse panel'"
        title="Toggle panel"
      >
        <svg viewBox="0 0 24 24" width="17" height="17" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
          <line x1="9" y1="3" x2="9" y2="21"></line>
        </svg>
      </button>
    </div>

    <button
      v-if="!collapsed"
      class="upload-primary"
      :disabled="isUploading"
      @click="fileInputRef.click()"
    >
      <span class="plus">+</span> Upload Documents
    </button>
    <button
      v-else
      class="upload-primary collapsed-upload"
      :disabled="isUploading"
      @click="fileInputRef.click()"
      aria-label="Upload documents"
      title="Upload documents"
    >
      <span class="plus">+</span>
    </button>

    <input
      ref="fileInputRef"
      type="file"
      accept=".pdf"
      multiple
      style="display: none"
      @change="onFileSelected"
    />

    <div v-if="errorMsg && !collapsed" class="error-banner" role="alert">
      <span>{{ errorMsg }}</span>
    </div>

    <div v-if="!collapsed && documents.length > 1" class="search-box">
      <svg viewBox="0 0 24 24" width="15" height="15" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="11" cy="11" r="8"></circle>
        <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
      </svg>
      <input v-model="searchQuery" type="text" placeholder="Search documents..." aria-label="Search documents" />
    </div>

    <div v-if="documents.length > 0 && !collapsed" class="select-all-row">
      <span>Select all</span>
      <button
        class="box"
        :class="{ 'is-on': isAllSelected }"
        role="checkbox"
        :aria-checked="isAllSelected"
        aria-label="Select all sources"
        @click="toggleSelectAll"
      >
        <svg v-if="isAllSelected" viewBox="0 0 24 24" width="12" height="12" stroke="currentColor" stroke-width="3.5" fill="none" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="20 6 9 17 4 12"></polyline>
        </svg>
      </button>
    </div>

    <div
      v-if="documents.length === 0 && pendingUploads.length === 0 && !collapsed"
      class="lib-empty"
      aria-label="No documents uploaded yet"
    >
      <div class="empty-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" width="30" height="30" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
          <polyline points="14 2 14 8 20 8"></polyline>
          <line x1="16" y1="13" x2="8" y2="13"></line>
          <line x1="16" y1="17" x2="8" y2="17"></line>
        </svg>
      </div>
      <p class="empty-title">No documents yet</p>
      <p class="empty-sub">Upload a PDF to get started.</p>
    </div>

    <div v-if="documents.length > 0 || pendingUploads.length > 0" class="doc-list">
      <div v-for="pending in pendingUploads" :key="pending.id" class="doc-card is-pending">
        <div v-if="!collapsed" class="doc-body">
          <div class="doc-name">{{ pending.name }}</div>
          <div class="doc-sub uploading">Uploading &amp; processing…</div>
        </div>
        <div class="shimmer"></div>
      </div>

      <div
        v-for="doc in filteredDocs"
        :key="doc.id"
        class="doc-card"
        :class="{ 'is-selected': selectedIds.includes(doc.id) }"
        tabindex="0"
      >
        <button
          class="box"
          :class="{ 'is-on': selectedIds.includes(doc.id) }"
          role="checkbox"
          :aria-checked="selectedIds.includes(doc.id)"
          aria-label="Select source"
          @click.stop="toggleSelect(doc.id)"
        >
          <svg v-if="selectedIds.includes(doc.id)" viewBox="0 0 24 24" width="12" height="12" stroke="currentColor" stroke-width="3.5" fill="none" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="20 6 9 17 4 12"></polyline>
          </svg>
        </button>

        <div class="pdf-badge" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
            <polyline points="14 2 14 8 20 8"></polyline>
          </svg>
        </div>

        <div v-if="!collapsed" class="doc-body">
          <div class="doc-name" :title="doc.filename">{{ doc.filename }}</div>
          <div class="doc-sub">{{ doc.total_pages }} pages • {{ formatSize(doc.file_size_kb) }}</div>
        </div>

        <div v-if="!collapsed" class="menu-wrap" @mouseleave="openMenuId = null">
          <button
            class="icon-btn menu-btn"
            aria-label="Document options"
            :aria-expanded="openMenuId === doc.id"
            @click.stop="openMenuId = openMenuId === doc.id ? null : doc.id"
            title="Document options"
          >
            <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true">
              <circle cx="12" cy="5" r="1.6"></circle>
              <circle cx="12" cy="12" r="1.6"></circle>
              <circle cx="12" cy="19" r="1.6"></circle>
            </svg>
          </button>
          <div v-if="openMenuId === doc.id" class="menu-pop" role="menu">
            <button role="menuitem" @click="toggleSelect(doc.id); openMenuId = null">
              {{ selectedIds.includes(doc.id) ? 'Deselect' : 'Select' }}
            </button>
            <button
              role="menuitem"
              class="menu-danger"
              :disabled="deletingIds.includes(doc.id)"
              @click="onDeleteDoc(doc.id); openMenuId = null"
            >
              {{ deletingIds.includes(doc.id) ? 'Deleting…' : 'Delete document' }}
            </button>
          </div>
        </div>
      </div>

      <div v-if="!collapsed && filteredDocs.length === 0 && documents.length > 0" class="no-match">
        No documents match “{{ searchQuery }}”.
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue';
import { uploadDocument, deleteDocument } from '../services/api.js';

const props = defineProps({
  documents: {
    type: Array,
    required: true,
  },
  selectedIds: {
    type: Array,
    required: true,
  },
  collapsed: {
    type: Boolean,
    default: false,
  },
  notebookId: {
    type: [Number, null],
    default: null,
  },
});

const emit = defineEmits([
  'document-added',
  'delete-document',
  'update:selectedIds',
  'toggle-collapse'
]);

const fileInputRef = ref(null);
const pendingUploads = ref([]);
const deletingIds = ref([]);
const errorMsg = ref('');
const searchQuery = ref('');
const openMenuId = ref(null);
let errorTimer = null;

const isUploading = computed(() => pendingUploads.value.length > 0);

const isAllSelected = computed(() => {
  if (props.documents.length === 0) return false;
  return props.documents.every(doc => props.selectedIds.includes(doc.id));
});

// Client-side name filter only — selection/upload logic unchanged.
const filteredDocs = computed(() => {
  const q = searchQuery.value.trim().toLowerCase();
  if (!q) return props.documents;
  return props.documents.filter(d => (d.filename || '').toLowerCase().includes(q));
});

function formatSize(kb) {
  if (!kb) return '0 KB';
  if (kb >= 1024) {
    return `${(kb / 1024).toFixed(1)} MB`;
  }
  return `${kb} KB`;
}

function showError(msg) {
  errorMsg.value = msg;
  clearTimeout(errorTimer);
  errorTimer = setTimeout(() => {
    errorMsg.value = '';
  }, 5000);
}

async function onFileSelected(event) {
  const files = Array.from(event.target.files || []);
  event.target.value = ''; // Reset
  if (files.length === 0) return;

  const uploadTasks = files.map(async (file) => {
    const tempId = 'pending-' + Math.random().toString(36).substr(2, 9);
    pendingUploads.value.push({ id: tempId, name: file.name });

    try {
      const result = await uploadDocument(file, props.notebookId);
      emit('document-added', result);

      // Auto-select newly uploaded documents
      const newSelected = [...props.selectedIds, result.id];
      emit('update:selectedIds', newSelected);
    } catch (err) {
      showError(err.message || `Upload failed for ${file.name}`);
    } finally {
      pendingUploads.value = pendingUploads.value.filter(p => p.id !== tempId);
    }
  });

  await Promise.allSettled(uploadTasks);
}

async function onDeleteDoc(docId) {
  deletingIds.value.push(docId);
  try {
    await deleteDocument(docId);
    emit('delete-document', docId);
    // Remove from selected list if it was selected
    const newSelected = props.selectedIds.filter(id => id !== docId);
    emit('update:selectedIds', newSelected);
  } catch (err) {
    showError(err.message || 'Delete failed');
  } finally {
    deletingIds.value = deletingIds.value.filter(id => id !== docId);
  }
}

function toggleSelect(docId) {
  const newSelected = props.selectedIds.includes(docId)
    ? props.selectedIds.filter(id => id !== docId)
    : [...props.selectedIds, docId];
  emit('update:selectedIds', newSelected);
}

function toggleSelectAll() {
  if (isAllSelected.value) {
    emit('update:selectedIds', []);
  } else {
    emit('update:selectedIds', props.documents.map(d => d.id));
  }
}
</script>

<style scoped>
.doc-library {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  background: #FFFEFB;
  border: 1px solid #E8E0D3;
  border-radius: 20px;
  box-shadow: 0 4px 20px rgba(70, 60, 45, 0.07);
  padding: 18px;
}

/* ── Panel header ─────────────────────────────────────────────────── */
.lib-header {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  flex-shrink: 0;
  padding: 0 4px;
  margin-bottom: 6px;
}

.lib-icon {
  color: var(--color-text-tertiary);
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.lib-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--color-text-secondary);
  flex-grow: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.icon-btn {
  background: transparent;
  color: var(--color-text-tertiary);
  border: 1px solid transparent;
  border-radius: var(--radius-xs);
  cursor: pointer;
  padding: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.icon-btn:hover {
  background: var(--color-surface-muted);
  color: var(--color-text-secondary);
  border-color: var(--color-border);
}

/* ── Upload ───────────────────────────────────────────────────────── */
.upload-primary {
  width: 100%;
  height: 46px;
  margin-top: 14px;
  background: #4F7456;
  color: #fff;
  border: none;
  border-radius: 12px;
  font-family: inherit;
  font-size: var(--font-size-md);
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  flex-shrink: 0;
  box-shadow: var(--shadow-sm);
}

.upload-primary:hover:not(:disabled) {
  background: #43634a;
}

.upload-primary:disabled {
  opacity: 0.65;
  cursor: wait;
}

.upload-primary .plus {
  font-size: 18px;
  line-height: 1;
  font-weight: 600;
}

.collapsed-upload {
  width: 40px;
  height: 40px;
  margin-top: 14px;
  border-radius: 12px;
  padding: 0;
}

/* ── Search ───────────────────────────────────────────────────────── */
.search-box {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  height: 40px;
  margin-top: 12px;
  background: #fff;
  border: 1px solid var(--color-border);
  border-radius: 12px;
  padding: 0 14px;
  color: var(--color-text-inverse);
  flex-shrink: 0;
}

.search-box input {
  border: none;
  background: transparent;
  outline: none;
  width: 100%;
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
}

.search-box input::placeholder {
  color: var(--color-text-inverse);
}

/* ── Select all ───────────────────────────────────────────────────── */
.select-all-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 12px;
  padding: 0 4px;
  color: var(--color-text-primary);
  font-size: var(--font-size-md);
  font-weight: 500;
  flex-shrink: 0;
}

/* Custom square checkbox (visual only — same toggle logic) */
.box {
  width: 20px;
  height: 20px;
  border-radius: 5px;
  border: 1.5px solid #cfc9ba;
  background: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  flex-shrink: 0;
  padding: 0;
  color: #fff;
}

.box:hover {
  border-color: var(--accent);
}

.box.is-on {
  background: var(--accent);
  border-color: var(--accent);
}

/* ── Empty state ──────────────────────────────────────────────────── */
.lib-empty {
  margin-top: 12px;
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface-tint);
  padding: 30px 16px;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.empty-icon {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: var(--color-surface-muted);
  color: var(--color-text-inverse);
  display: flex;
  align-items: center;
  justify-content: center;
}

.empty-title {
  margin: 8px 0 0 0;
  font-size: var(--font-size-md);
  font-weight: 600;
  color: var(--color-text-primary);
}

.empty-sub {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
}

/* ── Document list & cards ────────────────────────────────────────── */
.doc-list {
  display: flex;
  flex-direction: column;
  margin-top: 10px;
  overflow-y: auto;
  flex: 1;
  width: 100%;
  min-height: 0;
}

.doc-card {
  width: 100%;
  min-height: 72px;
  margin-bottom: 10px;
  background: #fff;
  border: 1px solid var(--color-border);
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(70, 60, 45, 0.05);
  padding: 12px 10px;
  display: flex;
  align-items: center;
  gap: 10px;
  position: relative;
  flex-shrink: 0;
}

.doc-card:last-child {
  margin-bottom: 2px;
}

.doc-card.is-selected {
  background: #fff;
  border: 1.5px solid var(--accent);
}

.pdf-badge {
  width: 40px;
  height: 40px;
  border-radius: 9px;
  background: #fbeae7;
  color: #b6503f;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.doc-body {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
  flex-grow: 1;
}

.doc-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.35;
}

.doc-sub {
  font-size: 13px;
  color: var(--color-text-tertiary);
}

.doc-sub.uploading {
  color: var(--accent-strong);
  font-weight: 600;
  animation: pulse 1.5s infinite;
}

.menu-wrap {
  position: relative;
  flex-shrink: 0;
  display: flex;
}

.menu-btn {
  color: var(--color-text-inverse);
}

.menu-pop {
  position: absolute;
  right: 0;
  top: calc(100% + 4px);
  background: #fff;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-md);
  min-width: 150px;
  z-index: 20;
  display: flex;
  flex-direction: column;
  padding: 4px;
}

.menu-pop button {
  background: transparent;
  border: none;
  text-align: left;
  font-family: inherit;
  font-size: var(--font-size-sm);
  font-weight: 500;
  color: var(--color-text-primary);
  padding: 8px 12px;
  border-radius: var(--radius-xs);
  cursor: pointer;
}

.menu-pop button:hover:not(:disabled) {
  background: var(--color-surface-muted);
}

.menu-pop .menu-danger {
  color: var(--color-danger);
}

.menu-pop .menu-danger:hover:not(:disabled) {
  background: var(--color-danger-soft);
}

.no-match {
  text-align: center;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-sm);
  padding: 12px;
}

.is-pending {
  overflow: hidden;
}

.shimmer {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: linear-gradient(90deg, transparent 25%, rgba(74, 107, 79, 0.08) 50%, transparent 75%);
  background-size: 200% 100%;
  animation: shimmer var(--motion-normal) infinite;
  pointer-events: none;
}

@keyframes shimmer {
  0%   { background-position: -200% 0; }
  100% { background-position:  200% 0; }
}

@keyframes pulse {
  0%, 100% { opacity: 0.6; }
  50% { opacity: 1; }
}

.mini-spinner {
  width: 13px;
  height: 13px;
  border: 2px solid var(--color-border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.error-banner {
  margin-top: 12px;
  background: var(--color-danger-soft);
  border: 1px solid var(--color-danger);
  border-radius: var(--radius-sm);
  padding: 8px 12px;
  font-size: var(--font-size-sm);
  color: var(--color-danger);
  flex-shrink: 0;
}

/* ── Collapsed rail ───────────────────────────────────────────────── */
.doc-library.is-collapsed {
  padding: 18px 8px;
  align-items: center;
}

.doc-library.is-collapsed .lib-header {
  justify-content: center;
  padding: 0;
}

.doc-library.is-collapsed .doc-card {
  justify-content: center;
  padding: 12px 6px;
}
</style>
