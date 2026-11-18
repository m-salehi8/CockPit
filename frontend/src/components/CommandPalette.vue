<script setup>
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import {
  Search,
  Activity,
  Package,
  HardDrive,
  Network,
  Terminal,
  Zap,
  Sparkles,
  RefreshCw,
  Flame,
  Globe,
  Shield,
  Skull,
  CornerDownLeft,
  Cpu,
} from 'lucide-vue-next'
import { useToast } from '../composables/useToast'
import { useTerminalDrawer } from '../composables/useTerminalDrawer'
import { formatBytes } from '../composables/useFormatters'

const props = defineProps({
  open: Boolean,
})

const emit = defineEmits(['close', 'navigate', 'refresh-data'])

const { notify } = useToast()
const { runCommandStream, showActionOutput } = useTerminalDrawer()

const query = ref('')
const selectedIndex = ref(0)
const inputEl = ref(null)
const listEl = ref(null)

const savedCommands = ref([])
const activePorts = ref([])
const processGroups = ref([])
const selfPid = ref(null)

async function loadPaletteData() {
  try {
    const [cmdRes, portRes, procRes] = await Promise.all([
      fetch('/api/commands').then((r) => r.json()).catch(() => ({ commands: [] })),
      fetch('/api/network/ports').then((r) => r.json()).catch(() => ({ ports: [] })),
      fetch('/api/system/processes?limit=25').then((r) => r.json()).catch(() => ({ groups: [] })),
    ])
    savedCommands.value = cmdRes.commands || []
    activePorts.value = portRes.ports || []
    selfPid.value = portRes.self_pid || null
    processGroups.value = procRes.groups || []
  } catch {
    // Silent fallback
  }
}

watch(
  () => props.open,
  async (isOpen) => {
    if (isOpen) {
      query.value = ''
      selectedIndex.value = 0
      loadPaletteData()
      await nextTick()
      inputEl.value?.focus()
    }
  }
)

const staticActions = [
  // Navigation
  {
    id: 'nav-monitor',
    type: 'Navigation',
    title: 'Go to System',
    subtitle: 'Live telemetry, CPU cores, ZRAM & processes',
    keywords: 'system monitor dashboard cpu ram processes telemetry',
    badge: 'Alt+1',
    icon: Activity,
    accent: 'text-emerald-400',
    run: () => emit('navigate', 'monitor'),
  },
  {
    id: 'nav-packages',
    type: 'Navigation',
    title: 'Go to Apps',
    subtitle: 'APT, Snap, NPM, Pip & AppImages',
    keywords: 'apps packages apt snap npm pip appimage uninstall',
    badge: 'Alt+2',
    icon: Package,
    accent: 'text-cyan-400',
    run: () => emit('navigate', 'packages'),
  },
  {
    id: 'nav-storage',
    type: 'Navigation',
    title: 'Go to Cleaner',
    subtitle: 'Partitions, system caches & dev workspace junk',
    keywords: 'cleaner storage disk cache node_modules venv',
    badge: 'Alt+3',
    icon: HardDrive,
    accent: 'text-emerald-400',
    run: () => emit('navigate', 'storage'),
  },
  {
    id: 'nav-network',
    type: 'Navigation',
    title: 'Go to Ports',
    subtitle: 'Listening TCP/UDP sockets & systemd daemons',
    keywords: 'ports network sockets systemd services docker postgres',
    badge: 'Alt+4',
    icon: Network,
    accent: 'text-cyan-400',
    run: () => emit('navigate', 'network'),
  },
  {
    id: 'nav-commands',
    type: 'Navigation',
    title: 'Go to Commands',
    subtitle: 'Saved command deck scripts & terminal output',
    keywords: 'commands deck scripts terminal bash tweaks',
    badge: 'Alt+5',
    icon: Terminal,
    accent: 'text-amber-400',
    run: () => emit('navigate', 'commands'),
  },

  // Rescue & DNS Quick Actions
  {
    id: 'rescue-drop-cache',
    type: 'System Rescue',
    title: 'Drop Memory Caches (Free RAM)',
    subtitle: 'Flush Linux PageCache, dentries & inodes via pkexec',
    keywords: 'drop cache free ram memory rescue flush slab',
    badge: 'Rescue',
    icon: Sparkles,
    accent: 'text-emerald-400',
    run: async () => {
      const res = await fetch('/api/system/rescue/drop-caches', { method: 'POST' })
      const data = await res.json()
      notify({
        title: data.success ? 'Memory Caches Dropped' : 'Cache Drop Cancelled',
        message: data.message,
        type: data.success ? 'success' : 'warning',
      })
    },
  },
  {
    id: 'rescue-swap-refresh',
    type: 'System Rescue',
    title: 'Swap Refresh (Flush Swap to RAM)',
    subtitle: 'Safely cycle swapoff -a && swapon -a',
    keywords: 'swap refresh cycle flush memory rescue',
    badge: 'Rescue',
    icon: RefreshCw,
    accent: 'text-cyan-400',
    run: async () => {
      const res = await fetch('/api/system/rescue/swap-refresh', { method: 'POST' })
      const data = await res.json()
      notify({
        title: data.success ? 'Swap Refreshed' : 'Swap Refresh Skipped',
        message: data.message,
        type: data.success ? 'success' : 'warning',
      })
    },
  },
  {
    id: 'rescue-panic-focus',
    type: 'System Rescue',
    title: 'Toggle Dev Focus Mode (Panic)',
    subtitle: 'Pause or restore heavy background services (Docker, Postgres, Redis, Snapd)',
    keywords: 'panic dev focus mode stop services free ram docker postgres',
    badge: 'Panic',
    icon: Flame,
    accent: 'text-amber-400',
    run: async () => {
      const snapRes = await fetch('/api/system/snapshot').then((r) => r.json()).catch(() => ({}))
      const enable = !snapRes.focus_mode_active
      const res = await fetch('/api/system/rescue/focus-mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enable }),
      })
      const data = await res.json()
      notify({
        title: data.success ? 'Dev Focus Mode Updated' : 'Focus Mode Error',
        message: data.message,
        type: data.success ? 'success' : 'error',
      })
    },
  },
  {
    id: 'rescue-enable-zram',
    type: 'System Rescue',
    title: 'Enable ZRAM Compressed Swap',
    subtitle: 'Configure high-priority zstd ZRAM swap block device via pkexec',
    keywords: 'zram enable swap compressed memory',
    badge: 'ZRAM',
    icon: Zap,
    accent: 'text-cyan-400',
    run: async () => {
      const res = await fetch('/api/system/rescue/enable-zram', { method: 'POST' })
      const data = await res.json()
      notify({
        title: data.success ? 'ZRAM Enabled' : 'ZRAM Configuration Failed',
        message: data.message,
        type: data.success ? 'success' : 'warning',
      })
    },
  },
  {
    id: 'dns-quick-shecan',
    type: 'Quick DNS',
    title: 'Switch DNS to Shecan',
    subtitle: '178.22.122.100 · 185.51.200.2',
    keywords: 'shecan dns switch network',
    badge: 'DNS',
    icon: Shield,
    accent: 'text-emerald-400',
    run: async () => {
      const res = await fetch('/api/system/dns/switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile: 'Shecan' }),
      })
      const data = await res.json()
      notify({
        title: data.success ? 'DNS: Shecan Active' : 'DNS Switch Failed',
        message: data.message,
        type: data.success ? 'success' : 'warning',
      })
    },
  },
  {
    id: 'dns-quick-cloudflare',
    type: 'Quick DNS',
    title: 'Switch DNS to Cloudflare (1.1.1.1)',
    subtitle: '1.1.1.1 · 1.0.0.1',
    keywords: 'cloudflare 1.1.1.1 dns switch network',
    badge: 'DNS',
    icon: Globe,
    accent: 'text-cyan-400',
    run: async () => {
      const res = await fetch('/api/system/dns/switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile: '1.1.1.1' }),
      })
      const data = await res.json()
      notify({
        title: data.success ? 'DNS: Cloudflare 1.1.1.1 Active' : 'DNS Switch Failed',
        message: data.message,
        type: data.success ? 'success' : 'warning',
      })
    },
  },
  {
    id: 'dns-quick-auto',
    type: 'Quick DNS',
    title: 'Reset DNS to Automatic (DHCP)',
    subtitle: 'Revert custom interface DNS and flush cache',
    keywords: 'auto automatic dhcp reset revert dns flush',
    badge: 'DNS',
    icon: RefreshCw,
    accent: 'text-zinc-300',
    run: async () => {
      const res = await fetch('/api/system/dns/switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile: 'Auto' }),
      })
      const data = await res.json()
      notify({
        title: data.success ? 'DNS: Automatic (DHCP)' : 'DNS Reset Failed',
        message: data.message,
        type: data.success ? 'success' : 'warning',
      })
    },
  },
]

function fuzzyScore(text, pattern) {
  if (!pattern) return 1
  const t = text.toLowerCase()
  const p = pattern.toLowerCase()
  if (t === p) return 100
  if (t.startsWith(p)) return 85
  if (t.includes(p)) return 65

  // Token match
  const tokens = p.split(/\s+/).filter(Boolean)
  if (tokens.length > 1 && tokens.every((tk) => t.includes(tk))) {
    return 55
  }

  // Subsequence match
  let ti = 0
  let pi = 0
  while (ti < t.length && pi < p.length) {
    if (t[ti] === p[pi]) pi++
    ti++
  }
  return pi === p.length ? 25 : 0
}

const results = computed(() => {
  const raw = query.value.trim()
  const q = raw.toLowerCase()

  const portItems = activePorts.value
    .filter((p) => !(p.port === 8765 && p.pid === selfPid.value))
    .map((entry) => ({
      id: `port-${entry.protocol}-${entry.port}-${entry.pid}`,
      type: 'Kill Port',
      title: `Kill :${entry.port} (${entry.process_name})`,
      subtitle: `${entry.protocol} ${entry.address}:${entry.port} · PID ${entry.pid || 'root'} · ${
        entry.rss_bytes ? formatBytes(entry.rss_bytes) : 'daemon'
      }`,
      keywords: `:${entry.port} port ${entry.port} ${entry.process_name} ${entry.protocol} kill`,
      badge: `:${entry.port}`,
      icon: Skull,
      accent: 'text-rose-400',
      isPort: true,
      portNum: String(entry.port),
      run: async () => {
        const res = await fetch('/api/network/ports/kill', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ port: entry.port, pid: entry.pid, force: true }),
        })
        const data = await res.json()
        notify({
          title: data.success ? `Port :${entry.port} Freed` : `Port :${entry.port} Error`,
          message: data.message,
          type: data.success ? 'success' : 'warning',
        })
        emit('refresh-data')
      },
    }))

  const commandItems = savedCommands.value.map((card) => ({
    id: `cmd-${card.id}`,
    type: 'Command Deck',
    title: card.title,
    subtitle: `$ ${card.command}`,
    keywords: `${card.title} ${card.category} ${card.description} ${card.command}`,
    badge: 'Run',
    icon: Terminal,
    accent: 'text-emerald-400',
    run: () => {
      runCommandStream({
        id: card.id,
        title: card.title,
        command: card.command,
        requires_root: card.requires_root,
      })
    },
  }))

  const processItems = processGroups.value.slice(0, 20).map((grp) => ({
    id: `proc-${grp.group_name}`,
    type: 'Kill Process',
    title: `Kill ${grp.group_name}`,
    subtitle: `${grp.process_count} proc(s) · ${formatBytes(grp.total_rss_bytes)} RAM (${grp.memory_percent}%) · CPU ${grp.total_cpu_percent}%`,
    keywords: `kill ${grp.group_name} ${grp.base_executable} process app ram hog`,
    badge: formatBytes(grp.total_rss_bytes),
    icon: Cpu,
    accent: 'text-amber-400',
    run: async () => {
      const res = await fetch('/api/system/processes/kill', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pids: grp.pids, force: false }),
      })
      const data = await res.json()
      notify({
        title: data.success ? `Terminated ${grp.group_name}` : 'Process Kill Error',
        message: data.message,
        type: data.success ? 'success' : 'error',
      })
      emit('refresh-data')
    },
  }))

  // Special mode: if query starts with ':', prioritize ports exclusively
  if (q.startsWith(':')) {
    const portQuery = q.slice(1).trim()
    return portItems.filter((item) => !portQuery || item.portNum.includes(portQuery))
  }

  const allPool = [...staticActions, ...commandItems, ...portItems, ...processItems]

  if (!q) {
    // Default suggestions when empty: Navigation + top Rescue + top 4 ports/processes
    return [
      ...staticActions.slice(0, 9),
      ...portItems.slice(0, 3),
      ...processItems.slice(0, 3),
    ]
  }

  const scored = []
  for (const item of allPool) {
    const s1 = fuzzyScore(item.title, q) * 1.4
    const s2 = fuzzyScore(item.keywords || '', q)
    const s3 = fuzzyScore(item.subtitle || '', q) * 0.7
    const best = Math.max(s1, s2, s3)
    if (best > 0) {
      scored.push({ item, score: best })
    }
  }

  scored.sort((a, b) => b.score - a.score)
  return scored.slice(0, 18).map((s) => s.item)
})

watch(results, () => {
  selectedIndex.value = 0
})

function scrollSelectedIntoView() {
  nextTick(() => {
    if (!listEl.value) return
    const activeEl = listEl.value.querySelector('[data-active="true"]')
    if (activeEl) {
      activeEl.scrollIntoView({ block: 'nearest' })
    }
  })
}

function handleKeydown(e) {
  if (!props.open) return
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    if (results.value.length > 0) {
      selectedIndex.value = (selectedIndex.value + 1) % results.value.length
      scrollSelectedIntoView()
    }
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    if (results.value.length > 0) {
      selectedIndex.value = (selectedIndex.value - 1 + results.value.length) % results.value.length
      scrollSelectedIntoView()
    }
  } else if (e.key === 'Enter') {
    e.preventDefault()
    const current = results.value[selectedIndex.value]
    if (current) {
      executeItem(current)
    }
  } else if (e.key === 'Escape') {
    e.preventDefault()
    emit('close')
  }
}

async function executeItem(item) {
  emit('close')
  await item.run()
}

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown)
})
</script>

<template>
  <Transition name="fade-slide">
    <div
      v-if="open"
      class="fixed inset-0 z-50 flex items-start justify-center pt-[13vh] bg-black/70 backdrop-blur-xs p-4"
      @click.self="emit('close')"
    >
      <div
        class="w-full max-w-xl rounded-xl bg-[#121215] border border-white/12 shadow-2xl overflow-hidden"
      >
        <!-- Command Input Bar -->
        <div class="flex items-center px-4 py-3 border-b border-white/[0.06] gap-3">
          <Search class="w-4 h-4 text-zinc-500 shrink-0" />
          <input
            ref="inputEl"
            v-model="query"
            type="text"
            placeholder="Type a command, tab, :port to kill, or app name..."
            class="w-full bg-transparent text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none"
          />
          <kbd
            class="px-1.5 py-0.5 text-[10px] font-mono text-zinc-500 bg-zinc-900 border border-white/[0.08] rounded shrink-0"
          >
            ESC
          </kbd>
        </div>

        <!-- Results List -->
        <div ref="listEl" class="max-h-80 overflow-y-auto p-1.5 space-y-0.5">
          <div
            v-if="results.length === 0"
            class="py-10 text-center text-xs text-zinc-500 font-mono"
          >
            No matching commands, ports, or processes for "{{ query }}"
          </div>

          <button
            v-for="(item, idx) in results"
            :key="item.id"
            :data-active="idx === selectedIndex"
            @mouseenter="selectedIndex = idx"
            @click="executeItem(item)"
            class="w-full flex items-center justify-between gap-3 px-3 py-2 rounded-lg text-left transition-colors cursor-pointer"
            :class="
              idx === selectedIndex
                ? 'bg-white/[0.07] text-zinc-100'
                : 'text-zinc-400 hover:bg-white/[0.04]'
            "
          >
            <div class="flex items-center gap-3 min-w-0">
              <div
                class="w-7 h-7 rounded-md bg-zinc-900 border border-white/[0.06] flex items-center justify-center shrink-0"
              >
                <component :is="item.icon" class="w-3.5 h-3.5" :class="item.accent" />
              </div>
              <div class="min-w-0">
                <div class="flex items-center gap-2">
                  <span class="text-xs font-medium text-zinc-100 truncate">{{ item.title }}</span>
                  <span class="text-[10px] text-zinc-500">{{ item.type }}</span>
                </div>
                <div class="text-[11px] text-zinc-500 truncate font-mono mt-0.5">
                  {{ item.subtitle }}
                </div>
              </div>
            </div>

            <div class="flex items-center gap-2 shrink-0">
              <span
                v-if="item.badge"
                class="px-1.5 py-0.5 text-[10px] font-mono rounded bg-zinc-900 text-zinc-400 border border-white/[0.06]"
              >
                {{ item.badge }}
              </span>
              <CornerDownLeft
                v-if="idx === selectedIndex"
                class="w-3.5 h-3.5 text-emerald-400"
              />
            </div>
          </button>
        </div>

        <!-- Minimal Footer Hints -->
        <div
          class="px-4 py-2 border-t border-white/[0.06] bg-[#0c0c0e] flex items-center justify-between text-[11px] text-zinc-500"
        >
          <div class="flex items-center gap-3">
            <span><strong class="text-zinc-400 font-mono">↑↓</strong> Navigate</span>
            <span><strong class="text-zinc-400 font-mono">↵</strong> Execute</span>
            <span><strong class="text-zinc-400 font-mono">:3000</strong> Kill Port</span>
          </div>
          <span class="font-mono text-[10px] text-zinc-600">Cockpit Quick Launcher</span>
        </div>
      </div>
    </div>
  </Transition>
</template>
