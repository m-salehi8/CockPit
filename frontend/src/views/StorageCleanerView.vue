<script setup>
import { ref, computed, onMounted } from 'vue'
import {
  HardDrive,
  FolderSearch,
  Trash2,
  RefreshCw,
  CheckSquare,
  Square,
  Shield,
  Package,
  Layers,
  FileText,
  Terminal,
  Container,
} from 'lucide-vue-next'
import { useToast } from '../composables/useToast'
import { useTerminalDrawer } from '../composables/useTerminalDrawer'
import { formatBytes, formatRelativeTime } from '../composables/useFormatters'

const { notify } = useToast()
const { showActionOutput } = useTerminalDrawer()

const loadingOverview = ref(false)
const disks = ref(null)
const caches = ref(null)
const cleaningCacheId = ref('')

const workspacePath = ref('~/projects')
const scanningJunk = ref(false)
const junkResult = ref({
  scanned_root: '',
  total_size_bytes: 0,
  item_count: 0,
  items: [],
})
const selectedJunkPaths = ref(new Set())
const deletingJunk = ref(false)
const junkTypeFilter = ref('all')

const filteredJunkItems = computed(() => {
  const list = junkResult.value.items || []
  if (junkTypeFilter.value === 'all') return list
  return list.filter((i) => i.type === junkTypeFilter.value)
})

const selectedJunkBytes = computed(() => {
  let sum = 0
  for (const item of junkResult.value.items || []) {
    if (selectedJunkPaths.value.has(item.path)) {
      sum += item.size_bytes
    }
  }
  return sum
})

async function fetchStorageOverview() {
  loadingOverview.value = true
  try {
    const res = await fetch('/api/storage/overview')
    const data = await res.json()
    disks.value = data.disks
    caches.value = data.caches
  } catch (err) {
    notify({ title: 'Storage Overview Error', message: String(err), type: 'error' })
  } finally {
    loadingOverview.value = false
  }
}

async function runDevJunkScan() {
  scanningJunk.value = true
  selectedJunkPaths.value = new Set()
  try {
    const res = await fetch('/api/storage/scan-dev-junk', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ root_path: workspacePath.value, max_depth: 6 }),
    })
    const data = await res.json()
    junkResult.value = data
  } catch (err) {
    notify({ title: 'Scan Failed', message: String(err), type: 'error' })
  } finally {
    scanningJunk.value = false
  }
}

function toggleJunkSelection(path) {
  const next = new Set(selectedJunkPaths.value)
  if (next.has(path)) {
    next.delete(path)
  } else {
    next.add(path)
  }
  selectedJunkPaths.value = next
}

function selectAllFilteredJunk() {
  const items = filteredJunkItems.value
  if (selectedJunkPaths.value.size === items.length) {
    selectedJunkPaths.value = new Set()
  } else {
    selectedJunkPaths.value = new Set(items.map((i) => i.path))
  }
}

async function handleBulkDeleteJunk() {
  if (selectedJunkPaths.value.size === 0) return
  deletingJunk.value = true
  try {
    const res = await fetch('/api/storage/delete-dev-junk', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ paths: Array.from(selectedJunkPaths.value) }),
    })
    const data = await res.json()
    notify({
      title: data.success ? 'Artifact Cleanup Complete' : 'Cleanup Warning',
      message: data.message,
      type: data.success ? 'success' : 'warning',
    })
    await runDevJunkScan()
    await fetchStorageOverview()
  } catch (err) {
    notify({ title: 'Delete Failed', message: String(err), type: 'error' })
  } finally {
    deletingJunk.value = false
  }
}

async function handleCleanSystemCache(targetId) {
  cleaningCacheId.value = targetId
  try {
    const res = await fetch('/api/storage/clean-cache', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target: targetId }),
    })
    const data = await res.json()
    notify({
      title: data.success ? 'Cache Cleaned' : 'Cache Clean Error',
      message: data.message,
      type: data.success ? 'success' : 'error',
    })
    if (data.stdout || data.stderr) {
      showActionOutput({
        title: `Clean Cache (${targetId})`,
        command: `clean-cache ${targetId}`,
        stdout: data.stdout || data.message,
        stderr: data.stderr,
        success: data.success,
      })
    }
    await fetchStorageOverview()
  } catch (err) {
    notify({ title: 'Clean Error', message: String(err), type: 'error' })
  } finally {
    cleaningCacheId.value = ''
  }
}

onMounted(() => {
  fetchStorageOverview()
  runDevJunkScan()
})
</script>

<template>
  <div class="space-y-5">
    <!-- Partition Visual Breakdown -->
    <div class="glass-panel rounded-xl p-5">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-xs font-semibold uppercase tracking-wider text-zinc-400">Partitions</h2>
        <button
          @click="fetchStorageOverview"
          :disabled="loadingOverview"
          class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-white/[0.03] hover:bg-white/[0.07] text-zinc-300 border border-white/[0.06] transition-colors cursor-pointer"
        >
          <RefreshCw class="w-3.5 h-3.5" :class="{ 'animate-spin': loadingOverview }" />
          <span>Refresh</span>
        </button>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div
          v-for="part in disks?.partitions || []"
          :key="part.mountpoint"
          class="glass-card rounded-xl p-5 bg-[#0c0c0e]"
        >
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2.5">
              <HardDrive class="w-4 h-4 text-emerald-400" />
              <span class="text-xs font-semibold text-zinc-100 font-mono">{{ part.mountpoint }}</span>
              <span class="text-[11px] font-mono text-zinc-500">{{ part.device }} · {{ part.fstype }}</span>
            </div>
            <span class="text-xs font-semibold font-mono tabular-nums text-emerald-400">{{ part.percent }}%</span>
          </div>

          <div class="mt-3 h-1.5 w-full bg-zinc-900 rounded-full overflow-hidden">
            <div
              class="h-full rounded-full transition-all duration-300"
              :class="
                part.percent > 88
                  ? 'bg-rose-400'
                  : part.percent > 75
                  ? 'bg-amber-400'
                  : 'bg-emerald-400'
              "
              :style="{ width: `${part.percent}%` }"
            />
          </div>

          <div class="mt-2.5 flex items-center justify-between text-[11px] text-zinc-500 font-mono tabular-nums">
            <span>Used <strong class="text-zinc-300 font-normal">{{ formatBytes(part.used_bytes) }}</strong></span>
            <span>Free <strong class="text-emerald-400 font-normal">{{ formatBytes(part.free_bytes) }}</strong></span>
            <span>Total {{ formatBytes(part.total_bytes) }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- System Cache Cleaner Cards -->
    <div class="glass-panel rounded-xl p-5">
      <h3 class="text-xs font-semibold uppercase tracking-wider text-zinc-400 mb-4">System & Package Caches</h3>

      <div v-if="caches" class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        <!-- APT Cache -->
        <div class="glass-card rounded-xl p-5 flex flex-col justify-between bg-[#0c0c0e]">
          <div>
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <Package class="w-4 h-4 text-emerald-400" />
                <h4 class="text-xs font-medium text-zinc-100">{{ caches.apt_cache.title }}</h4>
              </div>
              <span class="px-1.5 py-0.5 text-[10px] font-mono rounded bg-amber-500/10 text-amber-300 border border-amber-500/25">
                root
              </span>
            </div>
            <p class="text-[11px] font-mono text-zinc-500 mt-1.5 truncate">
              {{ caches.apt_cache.command_preview }}
            </p>
          </div>
          <div class="mt-4 flex items-center justify-between">
            <span class="text-base font-semibold font-mono tabular-nums text-emerald-400">
              {{ formatBytes(caches.apt_cache.size_bytes) }}
            </span>
            <button
              @click="handleCleanSystemCache('apt')"
              :disabled="cleaningCacheId === 'apt'"
              class="px-3 py-1.5 rounded-lg text-xs font-medium bg-white/[0.04] hover:bg-emerald-500/15 text-zinc-200 hover:text-emerald-300 border border-white/[0.07] cursor-pointer disabled:opacity-40"
            >
              {{ cleaningCacheId === 'apt' ? 'Cleaning...' : 'Clean' }}
            </button>
          </div>
        </div>

        <!-- Disabled Snap Revisions -->
        <div class="glass-card rounded-xl p-5 flex flex-col justify-between bg-[#0c0c0e]">
          <div>
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <Layers class="w-4 h-4 text-cyan-400" />
                <h4 class="text-xs font-medium text-zinc-100">{{ caches.snap_old.title }}</h4>
              </div>
              <span class="px-1.5 py-0.5 text-[10px] font-mono rounded bg-amber-500/10 text-amber-300 border border-amber-500/25">
                root
              </span>
            </div>
            <p class="text-[11px] font-mono text-zinc-500 mt-1.5 truncate">
              {{ caches.snap_old.command_preview }}
            </p>
          </div>
          <div class="mt-4 flex items-center justify-between">
            <span class="text-base font-semibold font-mono tabular-nums text-cyan-400">
              {{ formatBytes(caches.snap_old.size_bytes) }}
            </span>
            <button
              @click="handleCleanSystemCache('snap_old')"
              :disabled="cleaningCacheId === 'snap_old' || caches.snap_old.count === 0"
              class="px-3 py-1.5 rounded-lg text-xs font-medium bg-white/[0.04] hover:bg-cyan-500/15 text-zinc-200 hover:text-cyan-300 border border-white/[0.07] cursor-pointer disabled:opacity-40"
            >
              {{ cleaningCacheId === 'snap_old' ? 'Purging...' : 'Purge' }}
            </button>
          </div>
        </div>

        <!-- Systemd Journal Logs -->
        <div class="glass-card rounded-xl p-5 flex flex-col justify-between bg-[#0c0c0e]">
          <div>
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <FileText class="w-4 h-4 text-amber-400" />
                <h4 class="text-xs font-medium text-zinc-100">{{ caches.journal_logs.title }}</h4>
              </div>
              <span class="px-1.5 py-0.5 text-[10px] font-mono rounded bg-amber-500/10 text-amber-300 border border-amber-500/25">
                root
              </span>
            </div>
            <p class="text-[11px] font-mono text-zinc-500 mt-1.5 truncate">
              {{ caches.journal_logs.command_preview }}
            </p>
          </div>
          <div class="mt-4 flex items-center justify-between">
            <span class="text-base font-semibold font-mono tabular-nums text-amber-400">
              {{ formatBytes(caches.journal_logs.size_bytes) }}
            </span>
            <button
              @click="handleCleanSystemCache('journal')"
              :disabled="cleaningCacheId === 'journal'"
              class="px-3 py-1.5 rounded-lg text-xs font-medium bg-white/[0.04] hover:bg-amber-500/15 text-zinc-200 hover:text-amber-300 border border-white/[0.07] cursor-pointer disabled:opacity-40"
            >
              {{ cleaningCacheId === 'journal' ? 'Vacuuming...' : 'Vacuum 3d' }}
            </button>
          </div>
        </div>

        <!-- Pip Cache -->
        <div class="glass-card rounded-xl p-5 flex flex-col justify-between bg-[#0c0c0e]">
          <div>
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <Terminal class="w-4 h-4 text-emerald-400" />
                <h4 class="text-xs font-medium text-zinc-100">{{ caches.pip_cache.title }}</h4>
              </div>
              <span class="text-[10px] text-zinc-500 font-mono">user</span>
            </div>
            <p class="text-[11px] font-mono text-zinc-500 mt-1.5 truncate">
              {{ caches.pip_cache.path }}
            </p>
          </div>
          <div class="mt-4 flex items-center justify-between">
            <span class="text-base font-semibold font-mono tabular-nums text-emerald-400">
              {{ formatBytes(caches.pip_cache.size_bytes) }}
            </span>
            <button
              @click="handleCleanSystemCache('pip')"
              :disabled="cleaningCacheId === 'pip' || caches.pip_cache.size_bytes === 0"
              class="px-3 py-1.5 rounded-lg text-xs font-medium bg-white/[0.04] hover:bg-emerald-500/15 text-zinc-200 hover:text-emerald-300 border border-white/[0.07] cursor-pointer disabled:opacity-40"
            >
              {{ cleaningCacheId === 'pip' ? 'Clearing...' : 'Clear' }}
            </button>
          </div>
        </div>

        <!-- NPM Cache -->
        <div class="glass-card rounded-xl p-5 flex flex-col justify-between bg-[#0c0c0e]">
          <div>
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <Terminal class="w-4 h-4 text-amber-400" />
                <h4 class="text-xs font-medium text-zinc-100">{{ caches.npm_cache.title }}</h4>
              </div>
              <span class="text-[10px] text-zinc-500 font-mono">user</span>
            </div>
            <p class="text-[11px] font-mono text-zinc-500 mt-1.5 truncate">
              {{ caches.npm_cache.path }}
            </p>
          </div>
          <div class="mt-4 flex items-center justify-between">
            <span class="text-base font-semibold font-mono tabular-nums text-amber-400">
              {{ formatBytes(caches.npm_cache.size_bytes) }}
            </span>
            <button
              @click="handleCleanSystemCache('npm')"
              :disabled="cleaningCacheId === 'npm' || caches.npm_cache.size_bytes === 0"
              class="px-3 py-1.5 rounded-lg text-xs font-medium bg-white/[0.04] hover:bg-amber-500/15 text-zinc-200 hover:text-amber-300 border border-white/[0.07] cursor-pointer disabled:opacity-40"
            >
              {{ cleaningCacheId === 'npm' ? 'Clearing...' : 'Clear' }}
            </button>
          </div>
        </div>

        <!-- Docker System Prune -->
        <div class="glass-card rounded-xl p-5 flex flex-col justify-between bg-[#0c0c0e]">
          <div>
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <Container class="w-4 h-4 text-cyan-400" />
                <h4 class="text-xs font-medium text-zinc-100">{{ caches.docker.title }}</h4>
              </div>
              <span class="text-[10px] text-zinc-500 font-mono">docker</span>
            </div>
            <p class="text-[11px] text-zinc-500 mt-1.5 line-clamp-2" :title="caches.docker.summary">
              {{ caches.docker.summary }}
            </p>
          </div>
          <div class="mt-4 flex items-center justify-between">
            <span class="text-xs font-mono text-cyan-400">
              {{ caches.docker.available ? 'CLI Ready' : 'Not Installed' }}
            </span>
            <button
              @click="handleCleanSystemCache('docker')"
              :disabled="cleaningCacheId === 'docker' || !caches.docker.available"
              class="px-3 py-1.5 rounded-lg text-xs font-medium bg-white/[0.04] hover:bg-cyan-500/15 text-zinc-200 hover:text-cyan-300 border border-white/[0.07] cursor-pointer disabled:opacity-40"
            >
              {{ cleaningCacheId === 'docker' ? 'Pruning...' : 'Prune' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Asynchronous Dev Junk Scanner -->
    <div class="glass-panel rounded-xl p-5">
      <div class="flex flex-col lg:flex-row lg:items-center justify-between gap-3 mb-4">
        <div class="flex items-center gap-2.5">
          <h3 class="text-xs font-semibold uppercase tracking-wider text-zinc-400">Workspace Artifacts</h3>
          <span class="px-2 py-0.5 text-[11px] font-mono tabular-nums rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/25">
            {{ formatBytes(junkResult.total_size_bytes) }} Reclaimable
          </span>
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <div class="flex items-center bg-[#09090B] border border-white/[0.07] rounded-lg px-2.5 py-1">
            <FolderSearch class="w-3.5 h-3.5 text-zinc-500 mr-2" />
            <input
              v-model="workspacePath"
              type="text"
              placeholder="~/projects"
              class="bg-transparent text-xs font-mono text-zinc-100 focus:outline-none w-44"
              @keyup.enter="runDevJunkScan"
            />
          </div>

          <button
            @click="runDevJunkScan"
            :disabled="scanningJunk"
            class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-white/[0.03] hover:bg-white/[0.07] text-zinc-300 border border-white/[0.06] transition-colors cursor-pointer"
          >
            <RefreshCw class="w-3.5 h-3.5" :class="{ 'animate-spin': scanningJunk }" />
            <span>{{ scanningJunk ? 'Scanning...' : 'Scan' }}</span>
          </button>

          <button
            v-if="selectedJunkPaths.size > 0"
            @click="handleBulkDeleteJunk"
            :disabled="deletingJunk"
            class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-rose-500/15 hover:bg-rose-500/25 text-rose-300 border border-rose-500/30 transition-all cursor-pointer"
          >
            <Trash2 class="w-3.5 h-3.5" />
            <span>
              {{
                deletingJunk
                  ? 'Deleting...'
                  : `Delete (${selectedJunkPaths.size} · ${formatBytes(selectedJunkBytes)})`
              }}
            </span>
          </button>
        </div>
      </div>

      <!-- Filter Pills -->
      <div class="flex flex-wrap items-center justify-between gap-2 mb-3">
        <div class="flex flex-wrap items-center gap-1">
          <button
            v-for="ft in ['all', 'node_modules', '.venv', 'venv', '__pycache__', '.pytest_cache', 'target']"
            :key="ft"
            @click="junkTypeFilter = ft"
            class="px-2.5 py-1 rounded-md text-[11px] font-mono transition-colors cursor-pointer border"
            :class="
              junkTypeFilter === ft
                ? 'bg-white/[0.07] text-zinc-100 border-white/15'
                : 'bg-transparent text-zinc-500 border-transparent hover:text-zinc-300'
            "
          >
            {{ ft === 'all' ? 'All' : ft }}
          </button>
        </div>

        <button
          v-if="filteredJunkItems.length > 0"
          @click="selectAllFilteredJunk"
          class="text-xs text-cyan-400 hover:text-cyan-300 font-medium cursor-pointer"
        >
          {{
            selectedJunkPaths.size === filteredJunkItems.length
              ? 'Deselect All'
              : `Select All (${filteredJunkItems.length})`
          }}
        </button>
      </div>

      <div v-if="scanningJunk" class="py-10 text-center text-xs text-zinc-500 font-mono">
        Scanning workspace directories...
      </div>

      <div v-else-if="filteredJunkItems.length === 0" class="py-10 text-center text-xs text-zinc-500 font-mono">
        No heavy developer artifacts found in {{ junkResult.scanned_root || workspacePath }}.
      </div>

      <div v-else class="overflow-x-auto max-h-96">
        <table class="w-full text-left border-collapse">
          <thead class="sticky top-0 bg-[#121215]">
            <tr class="border-b border-white/[0.05] text-[11px] font-medium uppercase tracking-wider text-zinc-500">
              <th class="py-2 px-3 w-9"></th>
              <th class="py-2 px-3 font-medium">Project</th>
              <th class="py-2 px-3 font-medium">Type</th>
              <th class="py-2 px-3 font-medium">Path</th>
              <th class="py-2 px-3 font-medium">Modified</th>
              <th class="py-2 px-3 font-medium text-right">Size</th>
            </tr>
          </thead>
          <tbody class="text-xs">
            <tr
              v-for="item in filteredJunkItems"
              :key="item.path"
              @click="toggleJunkSelection(item.path)"
              class="hover:bg-white/[0.03] transition-colors cursor-pointer"
              :class="{ 'bg-emerald-500/[0.04]': selectedJunkPaths.has(item.path) }"
            >
              <td class="py-2 px-3 rounded-l-lg">
                <component
                  :is="selectedJunkPaths.has(item.path) ? CheckSquare : Square"
                  class="w-3.5 h-3.5"
                  :class="selectedJunkPaths.has(item.path) ? 'text-emerald-400' : 'text-zinc-600'"
                />
              </td>
              <td class="py-2 px-3 font-medium text-zinc-200">{{ item.project }}</td>
              <td class="py-2 px-3">
                <span class="px-1.5 py-0.5 rounded font-mono text-[10px] bg-white/[0.04] text-zinc-300 border border-white/[0.06]">
                  {{ item.type }}
                </span>
              </td>
              <td class="py-2 px-3 font-mono text-zinc-500 max-w-md truncate" :title="item.path">
                {{ item.path }}
              </td>
              <td class="py-2 px-3 text-zinc-500 font-mono">{{ formatRelativeTime(item.modified) }}</td>
              <td class="py-2 px-3 text-right font-mono tabular-nums font-medium text-emerald-400 rounded-r-lg">
                {{ formatBytes(item.size_bytes) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
