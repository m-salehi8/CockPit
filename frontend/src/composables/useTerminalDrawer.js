import { reactive } from 'vue'
import { useToast } from './useToast'

const state = reactive({
  open: false,
  title: '',
  command: '',
  lines: [],
  running: false,
  exitCode: null,
  durationMs: null,
})

export function useTerminalDrawer() {
  const { notify } = useToast()

  function closeDrawer() {
    state.open = false
  }

  function clearDrawer() {
    state.lines = []
  }

  function openDrawer() {
    state.open = true
  }

  async function runCommandStream({ id = null, title, command, requires_root = false }) {
    state.title = title || 'Command Execution'
    state.command = command
    state.lines = []
    state.running = true
    state.exitCode = null
    state.durationMs = null
    state.open = true

    try {
      const response = await fetch('/api/commands/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id,
          command,
          requires_root: Boolean(requires_root),
        }),
      })

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const rawLine of lines) {
          if (!rawLine.trim()) continue
          try {
            const evt = JSON.parse(rawLine)
            if (evt.type === 'stdout' || evt.type === 'stderr') {
              state.lines.push({ stream: evt.type, text: evt.data })
            } else if (evt.type === 'exit') {
              state.exitCode = evt.returncode
              state.durationMs = evt.duration_ms
              state.running = false
              notify({
                title: evt.success ? `Executed: ${state.title}` : `Exited (${evt.returncode})`,
                message: `Completed in ${evt.duration_ms} ms.`,
                type: evt.success ? 'success' : 'warning',
              })
            } else if (evt.type === 'error') {
              state.lines.push({ stream: 'stderr', text: evt.data + '\n' })
              state.exitCode = 1
              state.running = false
            }
          } catch {
            // Ignore malformed NDJSON chunk
          }
        }
      }
    } catch (err) {
      state.lines.push({ stream: 'stderr', text: String(err) + '\n' })
      state.running = false
      state.exitCode = 1
    } finally {
      state.running = false
    }
  }

  function showActionOutput({ title, command, stdout = '', stderr = '', success = true, durationMs = null }) {
    if (!stdout && !stderr) return
    state.title = title
    state.command = command
    state.lines = []
    if (stdout) state.lines.push({ stream: 'stdout', text: stdout + '\n' })
    if (stderr) state.lines.push({ stream: 'stderr', text: stderr + '\n' })
    state.running = false
    state.exitCode = success ? 0 : 1
    state.durationMs = durationMs
    state.open = true
  }

  return {
    drawerState: state,
    openDrawer,
    closeDrawer,
    clearDrawer,
    runCommandStream,
    showActionOutput,
  }
}
