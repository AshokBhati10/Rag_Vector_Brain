import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    allowedHosts: ['efficiency-matched-showing-music.trycloudflare.com', '.trycloudflare.com', '.ngrok-free.dev', '.ngrok-free.app', '.ngrok.io', '.ngrok.app']
  }
})