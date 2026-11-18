<script setup>
import { ref, computed, onMounted } from 'vue'
import {
  Package,
  Layers,
  Terminal,
  FileCode2,
  FolderCog,
  Search,
  RefreshCw,
  Trash2,
  AlertTriangle,
  Sparkles,
  CheckSquare,
  Square,
  X,
} from 'lucide-vue-next'
import { useToast } from '../composables/useToast'
import { useTerminalDrawer } from '../composables/useTerminalDrawer'
import { formatBytes } from '../composables/useFormatters'

const { notify } = useToast()
const { showActionOutput } = useTerminalDrawer()

const activeTab = ref('apt')
const searchQuery = ref('')
const loading = ref(false)
const packagesData = ref({
  apt: [],
  snap: [],
  npm: [],
  pip: [],
  manual: [],
})

const modalOpen = ref(false)
const targetPkg = ref(null)
const scanningOrphans = ref(false)
const orphanFolders = ref([])
const selectedOrphans = ref(new Set())
const uninstalling = ref(false)

const tabs = [
  { id: 'apt', label: 'APT', icon: Package, badgeColor: 'text-emerald-400' },
  { id: 'snap', label: 'Snap', icon: Layers, badgeColor: 'text-cyan-400' },
  { id: 'npm', label: 'NPM Global', icon: FileCode2, badgeColor: 'text-amber-400' },
  { id: 'pip', label: 'Pip / Pipx', icon: Terminal, badgeColor: 'text-cyan-400' },
  { id: 'manual', label: 'AppImages & /opt', icon: FolderCog, badgeColor: 'text-emerald-400' },
]

const currentList = computed(() => {
  const list = packagesData.value[activeTab.value] || []
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return list
  return list.filter(
    (item) =>
      (item.name && item.name.toLowerCase().includes(q)) ||
      (item.version && item.version.toLowerCase().includes(q)) ||
      (item.description && item.description.toLowerCase().includes(q)) ||
      (item.path && item.path.toLowerCase().includes(q))
  )
})

const totalMatchAcrossTabs = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  const counts = {}
  for (const t of tabs) {
    const arr = packagesData.value[t.id] || []
    if (!q) {
      counts[t.id] = arr.length
    } else {
      counts[t.id] = arr.filter(
        (item) =>
          (item.name && item.name.toLowerCase().includes(q)) ||
          (item.version && item.version.toLowerCase().includes(q)) ||
          (item.description && item.description.toLowerCase().includes(q)) ||
          (item.path && item.path.toLowerCase().includes(q))
      ).length
    }
  }
  return counts
})

async function fetchAllPackages() {
  loading.value = true
  try {
    const res = await fetch('/api/packages/list')
    const data = await res.json()
    packagesData.value = {
      apt: data.apt || [],
      snap: data.snap || [],
      npm: data.npm || [],
      pip: data.pip || [],
      manual: data.manual || [],
    }
  } catch (err) {
    notify({ title: 'Package Scan Error', message: String(err), type: 'error' })
  } finally {
    loading.value = false
  }
}

async function openUninstallModal(pkg) {
  targetPkg.value = pkg
  modalOpen.value = true
  orphanFolders.value = []
  selectedOrphans.value = new Set()
  scanningOrphans.value = true

  try {
    const res = await fetch(`/api/packages/orphans?app_name=${encodeURIComponent(pkg.name)}`)
    const data = await res.json()
    orphanFolders.value = data.orphans || []
    selectedOrphans.value = new Set(orphanFolders.value.map((o) => o.path))
  } catch {
    orphanFolders.value = []
  } finally {
    scanningOrphans.value = false
  }
}

function toggleOrphanSelect(path) {
  const next = new Set(selectedOrphans.value)
  if (next.has(path)) {
    next.delete(path)
  } else {
    next.add(path)
  }
  selectedOrphans.value = next
}

async function confirmUninstall() {
  if (!targetPkg.value) return
  uninstalling.value = true
  try {
    const payload = {
      manager: targetPkg.value.manager,
      name: targetPkg.value.name,
      revision: targetPkg.value.revision || null,
      path: targetPkg.value.path || null,
      purge_orphans: selectedOrphans.value.size > 0,
      orphan_paths: Array.from(selectedOrphans.value),
    }

    const res = await fetch('/api/packages/uninstall', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const data = await res.json()
    notify({
      title: data.success ? 'Uninstall Complete' : 'Uninstall Error',
      message: data.message,
      type: data.success ? 'success' : 'error',
    })
    if (data.stdout || data.stderr) {
      showActionOutput({
        title: `Uninstall ${targetPkg.value.name}`,
        command: `${targetPkg.value.manager} remove ${targetPkg.value.name}`,
        stdout: data.stdout || data.message,
        stderr: data.stderr,
        success: data.success,
      })
    }
    if (data.success) {
      modalOpen.value = false
      await fetchAllPackages()
    }
  } catch (err) {
    notify({ title: 'Uninstall Request Failed', message: String(err), type: 'error' })
  } finally {
    uninstalling.value = false
  }
}

onMounted(() => {
  fetchAllPackages()
})
</script>

<template>
  <div class="space-y-5">
    <!-- Top Tabs & Unified Search Bar -->
    <div class="flex flex-col md:flex-row md:items-center justify-between gap-3">
      <!-- Navigation Tabs -->
      <div class="flex flex-wrap items-center gap-1.5">
        <button
          v-for="t in tabs"
          :key="t.id"
          @click="activeTab = t.id"
          class="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium border transition-all cursor-pointer"
          :class="
            activeTab === t.id
              ? 'bg-[#121215] text-zinc-100 border-white/15'
              : 'bg-transparent text-zinc-500 border-transparent hover:text-zinc-300 hover:bg-white/[0.03]'
          "
        >
          <component :is="t.icon" class="w-3.5 h-3.5" :class="activeTab === t.id ? t.badgeColor : 'text-zinc-500'" />
          <span>{{ t.label }}</span>
          <span
            class="px-1.5 py-0.2 text-[10px] font-mono tabular-nums rounded bg-white/[0.04] text-zinc-400"
          >
            {{ totalMatchAcrossTabs[t.id] ?? 0 }}
          </span>
        </button>
      </div>

      <div class="flex items-center gap-2">
        <div class="relative">
          <Search class="w-3.5 h-3.5 text-zinc-500 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            v-model="searchQuery"
            type="text"
            placeholder="Filter packages..."
            class="pl-8 pr-3 py-1.5 text-xs rounded-lg bg-[#121215] border border-white/[0.07] text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-white/20 w-60"
          />
        </div>
        <button
          @click="fetchAllPackages"
          :disabled="loading"
          class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-[#121215] hover:bg-white/[0.06] text-zinc-300 border border-white/[0.07] transition-colors cursor-pointer"
        >
          <RefreshCw class="w-3.5 h-3.5" :class="{ 'animate-spin': loading }" />
          <span>Rescan</span>
        </button>
      </div>
    </div>

    <!-- Package Table Card -->
    <div class="glass-panel rounded-xl p-5">
      <div v-if="loading" class="py-12 text-center text-xs text-zinc-500 font-mono">
        Scanning installed system packages...
      </div>

      <div v-else-if="currentList.length === 0" class="py-12 text-center text-xs text-zinc-500 font-mono">
        No matching packages found.
      </div>

      <div v-else class="overflow-x-auto">
        <table class="w-full text-left border-collapse">
          <thead>
            <tr class="border-b border-white/[0.05] text-[11px] font-medium uppercase tracking-wider text-zinc-500">
              <th class="py-2.5 px-3 font-medium">Package</th>
              <th class="py-2.5 px-3 font-medium">Version</th>
              <th class="py-2.5 px-3 font-medium">Details</th>
              <th class="py-2.5 px-3 font-medium text-right">Size</th>
              <th class="py-2.5 px-3 font-medium text-right">Action</th>
            </tr>
          </thead>
          <tbody class="text-xs">
            <tr
              v-for="(pkg, idx) in currentList"
              :key="`${pkg.name}-${pkg.revision || idx}`"
              class="hover:bg-white/[0.03] transition-colors group"
            >
              <td class="py-2.5 px-3 rounded-l-lg">
                <div class="flex items-center gap-2">
                  <span class="font-medium text-zinc-100">{{ pkg.name }}</span>
                  <span
                    v-if="pkg.disabled"
                    class="px-1.5 py-0.2 text-[10px] font-mono rounded bg-amber-500/10 text-amber-300 border border-amber-500/25"
                  >
                    disabled
                  </span>
                </div>
              </td>
              <td class="py-2.5 px-3 font-mono tabular-nums text-cyan-400">
                {{ pkg.version }}
                <span v-if="pkg.revision" class="text-zinc-500">({{ pkg.revision }})</span>
              </td>
              <td class="py-2.5 px-3 text-zinc-500 max-w-md truncate" :title="pkg.description || pkg.path">
                <template v-if="pkg.path">
                  <span class="font-mono text-zinc-400">{{ pkg.path }}</span>
                </template>
                <template v-else-if="pkg.publisher">
                  {{ pkg.publisher }} · {{ pkg.tracking }}
                </template>
                <template v-else>
                  {{ pkg.description || pkg.section || 'Explicitly installed' }}
                </template>
              </td>
              <td class="py-2.5 px-3 font-mono tabular-nums text-right text-emerald-400">
                {{ pkg.size_bytes ? formatBytes(pkg.size_bytes) : '—' }}
              </td>
              <td class="py-2.5 px-3 text-right rounded-r-lg">
                <button
                  @click="openUninstallModal(pkg)"
                  class="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-rose-500/10 hover:bg-rose-500/25 text-rose-300 border border-rose-500/20 transition-colors cursor-pointer text-[11px]"
                >
                  <Trash2 class="w-3 h-3" />
                  <span>Uninstall</span>
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Uninstall & Orphan Config Deep Clean Modal -->
    <Transition name="fade-slide">
      <div
        v-if="modalOpen && targetPkg"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-xs p-4"
        @click.self="modalOpen = false"
      >
        <div class="w-full max-w-lg rounded-xl bg-[#121215] border border-white/10 shadow-2xl overflow-hidden">
          <div class="px-5 py-3.5 border-b border-white/[0.06] flex items-center justify-between">
            <div class="flex items-center gap-2">
              <AlertTriangle class="w-4 h-4 text-rose-400" />
              <h3 class="text-xs font-semibold uppercase tracking-wider text-zinc-100">
                Uninstall {{ targetPkg.name }}
              </h3>
            </div>
            <button
              @click="modalOpen = false"
              class="text-zinc-500 hover:text-zinc-200 p-1 rounded-lg"
            >
              <X class="w-4 h-4" />
            </button>
          </div>

          <div class="p-5 space-y-4 text-xs">
            <p class="text-zinc-400 leading-relaxed">
              Remove <strong class="text-zinc-100 font-mono">{{ targetPkg.name }}</strong>
              <span v-if="targetPkg.revision"> (rev {{ targetPkg.revision }})</span>
              via <span class="uppercase font-mono text-cyan-400">{{ targetPkg.manager }}</span>.
            </p>

            <!-- Orphan config scanner section -->
            <div class="rounded-lg bg-[#09090B] border border-white/[0.06] p-3.5 space-y-2.5">
              <div class="flex items-center justify-between">
                <span class="font-medium text-zinc-300 flex items-center gap-1.5">
                  <Sparkles class="w-3.5 h-3.5 text-emerald-400" />
                  Associated Config & Cache Folders
                </span>
                <span v-if="scanningOrphans" class="text-cyan-400 font-mono text-[11px]">Scanning...</span>
              </div>

              <div v-if="!scanningOrphans && orphanFolders.length === 0" class="text-zinc-500 font-mono text-[11px]">
                No leftover user folders found.
              </div>

              <div v-else class="space-y-1.5 max-h-44 overflow-y-auto">
                <div
                  v-for="item in orphanFolders"
                  :key="item.path"
                  @click="toggleOrphanSelect(item.path)"
                  class="flex items-center justify-between p-2 rounded-md border cursor-pointer transition-colors"
                  :class="
                    selectedOrphans.has(item.path)
                      ? 'bg-emerald-500/10 border-emerald-500/25 text-zinc-100'
                      : 'bg-white/[0.02] border-white/[0.05] text-zinc-500'
                  "
                >
                  <div class="flex items-center gap-2 min-w-0">
                    <component
                      :is="selectedOrphans.has(item.path) ? CheckSquare : Square"
                      class="w-3.5 h-3.5 shrink-0"
                      :class="selectedOrphans.has(item.path) ? 'text-emerald-400' : 'text-zinc-600'"
                    />
                    <span class="font-mono text-[11px] truncate">{{ item.path }}</span>
                  </div>
                  <span class="font-mono tabular-nums text-emerald-400 shrink-0 ml-2">
                    {{ formatBytes(item.size_bytes) }}
                  </span>
                </div>
              </div>
            </div>
          </div>

          <div class="px-5 py-3 bg-[#09090B] border-t border-white/[0.06] flex items-center justify-end gap-2">
            <button
              @click="modalOpen = false"
              class="px-3.5 py-1.5 rounded-lg text-xs font-medium bg-white/[0.04] hover:bg-white/[0.08] text-zinc-300 cursor-pointer"
            >
              Cancel
            </button>
            <button
              @click="confirmUninstall"
              :disabled="uninstalling"
              class="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-medium bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 border border-rose-500/30 cursor-pointer disabled:opacity-50"
            >
              <Trash2 class="w-3.5 h-3.5" />
              <span>
                {{
                  uninstalling
                    ? 'Removing...'
                    : selectedOrphans.size > 0
                    ? `Uninstall + Purge (${selectedOrphans.size})`
                    : 'Uninstall'
                }}
              </span>
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>
