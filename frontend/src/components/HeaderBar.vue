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
      <button class="new-nb-btn" @click="promptCreateNotebook" title="Create a new notebook">
        <span class="plus-icon" aria-hidden="true">+</span> New Notebook
      </button>
    </nav>

    <div class="top-spacer">
      <label v-if="notebooks.length > 0" class="nb-label" for="nb-select">Recent Notebooks</label>
      <select
        v-if="notebooks.length > 0"
        id="nb-select"
        ref="notebookSelectRef"
        class="nb-select"
        :value="currentNotebookId"
        aria-label="Select notebook"
        title="Select notebook"
        @change="$emit('select-notebook', Number($event.target.value))"
      >
        <option v-for="nb in notebooks" :key="nb.id" :value="nb.id">
          {{ nb.name }}
        </option>
      </select>
      <span v-if="username" class="user-name" :title="`Logged in as ${username}`">{{ username }}</span>
      <button v-if="username" class="logout-btn" @click="$emit('logout')" title="Log out">
        Log out
      </button>
    </div>
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
  username: {
    type: String,
    default: '',
  },
});

const emit = defineEmits(['select-notebook', 'create-notebook', 'logout', 'new-chat', 'nav-chat', 'nav-notebook', 'nav-documents']);

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
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
}

.nb-label {
  font-size: var(--font-size-xs);
  font-weight: 600;
  color: var(--color-text-tertiary);
  white-space: nowrap;
}

.nb-select {
  height: 36px;
  max-width: 170px;
  border: 1px solid var(--color-border);
  border-radius: 9px;
  background: #fff;
  color: var(--color-text-primary);
  font-family: inherit;
  font-size: var(--font-size-sm);
  font-weight: 600;
  padding: 0 8px;
  cursor: pointer;
  outline: none;
}

.nb-select:focus {
  border-color: var(--accent);
}

.user-name {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-text-secondary);
  max-width: 140px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.logout-btn {
  height: 36px;
  padding: 0 14px;
  border: 1px solid var(--color-border);
  border-radius: 9px;
  background: #fff;
  color: var(--color-text-primary);
  font-family: inherit;
  font-size: var(--font-size-sm);
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}

.logout-btn:hover {
  border-color: var(--accent);
  color: var(--accent-strong);
}
</style>
