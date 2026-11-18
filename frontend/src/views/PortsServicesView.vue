<script setup>
import { ref, computed, onMounted } from 'vue'
import {
  Network,
  Server,
  Play,
  Square,
  RotateCw,
  Skull,
  Search,
  RefreshCw,
  Shield,
  Container,
  Database,
  Zap,
  Globe,
  Terminal,
  Package,
  Clock,
  Radio,
} from 'lucide-vue-next'
import { useToast } from '../composables/useToast'
import { useTerminalDrawer } from '../composables/useTerminalDrawer'
import { formatBytes } from '../composables/useFormatters'

const { notify } = useToast()
const { showActionOutput } = useTerminalDrawer()

const ports = ref([])
const selfPid = ref(null)
const loadingPorts = ref(false)
const portSearch = ref('')
const busyPort = ref(null)

const services = ref([])
const loadingServices = ref(false)
const busyService = ref('')

const filteredPorts = computed(() => {
  const q = portSearch.value.trim().toLowerCase()
  if (!q) return ports.value
  return ports.value.filter(
    (p) =>
      String(p.port).includes(q) ||
      (p.process_name && p.process_name.toLowerCase().includes(q)) ||
      (p.user && p.user.toLowerCase().includes(q)) ||
      (p.pid && String(p.pid).includes(q)) ||
      (p.address && p.address.toLowerCase().includes(q))
  )
})

function getServiceIcon(iconName) {
  const map = {
    container: Container,
    database: Database,
    zap: Zap,
    globe: Globe,
    terminal: Terminal,
    shield: Shield,
    package: Package,
    clock: Clock,
    radio: Radio,
  }
  return map[iconName] || Server
}

async function fetchPorts() {
  loadingPorts.value = true
  try {
    const res = await fetch('/api/network/ports')
    const data = await res.json()
    ports.value = data.ports || []
    selfPid.value = data.self_pid
  } catch (err) {
    notify({ title: 'Ports Query Error', message: String(err), type: 'error' })
  } finally {
    loadingPorts.value = false
  }
}

async function fetchServices() {
  loadingServices.value = true
  try {
    const res = await fetch('/api/network/services')
    const data = await res.json()
    services.value = data.services || []
  } catch (err) {
    notify({ title: 'Systemd Query Error', message: String(err), type: 'error' })
  } finally {
    loadingServices.value = false
  }
}

async function handleKillPort(entry, force = true) {
  busyPort.value = entry.port
  try {
    const res = await fetch('/api/network/ports/kill', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        port: entry.port,
        pid: entry.pid,
        force,
      }),
    })
    const data = await res.json()
    notify({
      title: data.success ? `Port :${entry.port} Freed` : `Port :${entry.port} Blocked`,
      message: data.message,
      type: data.success ? 'success' : 'warning',
    })
    await fetchPorts()
  } catch (err) {
    notify({ title: 'Kill Port Error', message: String(err), type: 'error' })
  } finally {
    busyPort.value = null
  }
}

async function handleServiceAction(unit, action) {
  busyService.value = `${unit}-${action}`
  try {
    const res = await fetch('/api/network/services/action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ unit, action }),
    })
    const data = await res.json()
    notify({
      title: data.success ? `Systemd: ${unit}` : 'Systemd Action Failed',
      message: data.message,
      type: data.success ? 'success' : 'error',
    })
    if (data.stdout || data.stderr) {
      showActionOutput({
        title: `systemctl ${action} ${unit}`,
        command: `pkexec systemctl ${action} ${unit}`,
        stdout: data.stdout || data.message,
        stderr: data.stderr,
        success: data.success,
      })
    }
    await fetchServices()
    await fetchPorts()
  } catch (err) {
    notify({ title: 'Service Control Error', message: String(err), type: 'error' })
  } finally {
    busyService.value = ''
  }
}

onMounted(() => {
  fetchPorts()
  fetchServices()
})
</script>

<template>
  <div class="space-y-5">
    <!-- Active Listening Ports & 1-Click Port Killer -->
    <div class="glass-panel rounded-xl p-5">
      <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
        <div class="flex items-center gap-2.5">
          <h2 class="text-xs font-semibold uppercase tracking-wider text-zinc-400">Listening Ports</h2>
          <span class="px-2 py-0.5 text-[11px] font-mono tabular-nums rounded bg-white/[0.04] text-cyan-400 border border-white/[0.06]">
            {{ ports.length }} Bound
          </span>
        </div>

        <div class="flex items-center gap-2">
          <div class="relative">
            <Search class="w-3.5 h-3.5 text-zinc-500 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              v-model="portSearch"
              type="text"
              placeholder="Filter port (e.g. 3000) or app..."
              class="pl-8 pr-3 py-1.5 text-xs rounded-lg bg-[#09090B] border border-white/[0.07] text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-white/20 w-56"
            />
          </div>
          <button
            @click="fetchPorts"
            :disabled="loadingPorts"
            class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-white/[0.03] hover:bg-white/[0.07] text-zinc-300 border border-white/[0.06] transition-colors cursor-pointer"
          >
            <RefreshCw class="w-3.5 h-3.5" :class="{ 'animate-spin': loadingPorts }" />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      <div v-if="filteredPorts.length === 0" class="py-10 text-center text-xs text-zinc-500 font-mono">
        No matching listening TCP/UDP ports found.
      </div>

      <div v-else class="overflow-x-auto">
        <table class="w-full text-left border-collapse">
          <thead>
            <tr class="border-b border-white/[0.05] text-[11px] font-medium uppercase tracking-wider text-zinc-500">
              <th class="py-2.5 px-3 font-medium">Port</th>
              <th class="py-2.5 px-3 font-medium">Proto</th>
              <th class="py-2.5 px-3 font-medium">Address</th>
              <th class="py-2.5 px-3 font-medium">Process</th>
              <th class="py-2.5 px-3 font-medium">PID</th>
              <th class="py-2.5 px-3 font-medium">User</th>
              <th class="py-2.5 px-3 font-medium text-right">RSS</th>
              <th class="py-2.5 px-3 font-medium text-right">Action</th>
            </tr>
          </thead>
          <tbody class="text-xs">
            <tr
              v-for="entry in filteredPorts"
              :key="`${entry.protocol}-${entry.address}-${entry.port}-${entry.pid}`"
              class="hover:bg-white/[0.03] transition-colors group"
            >
              <td class="py-2.5 px-3 rounded-l-lg">
                <div class="flex items-center gap-2">
                  <span
                    class="font-mono tabular-nums font-semibold"
                    :class="entry.is_common_dev_port ? 'text-emerald-400' : 'text-cyan-400'"
                  >
                    :{{ entry.port }}
                  </span>
                  <span
                    v-if="entry.is_common_dev_port"
                    class="px-1.5 py-0.2 text-[9px] font-mono rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/25"
                  >
                    DEV
                  </span>
                </div>
              </td>
              <td class="py-2.5 px-3 font-mono text-zinc-400">{{ entry.protocol }}</td>
              <td class="py-2.5 px-3 font-mono tabular-nums text-zinc-500">{{ entry.address }}</td>
              <td class="py-2.5 px-3">
                <div class="font-medium text-zinc-200">{{ entry.process_name }}</div>
                <div
                  v-if="entry.cmdline && entry.cmdline !== entry.process_name"
                  class="text-[11px] font-mono text-zinc-500 max-w-xs truncate"
                  :title="entry.cmdline"
                >
                  {{ entry.cmdline }}
                </div>
              </td>
              <td class="py-2.5 px-3 font-mono tabular-nums text-cyan-400">{{ entry.pid || 'root' }}</td>
              <td class="py-2.5 px-3 font-mono text-zinc-500">{{ entry.user }}</td>
              <td class="py-2.5 px-3 font-mono tabular-nums text-right text-emerald-400">
                {{ entry.rss_bytes ? formatBytes(entry.rss_bytes) : '—' }}
              </td>
              <td class="py-2.5 px-3 text-right rounded-r-lg">
                <span
                  v-if="entry.port === 8765 && entry.pid === selfPid"
                  class="px-2 py-0.5 rounded bg-white/[0.04] text-zinc-500 text-[10px] font-mono"
                >
                  Cockpit
                </span>
                <button
                  v-else
                  @click="handleKillPort(entry, true)"
                  :disabled="busyPort === entry.port"
                  class="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-rose-500/10 hover:bg-rose-500/25 text-rose-300 border border-rose-500/20 transition-colors cursor-pointer disabled:opacity-50 text-[11px]"
                >
                  <Skull class="w-3 h-3" />
                  <span>{{ busyPort === entry.port ? '...' : 'Kill' }}</span>
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Systemd Developer Services Dashboard -->
    <div class="glass-panel rounded-xl p-5">
      <div class="flex items-center justify-between mb-4">
        <h3 class="text-xs font-semibold uppercase tracking-wider text-zinc-400">Systemd Daemons</h3>
        <button
          @click="fetchServices"
          :disabled="loadingServices"
          class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-white/[0.03] hover:bg-white/[0.07] text-zinc-300 border border-white/[0.06] transition-colors cursor-pointer"
        >
          <RefreshCw class="w-3.5 h-3.5" :class="{ 'animate-spin': loadingServices }" />
          <span>Refresh</span>
        </button>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        <div
          v-for="svc in services"
          :key="svc.unit"
          class="glass-card rounded-xl p-5 flex flex-col justify-between bg-[#0c0c0e]"
        >
          <div>
            <div class="flex items-start justify-between gap-2">
              <div class="flex items-center gap-2.5">
                <div
                  class="p-2 rounded-lg border"
                  :class="
                    svc.is_active
                      ? 'bg-emerald-500/10 border-emerald-500/25 text-emerald-400'
                      : 'bg-white/[0.03] border-white/[0.06] text-zinc-500'
                  "
                >
                  <component :is="getServiceIcon(svc.icon)" class="w-4 h-4" />
                </div>
                <div>
                  <h4 class="text-xs font-semibold text-zinc-100">{{ svc.label }}</h4>
                  <span class="text-[11px] font-mono text-zinc-500">{{ svc.unit }}.service</span>
                </div>
              </div>

              <!-- Status Dot & Minimal Label -->
              <span
                v-if="!svc.installed"
                class="px-2 py-0.5 text-[10px] font-mono rounded bg-white/[0.03] text-zinc-500 border border-white/[0.05]"
              >
                Missing
              </span>
              <span
                v-else-if="svc.is_active"
                class="inline-flex items-center gap-1.5 px-2 py-0.5 text-[10px] font-mono rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/25"
              >
                <span class="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                Active
              </span>
              <span
                v-else
                class="inline-flex items-center gap-1.5 px-2 py-0.5 text-[10px] font-mono rounded bg-white/[0.03] text-zinc-500 border border-white/[0.06]"
              >
                <span class="w-1.5 h-1.5 rounded-full bg-zinc-600" />
                Stopped
              </span>
            </div>

            <!-- PID & Memory Info -->
            <div class="mt-3 pt-2.5 border-t border-white/[0.05] flex items-center justify-between text-[11px] text-zinc-500 font-mono tabular-nums">
              <span>PID <strong class="text-zinc-300 font-normal">{{ svc.main_pid || '—' }}</strong></span>
              <span>
                RAM
                <strong class="text-emerald-400 font-normal">
                  {{ svc.memory_bytes > 0 ? formatBytes(svc.memory_bytes) : '0 B' }}
                </strong>
              </span>
              <span>{{ svc.unit_file_state }}</span>
            </div>
          </div>

          <!-- Start / Stop / Restart Controls -->
          <div class="mt-3.5 flex items-center gap-1.5">
            <button
              v-if="!svc.is_active"
              @click="handleServiceAction(svc.unit, 'start')"
              :disabled="!svc.installed || busyService === `${svc.unit}-start`"
              class="flex-1 inline-flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-xs font-medium bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300 border border-emerald-500/25 transition-colors cursor-pointer disabled:opacity-35"
            >
              <Play class="w-3 h-3" />
              <span>{{ busyService === `${svc.unit}-start` ? 'Starting...' : 'Start' }}</span>
            </button>

            <button
              v-else
              @click="handleServiceAction(svc.unit, 'stop')"
              :disabled="!svc.installed || busyService === `${svc.unit}-stop`"
              class="flex-1 inline-flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-xs font-medium bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border border-rose-500/25 transition-colors cursor-pointer disabled:opacity-35"
            >
              <Square class="w-3 h-3" />
              <span>{{ busyService === `${svc.unit}-stop` ? 'Stopping...' : 'Stop' }}</span>
            </button>

            <button
              @click="handleServiceAction(svc.unit, 'restart')"
              :disabled="!svc.installed || busyService === `${svc.unit}-restart`"
              class="inline-flex items-center justify-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium bg-white/[0.03] hover:bg-white/[0.08] text-zinc-300 border border-white/[0.07] transition-colors cursor-pointer disabled:opacity-35"
              title="Restart Service"
            >
              <RotateCw
                class="w-3 h-3"
                :class="{ 'animate-spin': busyService === `${svc.unit}-restart` }"
              />
              <span>Restart</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
