<template>
  <div class="chat-workspace">
    <div class="message-list" ref="messageListRef">
      <!-- Slim inline hint (no banner): conversation starts directly -->
      <div v-if="messages.length === 0" class="chat-hint">
        <p v-if="documentsCount === 0">Upload a PDF with “Upload Documents” to start asking questions.</p>
        <p v-else>Ask a question about your documents to begin.</p>
      </div>

      <div
        v-for="msg in messages"
        :key="msg.id"
        class="row"
        :class="msg.role === 'user' ? 'row-user' : 'row-ai'"
      >
        <!-- Loading / typing indicator -->
        <div v-if="msg.isLoading" class="ai-card typing-card" aria-label="Assistant is typing">
          <div class="ai-head">
            <span class="ai-avatar" aria-hidden="true">VB</span>
            <span class="ai-name">VectorBrain</span>
          </div>
          <div class="typing-dots"><span></span><span></span><span></span></div>
        </div>

        <!-- Error bubble -->
        <div v-else-if="msg.isError" class="ai-card error-card">
          <div class="ai-head">
            <span class="ai-avatar" aria-hidden="true">VB</span>
            <span class="ai-name">VectorBrain</span>
          </div>
          <p class="error-text">{{ msg.content }}</p>
          <button class="retry-btn" @click="retry(msg)" aria-label="Retry this question">Retry</button>
        </div>

        <!-- User bubble -->
        <div v-else-if="msg.role === 'user'" class="user-col">
          <div class="user-bubble">{{ msg.content }}</div>
          <span v-if="msg.createdAt" class="stamp">{{ formatTime(msg.createdAt) }}</span>
        </div>

        <!-- AI answer card -->
        <div v-else class="ai-card">
          <div class="ai-head">
            <span class="ai-avatar" aria-hidden="true">VB</span>
            <span class="ai-name">VectorBrain</span>
            <span v-if="msg.createdAt" class="stamp">{{ formatTime(msg.createdAt) }}</span>
          </div>
          <div class="answer-body assistant-markdown" v-html="renderAnswer(msg)"></div>
          <div v-if="visibleSources(msg).length > 0" class="sources-box">
            <p class="sources-title">Sources</p>
            <ul class="sources-list">
              <li v-for="(name, idx) in visibleSources(msg)" :key="idx">
                {{ name }}
              </li>
            </ul>
          </div>
          <div v-if="msg.cached" class="cached-badge">Served from semantic cache</div>
        </div>
      </div>
    </div>

    <!-- Composer -->
    <div class="composer-zone">
      <div class="composer">
        <textarea
          id="chat-input"
          v-model="inputText"
          class="composer-input"
          placeholder="Ask a question about your documents..."
          rows="1"
          :disabled="isSending"
          @keydown="handleKeydown"
          @keydown.esc="inputText = ''"
          @input="autoResize"
          ref="textareaRef"
        ></textarea>
        <div class="composer-bar">
          <span class="scope-pill" :title="sourcesHint">{{ sourcesLabel }}</span>
          <button
            id="send-btn"
            class="send-btn"
            :class="{ 'is-loading': isSending }"
            :disabled="isSending || inputText.trim() === ''"
            @click="sendMessage()"
            aria-label="Send message"
          >
            <span v-if="isSending" class="spinner" aria-hidden="true"></span>
            <svg v-else viewBox="0 0 24 24" width="17" height="17" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round">
              <line x1="22" y1="2" x2="11" y2="13"></line>
              <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
            </svg>
          </button>
        </div>
      </div>
      <p class="composer-note">VectorBrain uses your selected documents to generate accurate, cited answers.</p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted } from 'vue';
import { sendMessageStream } from '../services/api.js';
import MarkdownIt from 'markdown-it';

const md = new MarkdownIt({
  html: false,    // disable raw HTML in source (XSS safety)
  breaks: true,   // convert \n to <br> inside paragraphs
  linkify: true,  // auto-link URLs
});

const props = defineProps({
  messages: {
    type: Array,
    required: true,
  },
  selectedIds: {
    type: Array,
    required: true,
  },
  notebookId: {
    type: [Number, null],
    default: null,
  },
  documentsCount: {
    type: Number,
    default: 0,
  },
});

const emit = defineEmits(['message-added', 'message-resolved', 'remove-message']);

const inputText = ref('');
const isSending = ref(false);
const messageListRef = ref(null);
const textareaRef = ref(null);

// Empty selection means "query across ALL documents" (backend treats
// document_ids null/empty as search-all), so label it honestly.
const sourcesLabel = computed(() => {
  if (props.documentsCount === 0) return 'No sources';
  if (props.selectedIds.length === 0) return 'All sources';
  return `${props.selectedIds.length} ${props.selectedIds.length === 1 ? 'source' : 'sources'}`;
});

const sourcesHint = computed(() => {
  if (props.documentsCount === 0) return 'Upload a PDF to add a source';
  if (props.selectedIds.length === 0) return 'No filter selected — searching across all documents';
  return 'Searching within the selected sources';
});

onMounted(() => {
  textareaRef.value?.focus();
});

function focusInput() {
  textareaRef.value?.focus();
}

defineExpose({ focusInput });

function handleKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}

function autoResize() {
  const el = textareaRef.value;
  if (!el) return;
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 150) + 'px';
}

async function scrollToBottom() {
  await nextTick();
  const list = messageListRef.value;
  if (list) list.scrollTop = list.scrollHeight;
}

function renderMarkdown(text) {
  if (!text) return '';
  return md.render(text);
}

// NOTE on citations: the backend prompt instructs the model to cite real
// "[filename, p. N]" metadata. The display transform below NEVER invents
// identity — a marker is restyled only when its (filename, page) pair matches
// the verified backend `sources` array exactly; anything else (or missing
// metadata) renders untouched. Filenames/pages always come from SOURCE data.
//
// Consistency: the model nondeterministically varies marker *syntax* (ASCII
// vs CJK brackets, "p." vs "P.", optional dot). The pattern below accepts all
// syntax variants but the verified-set gate is unchanged and exact, so every
// verified citation renders through the same chip component while fabricated
// markers still render as plain text.
function unescapeHtml(s) {
  return String(s)
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'");
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function renderAnswer(msg) {
  const html = renderMarkdown(msg.content);
  const src = Array.isArray(msg.sources) ? msg.sources : [];
  if (src.length === 0) return html;
  const verified = new Set(
    src
      .filter((s) => s && s.filename != null)
      .map((s) => `${s.filename}|||${Number(s.page)}`)
  );
  // Transform text segments only — never restyle code blocks/pre content.
  return html
    .split(/(<pre>.*?<\/pre>|<code>.*?<\/code>)/gs)
    .map((seg, i) => {
      if (i % 2 === 1) return seg;
      return seg.replace(/[\[【]([^<>\[\]【】]+?),\s*[pP]\.?\s*(\d+)\s*[\]】]/g, (marker, name, pg) => {
        const clean = unescapeHtml(name.trim());
        const page = Number(pg);
        if (!verified.has(`${clean}|||${page}`)) return marker;
        // Chip shows filename + compact page ref only (no brackets, no "p.").
        // Page stays verified metadata; full name is kept in the tooltip.
        const safe = escapeHtml(clean);
        return `<span class="cite" title="${safe}, page ${page}">${safe}, P-${page}</span>`;
      });
    })
    .join('');
}

// Sources list shows verified filenames only (no page numbers — those live
// next to the answer text). Entries without a filename are skipped, never
// fabricated.
function visibleSources(msg) {
  if (!Array.isArray(msg.sources)) return [];
  const names = [];
  for (const s of msg.sources) {
    if (s && s.filename && !names.includes(s.filename)) names.push(s.filename);
  }
  return names;
}
function formatTime(iso) {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    let h = d.getHours();
    const m = String(d.getMinutes()).padStart(2, '0');
    const ampm = h >= 12 ? 'PM' : 'AM';
    h = h % 12 || 12;
    return `${h}:${m} ${ampm}`;
  } catch {
    return '';
  }
}

async function sendMessage(questionOverride = null) {
  const question = questionOverride ?? inputText.value.trim();
  if (!question || isSending.value) return;

  if (!questionOverride) {
    inputText.value = '';
    if (textareaRef.value) textareaRef.value.style.height = 'auto';
  }

  // 1. Push user message
  const userMsgId = Date.now();
  emit('message-added', { id: userMsgId, role: 'user', content: question, createdAt: new Date().toISOString() });

  // 2. Push loading assistant placeholder
  const aiMsgId = Date.now() + 1;
  emit('message-added', { id: aiMsgId, role: 'assistant', content: '', isLoading: true, createdAt: new Date().toISOString() });

  isSending.value = true;
  await scrollToBottom();

  try {
    let fullContent = '';
    let isFirstToken = true;
    let isCachedHit = false;

    await sendMessageStream(
      question,
      props.notebookId,
      props.selectedIds,
      (token) => {
        fullContent += token;
        emit('message-resolved', {
          id: aiMsgId,
          content: fullContent,
          citations: [],
          isLoading: false,
          isError: false,
          cached: isCachedHit,
        });

        if (isFirstToken) {
          isFirstToken = false;
          scrollToBottom();
        }
      },
      (sources) => {
        const citations = sources.map(
          (s) => `${s.filename}, p.${s.page}`
        );
        emit('message-resolved', {
          id: aiMsgId,
          content: fullContent,
          citations,
          sources,
          isLoading: false,
          isError: false,
          cached: isCachedHit,
        });
      },
      (cachedVal) => {
        isCachedHit = cachedVal;
      }
    );
  } catch (err) {
    emit('message-resolved', {
      id: aiMsgId,
      content: err.message ?? 'Something went wrong. Please try again.',
      citations: [],
      isLoading: false,
      isError: true,
      question,
    });
  } finally {
    isSending.value = false;
    await scrollToBottom();
  }
}

function retry(msg) {
  emit('remove-message', msg.id);
  sendMessage(msg.question);
}
</script>

<style scoped>
.chat-workspace {
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  min-height: 0;
  background: transparent;
}

/* ── Message list ─────────────────────────────────────────────────── */
.message-list {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
  padding: 22px 26px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ── Slim inline hint (no banner) ───────────────────────────────────── */
.chat-hint {
  margin: auto;
  text-align: center;
  color: var(--color-text-inverse);
  font-size: var(--font-size-md);
  padding: 20px;
}

.chat-hint p {
  margin: 0;
}

/* ── Rows ─────────────────────────────────────────────────────────── */
.row {
  display: flex;
  width: 100%;
}

.row-user {
  justify-content: flex-end;
}

.row-ai {
  justify-content: flex-start;
}

.user-col {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  max-width: 75%;
}

.user-bubble {
  background: var(--accent-soft);
  color: var(--color-text-secondary);
  border: 1px solid #d5e2d3;
  border-radius: var(--radius-md);
  border-bottom-right-radius: 4px;
  padding: 11px 16px;
  font-size: var(--font-size-md);
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.stamp {
  font-size: var(--font-size-xs);
  color: var(--color-text-inverse);
}

/* ── AI card ──────────────────────────────────────────────────────── */
.ai-card {
  background: #fff;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-md);
  padding: 18px 22px;
  width: 100%;
  max-width: 900px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.ai-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--color-border);
}

.ai-avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--accent);
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.ai-name {
  font-size: var(--font-size-sm);
  font-weight: 700;
  color: var(--color-text-secondary);
}

.ai-head .stamp {
  margin-left: auto;
}

.answer-body {
  font-size: var(--font-size-md);
  line-height: 1.7;
  color: var(--color-text-primary);
  word-break: break-word;
  min-width: 0;
}

.sources-box {
  border-top: 1px solid var(--color-border);
  padding-top: 10px;
  margin-top: 2px;
}

.sources-title {
  margin: 0 0 6px 0;
  font-size: var(--font-size-sm);
  font-weight: 700;
  color: var(--color-text-secondary);
}

.sources-list {
  margin: 0;
  padding-left: 20px;
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
  line-height: 1.6;
}

/* Inline citation chip: compact rounded pill in a neutral warm-gray that is
   clearly distinct from normal text, browser selection blue, code blocks,
   and the green accent. Secondary to the answer, never button-like. */
.assistant-markdown :deep(.cite) {
  display: inline-block;
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: baseline;
  color: #6b6455;
  background: #f1efe9;
  border: 1px solid #e2ded4;
  border-radius: 999px;
  padding: 0 9px;
  font-size: 0.8em;
  font-weight: 600;
  line-height: 1.7;
  white-space: nowrap;
}

.cached-badge {
  align-self: flex-start;
  font-size: var(--font-size-xs);
  font-weight: 600;
  color: var(--accent-strong);
  background: var(--accent-soft);
  border: 1px solid #cfdfcc;
  border-radius: var(--radius-sm);
  padding: 3px 12px;
}

/* ── markdown-it output ───────────────────────────────────────────── */
.assistant-markdown :deep(h1),
.assistant-markdown :deep(h2),
.assistant-markdown :deep(h3),
.assistant-markdown :deep(h4) {
  margin: 16px 0 8px 0;
  color: var(--color-text-secondary);
  font-weight: 700;
  line-height: 1.35;
}
.assistant-markdown :deep(h1) { font-size: var(--font-size-3xl); }
.assistant-markdown :deep(h2) { font-size: var(--font-size-2xl); }
.assistant-markdown :deep(h3) { font-size: var(--font-size-xl); }
.assistant-markdown :deep(h4) { font-size: var(--font-size-lg); }

.assistant-markdown :deep(p) {
  margin: 0 0 12px 0;
  line-height: 1.75;
}

.assistant-markdown :deep(ul),
.assistant-markdown :deep(ol) {
  margin: 0 0 12px 0;
  padding-left: 22px;
}

.assistant-markdown :deep(li) {
  margin-bottom: 6px;
  line-height: 1.65;
}

.assistant-markdown :deep(li > ul),
.assistant-markdown :deep(li > ol) {
  margin: 4px 0 0 0;
}

.assistant-markdown :deep(strong) {
  color: var(--color-text-secondary);
  font-weight: 700;
}

.assistant-markdown :deep(em) {
  font-style: italic;
}

.assistant-markdown :deep(code) {
  background: var(--color-surface-muted);
  padding: 0.15em 0.4em;
  border-radius: 4px;
  font-size: 0.88em;
}

.assistant-markdown :deep(pre) {
  background: var(--color-surface-muted);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xs);
  padding: 12px 16px;
  overflow-x: auto;
  margin: 0 0 12px 0;
}

.assistant-markdown :deep(pre code) {
  background: none;
  padding: 0;
}

.assistant-markdown :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 0 0 12px 0;
  font-size: var(--font-size-sm);
  display: block;
  overflow-x: auto;
}

.assistant-markdown :deep(th),
.assistant-markdown :deep(td) {
  border: 1px solid var(--color-border);
  padding: 7px 12px;
  text-align: left;
}

.assistant-markdown :deep(th) {
  background: var(--color-surface-muted);
  font-weight: 700;
  color: var(--color-text-secondary);
}

/* ── Typing / error ───────────────────────────────────────────────── */
.typing-card {
  max-width: 220px;
}

.typing-dots {
  display: flex;
  gap: 6px;
  padding: 6px 2px;
}

.typing-dots span {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--accent);
  opacity: 0.5;
  animation: bounce var(--motion-normal) infinite alternate;
}

.typing-dots span:nth-child(2) { animation-delay: 100ms; }
.typing-dots span:nth-child(3) { animation-delay: 200ms; }

@keyframes bounce {
  0% { transform: translateY(0); opacity: 0.4; }
  100% { transform: translateY(-5px); opacity: 1; }
}

.error-card {
  border-color: var(--color-danger);
  max-width: 560px;
}

.error-text {
  margin: 0;
  color: var(--color-danger);
  font-size: var(--font-size-md);
}

.retry-btn {
  align-self: flex-start;
  background: #fff;
  color: var(--color-text-primary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: 6px 18px;
  font-family: inherit;
  font-size: var(--font-size-sm);
  font-weight: 600;
  cursor: pointer;
}

.retry-btn:hover {
  border-color: var(--accent);
  color: var(--accent-strong);
}

/* ── Composer ─────────────────────────────────────────────────────── */
.composer-zone {
  padding: 12px 26px 10px 26px;
  flex-shrink: 0;
}

.composer {
  background: #fff;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md);
  padding: 12px 14px 10px 18px;
  display: flex;
  flex-direction: column;
}

.composer:focus-within {
  border-color: var(--accent);
}

.composer-input {
  background: transparent;
  border: none;
  outline: none;
  resize: none;
  width: 100%;
  font-size: var(--font-size-md);
  line-height: 1.55;
  color: var(--color-text-primary);
  min-height: 26px;
  max-height: 150px;
  overflow-y: auto;
}

.composer-input::placeholder {
  color: var(--color-text-inverse);
}

.composer-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--color-border);
}

.scope-pill {
  font-size: var(--font-size-xs);
  font-weight: 600;
  color: var(--accent-strong);
  background: var(--accent-soft);
  border-radius: var(--radius-sm);
  padding: 4px 12px;
}

.send-btn {
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: var(--radius-sm);
  width: 38px;
  height: 38px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  flex-shrink: 0;
}

.send-btn:hover:not(:disabled) {
  background: var(--accent-strong);
}

.send-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.send-btn.is-loading {
  color: transparent;
}

.spinner {
  position: absolute;
  width: 15px;
  height: 15px;
  border: 2px solid rgba(255, 255, 255, 0.5);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin var(--motion-normal) linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.composer-note {
  margin: 7px 2px 0 2px;
  font-size: var(--font-size-xs);
  color: var(--color-text-inverse);
  text-align: center;
}
</style>
