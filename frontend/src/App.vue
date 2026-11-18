<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import {
  Activity,
  Package,
  HardDrive,
  Network,
  Terminal,
  Zap,
  Globe,
  Search,
  Flame,
} from 'lucide-vue-next'
import SystemMonitorView from './views/SystemMonitorView.vue'
import PackageManagerView from './views/PackageManagerView.vue'
import StorageCleanerView from './views/StorageCleanerView.vue'
import PortsServicesView from './views/PortsServicesView.vue'
import CommandDeckView from './views/CommandDeckView.vue'
import ToastContainer from './components/ToastContainer.vue'
import CommandPalette from './components/CommandPalette.vue'
import TerminalDrawer from './components/TerminalDrawer.vue'
import { useMetricsStream } from './composables/useMetricsStream'
import { useToast } from './composables/useToast'
import { useTerminalDrawer } from './composables/useTerminalDrawer'
import { formatBytes, formatUptime } from './composables/useFormatters'

const { connected, latest, connect, disconnect } = useMetricsStream()
const { notify } = useToast()
const { drawerState, closeDrawer, clearDrawer } = useTerminalDrawer()

const currentView = ref('monitor')
const paletteOpen = ref(false)
const switchingDns = ref(false)
const freeingRam = ref(false)

const hostMeta = ref({
  hostname: 'ubuntu-host',
  kernel: 'Linux',
  backend_rss_mb: 0,
})

const navItems = [
  {
    id: 'monitor',
    label: 'System',
    shortcut: 'Alt+1',
    icon: Activity,
  },
  {
    id: 'packages',
    label: 'Apps',
    shortcut: 'Alt+2',
    icon: Package,
  },
  {
    id: 'storage',
    label: 'Cleaner',
    shortcut: 'Alt+3',
    icon: HardDrive,
  },
  {
    id: 'network',
    label: 'Ports',
    shortcut: 'Alt+4',
    icon: Network,
  },
  {
    id: 'commands',
    label: 'Commands',
    shortcut: 'Alt+5',
    icon: Terminal,
  },
]

const currentNav = computed(() => navItems.find((i) => i.id === currentView.value) || navItems[0])

const activeDnsProfile = computed(() => latest.value?.network?.dns_profile || 'Auto')
const pingMs = computed(() => latest.value?.network?.ping_ms ?? null)

async function fetchHealthMeta() {
  try {
    const res = await fetch('/api/health')
    const data = await res.json()
    hostMeta.value = data
  } catch {
    // Ignore on boot
  }
}

async function cycleDnsProfile() {
  if (switchingDns.value) return
  const order = ['Shecan', '1.1.1.1', 'Auto']
  const currentIdx = order.indexOf(activeDnsProfile.value)
  const nextProfile = order[(currentIdx + 1) % order.length]

  switchingDns.value = true
  try {
    const res = await fetch('/api/system/dns/switch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ profile: nextProfile }),
    })
    const data = await res.json()
    notify({
      title: data.success ? `DNS: ${data.dns_profile}` : 'DNS Switch Cancelled',
      message: data.message,
      type: data.success ? 'success' : 'warning',
    })
  } catch (err) {
    notify({ title: 'DNS Error', message: String(err), type: 'error' })
  } finally {
    switchingDns.value = false
  }
}

async function handleQuickFreeRam() {
  if (freeingRam.value) return
  freeingRam.value = true
  try {
    const res = await fetch('/api/system/rescue/drop-caches', { method: 'POST' })
    const data = await res.json()
    notify({
      title: data.success ? 'Memory Caches Dropped' : 'Cache Drop Cancelled',
      message: data.message,
      type: data.success ? 'success' : 'warning',
    })
  } catch (err) {
    notify({ title: 'Free RAM Error', message: String(err), type: 'error' })
  } finally {
    freeingRam.value = false
  }
}

function handleGlobalKeydown(e) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    paletteOpen.value = !paletteOpen.value
    return
  }

  if (e.altKey && !e.ctrlKey && !e.metaKey) {
    const idx = parseInt(e.key, 10)
    if (idx >= 1 && idx <= navItems.length) {
      e.preventDefault()
      currentView.value = navItems[idx - 1].id
    }
  }
}

onMounted(() => {
  connect()
  fetchHealthMeta()
  window.addEventListener('keydown', handleGlobalKeydown)
})

onBeforeUnmount(() => {
  disconnect()
  window.removeEventListener('keydown', handleGlobalKeydown)
})
</script>

<template>
  <div class="h-screen w-screen flex bg-[#09090B] text-zinc-100 overflow-hidden select-none">
    <!-- Minimal Left Sidebar Navigation -->
    <aside class="w-56 shrink-0 h-full bg-[#09090B] border-r border-white/[0.06] flex flex-col justify-between">
      <div>
        <!-- Brand Header -->
        <div
          class="h-13 px-4 border-b border-white/[0.06] flex items-center justify-between"
          :title="`Host: ${hostMeta.hostname} · Kernel: ${hostMeta.kernel}`"
        >
          <div class="flex items-center gap-2.5">
            <div class="w-6 h-6 rounded-md bg-[#121215] border border-white/10 flex items-center justify-center">
              <img src="/cockpit.svg" alt="Cockpit" class="w-4 h-4" />
            </div>
            <span class="text-xs font-semibold tracking-wider text-zinc-100 uppercase">Cockpit</span>
          </div>
          <span class="px-1.5 py-0.5 text-[10px] font-mono text-zinc-500 bg-[#121215] rounded border border-white/[0.06]">
            8GB
          </span>
        </div>

        <!-- Compact 1-Line Navigation Links -->
        <nav class="p-2.5 space-y-1">
          <button
            v-for="item in navItems"
            :key="item.id"
            @click="currentView = item.id"
            class="w-full flex items-center justify-between px-3 py-2 rounded-lg text-left transition-all cursor-pointer group"
            :class="
              currentView === item.id
                ? 'bg-[#121215] text-zinc-100 border border-white/10'
                : 'text-zinc-400 hover:text-zinc-200 hover:bg-white/[0.03] border border-transparent'
            "
          >
            <div class="flex items-center gap-2.5 min-w-0">
              <component
                :is="item.icon"
                class="w-4 h-4 shrink-0 transition-colors"
                :class="currentView === item.id ? 'text-emerald-400' : 'text-zinc-500 group-hover:text-zinc-300'"
              />
              <span class="text-xs font-medium truncate">{{ item.label }}</span>
            </div>
            <kbd
              class="text-[10px] font-mono px-1.5 py-0.5 rounded bg-zinc-900/80 text-zinc-500 border border-white/[0.05]"
            >
              {{ item.shortcut }}
            </kbd>
          </button>
        </nav>
      </div>

      <!-- Bottom Minimalist 1-Line Telemetry Status Bar -->
      <div
        class="px-3.5 py-3 border-t border-white/[0.06] bg-[#09090B] space-y-2"
        :title="`Host: ${hostMeta.hostname} • Kernel: ${hostMeta.kernel} • Backend RSS: ${
          latest?.backend_rss_mb ?? hostMeta.backend_rss_mb
        } MB`"
      >
        <!-- Ultra-thin dual progress hairlines -->
        <div class="grid grid-cols-2 gap-1.5">
          <div class="h-0.5 w-full bg-zinc-900 rounded-full overflow-hidden" title="CPU Load">
            <div
              class="h-full bg-cyan-400 transition-all duration-300"
              :style="{ width: `${latest?.cpu?.total_percent || 0}%` }"
            />
          </div>
          <div class="h-0.5 w-full bg-zinc-900 rounded-full overflow-hidden" title="RAM Usage">
            <div
              class="h-full bg-emerald-400 transition-all duration-300"
              :style="{ width: `${latest?.memory?.percent || 0}%` }"
            />
          </div>
        </div>

        <div class="flex items-center justify-between text-[11px] font-mono text-zinc-500">
          <div class="flex items-center gap-1.5">
            <span
              class="w-1.5 h-1.5 rounded-full"
              :class="connected ? 'bg-emerald-400' : 'bg-rose-500'"
            />
            <span class="text-zinc-400">{{ latest?.cpu?.total_percent ?? 0 }}%</span>
            <span>·</span>
            <span class="text-zinc-400">{{ latest?.memory?.percent ?? 0 }}%</span>
          </div>
          <span class="text-[10px] text-zinc-500">
            {{ latest?.backend_rss_mb ?? hostMeta.backend_rss_mb }}MB
          </span>
        </div>
      </div>
    </aside>

    <!-- Main Content Viewport -->
    <div class="flex-1 flex flex-col h-full overflow-hidden">
      <!-- Minimalist Top Quick-Action Header -->
      <header class="h-13 shrink-0 px-6 border-b border-white/[0.06] bg-[#09090B]/90 backdrop-blur-md flex items-center justify-between gap-4">
        <!-- Left: Breadcrumb / Current View Title + minimal Uptime badge -->
        <div class="flex items-center gap-2.5 min-w-0">
          <span class="text-xs text-zinc-500">Cockpit</span>
          <span class="text-xs text-zinc-600">/</span>
          <h2 class="text-xs font-semibold text-zinc-100 truncate">{{ currentNav.label }}</h2>
          <span
            v-if="latest?.uptime_seconds"
            class="px-2 py-0.5 rounded bg-[#121215] border border-white/[0.06] font-mono text-[11px] text-zinc-400 hidden sm:inline-block"
            :title="`Host: ${hostMeta.hostname} · Kernel ${hostMeta.kernel}`"
          >
            {{ formatUptime(latest.uptime_seconds) }}
          </span>
        </div>

        <!-- Center: Minimalist Ctrl+K Search/Command Trigger Bar -->
        <button
          @click="paletteOpen = true"
          class="flex items-center justify-between gap-6 px-3 py-1.5 rounded-lg bg-[#121215] hover:bg-white/[0.04] border border-white/[0.07] hover:border-white/15 text-xs text-zinc-400 transition-all cursor-pointer w-64 sm:w-80"
        >
          <span class="flex items-center gap-2 truncate">
            <Search class="w-3.5 h-3.5 text-zinc-500 shrink-0" />
            <span class="text-zinc-500 truncate">Quick Action...</span>
          </span>
          <kbd class="px-1.5 py-0.5 text-[10px] font-mono text-zinc-400 bg-zinc-900 rounded border border-white/[0.06] shrink-0">
            ⌘K
          </kbd>
        </button>

        <!-- Right: Interactive Quick-Toggles -->
        <div class="flex items-center gap-2.5 text-xs shrink-0">
          <!-- Dev Focus Mode Indicator if active -->
          <span
            v-if="latest?.focus_mode_active"
            class="px-2 py-1 rounded-md bg-amber-500/10 text-amber-300 border border-amber-500/25 text-[11px] font-medium hidden lg:inline-flex items-center gap-1"
          >
            <Flame class="w-3 h-3" />
            Focus
          </span>

          <!-- 1-Click DNS Pill -->
          <button
            @click="cycleDnsProfile"
            :disabled="switchingDns"
            class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-[#121215] hover:bg-white/[0.05] border border-white/[0.06] text-[11px] font-mono transition-colors cursor-pointer disabled:opacity-50"
            title="Click to cycle DNS (Shecan → 1.1.1.1 → Auto)"
          >
            <Globe
              class="w-3 h-3"
              :class="
                activeDnsProfile === 'Shecan'
                  ? 'text-emerald-400'
                  : activeDnsProfile === '1.1.1.1'
                  ? 'text-cyan-400'
                  : 'text-zinc-400'
              "
            />
            <span class="text-zinc-300">{{ switchingDns ? '...' : activeDnsProfile }}</span>
          </button>

          <!-- Live Ping Dot -->
          <div
            class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-[#121215] border border-white/[0.06] text-[11px] font-mono"
            title="Live DNS Resolver Latency"
          >
            <span
              class="w-1.5 h-1.5 rounded-full"
              :class="
                pingMs === null
                  ? 'bg-zinc-600'
                  : pingMs < 60
                  ? 'bg-emerald-400'
                  : pingMs < 130
                  ? 'bg-amber-400'
                  : 'bg-rose-400'
              "
            />
            <span class="text-zinc-300">{{ pingMs !== null ? `${pingMs}ms` : '—' }}</span>
          </div>

          <!-- Available RAM + Quick RAM Rescue Pill -->
          <div class="flex items-center rounded-md bg-[#121215] border border-white/[0.06] overflow-hidden">
            <span class="px-2.5 py-1 font-mono text-[11px] text-zinc-400 hidden md:inline-block">
              <strong class="text-emerald-400 font-medium">{{ formatBytes(latest?.memory?.available_bytes) }}</strong> free
            </span>
            <button
              @click="handleQuickFreeRam"
              :disabled="freeingRam"
              class="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-medium text-zinc-200 hover:text-emerald-300 bg-white/[0.03] hover:bg-emerald-500/15 border-l border-white/[0.06] transition-colors cursor-pointer disabled:opacity-50"
              title="Drop Linux kernel memory caches (pkexec)"
            >
              <Zap class="w-3 h-3 text-emerald-400" />
              <span>{{ freeingRam ? '...' : 'Free RAM' }}</span>
            </button>
          </div>
        </div>
      </header>

      <!-- Active Module Content -->
      <main class="flex-1 overflow-y-auto p-6">
        <Transition name="fade-slide" mode="out-in">
          <SystemMonitorView v-if="currentView === 'monitor'" />
          <PackageManagerView v-else-if="currentView === 'packages'" />
          <StorageCleanerView v-else-if="currentView === 'storage'" />
          <PortsServicesView v-else-if="currentView === 'network'" />
          <CommandDeckView v-else-if="currentView === 'commands'" />
        </Transition>
      </main>
    </div>

    <!-- Global Ctrl+K Command Palette -->
    <CommandPalette
      :open="paletteOpen"
      @close="paletteOpen = false"
      @navigate="(view) => (currentView = view)"
    />

    <!-- Global Slide-Over Terminal Output Drawer -->
    <TerminalDrawer
      :open="drawerState.open"
      :title="drawerState.title"
      :command="drawerState.command"
      :lines="drawerState.lines"
      :running="drawerState.running"
      :exit-code="drawerState.exitCode"
      :duration-ms="drawerState.durationMs"
      @close="closeDrawer"
      @clear="clearDrawer"
    />

    <!-- Global Action Toast Notifications -->
    <ToastContainer />
  </div>
</template>
