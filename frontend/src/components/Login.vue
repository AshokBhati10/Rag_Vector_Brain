<template>
  <div class="login-wrap">
    <form class="login-card" @submit.prevent="onSubmit">
      <div class="login-brand">
        <div class="brand-mark" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 2a10 10 0 0 1 10 10c0 5.523-4.477 10-10 10S2 17.523 2 12 6.477 2 12 2z"></path>
            <path d="M12 6a6 6 0 0 1 6 6c0 3.314-2.686 6-6 6s-6-2.686-6-6 2.686-6 6-6z"></path>
            <circle cx="12" cy="12" r="2"></circle>
          </svg>
        </div>
        <h1 class="login-title">VectorBrain</h1>
        <p class="login-sub">{{ isSignup ? 'Create an account to get started.' : 'Log in to access your notebooks.' }}</p>
      </div>

      <label class="login-label" for="login-username">Username</label>
      <input
        id="login-username"
        v-model="username"
        class="login-input"
        type="text"
        autocomplete="username"
        :disabled="isLoading"
        autofocus
      />

      <label class="login-label" for="login-password">Password</label>
      <input
        id="login-password"
        v-model="password"
        class="login-input"
        type="password"
        :autocomplete="isSignup ? 'new-password' : 'current-password'"
        :disabled="isLoading"
      />

      <template v-if="isSignup">
        <label class="login-label" for="login-confirm">Confirm password</label>
        <input
          id="login-confirm"
          v-model="confirmPassword"
          class="login-input"
          type="password"
          autocomplete="new-password"
          :disabled="isLoading"
        />
      </template>

      <div v-if="errorMsg" class="login-error" role="alert">{{ errorMsg }}</div>

      <button class="login-btn" type="submit" :disabled="isLoading">
        {{ isLoading ? (isSignup ? 'Creating account…' : 'Logging in…') : (isSignup ? 'Create account' : 'Log in') }}
      </button>

      <button class="login-switch" type="button" :disabled="isLoading" @click="toggleMode">
        {{ isSignup ? 'Already have an account? Log in' : "New here? Create account" }}
      </button>
    </form>
  </div>
</template>

<script setup>
import { ref } from 'vue';
import { loginUser, registerUser } from '../services/api.js';

const emit = defineEmits(['authenticated']);

const isSignup = ref(false);
const username = ref('');
const password = ref('');
const confirmPassword = ref('');
const errorMsg = ref('');
const isLoading = ref(false);

function toggleMode() {
  isSignup.value = !isSignup.value;
  errorMsg.value = '';
  confirmPassword.value = '';
}

async function onSubmit() {
  errorMsg.value = '';
  if (!username.value.trim() || !password.value) {
    errorMsg.value = 'Please enter your username and password.';
    return;
  }
  if (isSignup.value && password.value !== confirmPassword.value) {
    errorMsg.value = 'Passwords do not match.';
    return;
  }
  isLoading.value = true;
  try {
    const user = isSignup.value
      ? await registerUser(username.value.trim(), password.value)
      : await loginUser(username.value.trim(), password.value);
    emit('authenticated', user);
  } catch (err) {
    errorMsg.value = err.message || (isSignup.value ? 'Registration failed. Please try again.' : 'Login failed. Please try again.');
  } finally {
    isLoading.value = false;
  }
}
</script>

<style scoped>
.login-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  width: 100%;
  background-color: var(--color-surface-base);
  padding: 20px;
}

.login-card {
  width: 100%;
  max-width: 360px;
  background: #fff;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md);
  padding: 28px 26px;
  display: flex;
  flex-direction: column;
}

.login-brand {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  margin-bottom: 18px;
}

.brand-mark {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  background: var(--accent-soft);
  color: var(--accent-strong);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 10px;
}

.login-title {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--color-text-secondary);
}

.login-sub {
  margin: 4px 0 0 0;
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
}

.login-label {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 10px 0 4px 0;
}

.login-input {
  height: 42px;
  border: 1px solid var(--color-border);
  border-radius: 12px;
  padding: 0 14px;
  font-size: var(--font-size-md);
  font-family: inherit;
  color: var(--color-text-primary);
  background: #fff;
  outline: none;
}

.login-input:focus {
  border-color: var(--accent);
}

.login-error {
  margin-top: 12px;
  background: var(--color-danger-soft);
  border: 1px solid var(--color-danger);
  border-radius: var(--radius-sm);
  padding: 8px 12px;
  font-size: var(--font-size-sm);
  color: var(--color-danger);
}

.login-btn {
  margin-top: 18px;
  height: 46px;
  background: #4F7456;
  color: #fff;
  border: none;
  border-radius: 12px;
  font-family: inherit;
  font-size: var(--font-size-md);
  font-weight: 600;
  cursor: pointer;
}

.login-btn:hover:not(:disabled) {
  background: #43634a;
}

.login-btn:disabled {
  opacity: 0.65;
  cursor: wait;
}

.login-switch {
  margin-top: 12px;
  background: transparent;
  border: none;
  color: var(--accent-strong);
  font-family: inherit;
  font-size: var(--font-size-sm);
  font-weight: 600;
  cursor: pointer;
  padding: 4px;
}

.login-switch:hover:not(:disabled) {
  text-decoration: underline;
}
</style>
