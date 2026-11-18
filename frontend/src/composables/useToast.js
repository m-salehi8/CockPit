import { reactive } from 'vue'

const state = reactive({
  toasts: [],
})

let nextId = 1

export function useToast() {
  function notify({ title, message = '', type = 'info', duration = 4500 }) {
    const id = nextId++
    state.toasts.push({ id, title, message, type })
    if (duration > 0) {
      setTimeout(() => {
        dismiss(id)
      }, duration)
    }
  }

  function dismiss(id) {
    const idx = state.toasts.findIndex((t) => t.id === id)
    if (idx !== -1) {
      state.toasts.splice(idx, 1)
    }
  }

  return {
    toasts: state.toasts,
    notify,
    dismiss,
  }
}
