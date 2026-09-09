<template>
  <header class="topbar">
    <div class="brand">
      <div class="brand-mark" aria-hidden="true">
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 2a10 10 0 0 1 10 10c0 5.523-4.477 10-10 10S2 17.523 2 12 6.477 2 12 2z"></path>
          <path d="M12 6a6 6 0 0 1 6 6c0 3.314-2.686 6-6 6s-6-2.686-6-6 2.686-6 6-6z"></path>
          <circle cx="12" cy="12" r="2"></circle>
        </svg>
      </div>
      <div class="brand-text">
        <h1 class="brand-name">VectorBrain</h1>
        <p class="brand-tagline">Your Documents. Smarter Answers.</p>
      </div>
    </div>

    <nav class="topnav" aria-label="Primary">
      <button class="nav-item is-active" @click="$emit('nav-chat')">
        <svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
        </svg>
        Chat
      </button>
      <button class="nav-item" @click="$emit('nav-notebook')">
        <svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round">
          <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"></path>
          <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"></path>
        </svg>
        My Notebook
      </button>
      <button class="nav-item" @click="$emit('nav-documents')">
        <svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
          <polyline points="14 2 14 8 20 8"></polyline>
        </svg>
        Documents
      </button>
      <span class="nav-divider" aria-hidden="true"></span>
      <button class="new-nb-btn" @click="promptCreateNotebook" title="Create a new notebook">
        <span class="plus-icon" aria-hidden="true">+</span> New Notebook
      </button>
    </nav>

    <!-- Right column intentionally empty: the single centered nav is the
         only control group in the header. Notebook/new-chat handlers stay
         wired in script (functionality preserved) but render nothing here. -->
    <div class="top-spacer" aria-hidden="true"></div>
  </header>
</template>

<script setup>
import { ref } from 'vue';

defineProps({
  notebooks: {
    type: Array,
    required: true,
  },
  currentNotebookId: {
    type: [Number, null],
    required: true,
  },
});

const emit = defineEmits(['select-notebook', 'create-notebook', 'new-chat', 'nav-chat', 'nav-notebook', 'nav-documents']);

const notebookSelectRef = ref(null);

function focusNotebookSelect() {
  notebookSelectRef.value?.focus();
}

function promptCreateNotebook() {
  const name = prompt('Enter a name for the new notebook:');
  if (name && name.trim()) {
    emit('create-notebook', name.trim());
  }
}

defineExpose({ focusNotebookSelect });
</script>

<style scoped>
.topbar {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  padding: 10px 22px;
  background: var(--color-surface-raised);
  border-bottom: 1px solid var(--color-border);
  min-height: 74px;
  flex-shrink: 0;
}

.brand {
  justify-self: start;
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.brand-mark {
  width: 38px;
  height: 38px;
  border-radius: 12px;
  background: var(--accent-soft);
  color: var(--accent-strong);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.brand-name {
  margin: 0;
  font-size: 19px;
  font-weight: 700;
  color: var(--color-text-secondary);
  line-height: 1.2;
  white-space: nowrap;
}

.brand-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.brand-tagline {
  margin: 0;
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  white-space: nowrap;
}

.topnav {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  justify-self: center;
  height: 46px;
  background: #FFFFFF;
  border: 1px solid #E5DDCE;
  border-radius: 14px;
  box-shadow: 0 2px 10px rgba(70, 60, 45, 0.05);
  padding: 0 6px;
  white-space: nowrap;
}

.nav-item {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  border: none;
  background: transparent;
  color: var(--color-text-primary);
  font-family: inherit;
  font-size: 14px;
  font-weight: 600;
  height: 36px;
  padding: 0 18px;
  border-radius: 8px;
  cursor: pointer;
  white-space: nowrap;
}

.nav-item:hover {
  color: var(--color-text-secondary);
  background: var(--color-surface-tint);
}

.nav-item.is-active {
  background: #E8F0E5;
  color: #355E3B;
}

.nav-divider {
  width: 1px;
  align-self: stretch;
  margin: 8px 2px;
  background: var(--color-border);
  flex-shrink: 0;
}

.new-nb-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 16px;
  border: none;
  border-radius: 9px;
  background: #4F7456;
  color: #fff;
  font-family: inherit;
  font-size: var(--font-size-sm);
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}

.new-nb-btn:hover {
  background: #43634a;
}

.new-nb-btn .plus-icon {
  font-size: 15px;
  line-height: 1;
}

.top-spacer {
  justify-self: end;
  min-width: 0;
}
</style>
