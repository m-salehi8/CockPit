import { ref, reactive } from 'vue'

const connected = ref(false)
const latest = ref(null)
const history = reactive({
  timestamps: [],
  cpu: [],
  ramPercent: [],
  swapPercent: [],
  netDown: [],
  netUp: [],
  diskRead: [],
  diskWrite: [],
})

const MAX_POINTS = 40
let socket = null
let reconnectTimer = null

function pushHistory(payload) {
  const timeLabel = new Date(payload.timestamp * 1000).toLocaleTimeString([], {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })

  history.timestamps.push(timeLabel)
  history.cpu.push(payload.cpu?.total_percent ?? 0)
  history.ramPercent.push(payload.memory?.percent ?? 0)
  history.swapPercent.push(payload.swap?.percent ?? 0)
  history.netDown.push(payload.network?.download_bytes_per_sec ?? 0)
  history.netUp.push(payload.network?.upload_bytes_per_sec ?? 0)
  history.diskRead.push(payload.disk_io?.read_bytes_per_sec ?? 0)
  history.diskWrite.push(payload.disk_io?.write_bytes_per_sec ?? 0)

  if (history.timestamps.length > MAX_POINTS) {
    history.timestamps.shift()
    history.cpu.shift()
    history.ramPercent.shift()
    history.swapPercent.shift()
    history.netDown.shift()
    history.netUp.shift()
    history.diskRead.shift()
    history.diskWrite.shift()
  }
}

function connect() {
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
    return
  }

  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const wsUrl = `${proto}//${window.location.host}/ws/metrics`

  socket = new WebSocket(wsUrl)

  socket.onopen = () => {
    connected.value = true
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
  }

  socket.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      latest.value = data
      pushHistory(data)
    } catch {
      // Ignore malformed frame
    }
  }

  socket.onclose = () => {
    connected.value = false
    socket = null
    reconnectTimer = setTimeout(connect, 2500)
  }

  socket.onerror = () => {
    connected.value = false
  }
}

function disconnect() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  if (socket) {
    socket.close()
    socket = null
  }
}

export function useMetricsStream() {
  return {
    connected,
    latest,
    history,
    connect,
    disconnect,
  }
}
