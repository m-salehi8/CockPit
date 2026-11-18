<script setup>
import { ref, computed, onMounted } from 'vue'
import {
  Terminal,
  Play,
  Plus,
  Edit3,
  Trash2,
  Shield,
  Globe,
  RefreshCw,
  Activity,
  Lock,
  GitBranch,
  Smartphone,
  Cpu,
  BarChart2,
  AlertTriangle,
  Zap,
  Container,
  HardDrive,
  X,
} from 'lucide-vue-next'
import { useToast } from '../composables/useToast'
import { useTerminalDrawer } from '../composables/useTerminalDrawer'

const { notify } = useToast()
const { drawerState, openDrawer, runCommandStream } = useTerminalDrawer()

const commands = ref([])
const activeCategory = ref('All')
const loading = ref(false)

const modalOpen = ref(false)
const form = ref({
  id: null,
  title: '',
  category: 'Custom',
  description: '',
  command: '',
  requires_root: false,
  icon: 'terminal',
})

const categories = computed(() => {
  const set = new Set(['All'])
  for (const c of commands.value) {
    if (c.category) set.add(c.category)
  }
  return Array.from(set)
})

const filteredCommands = computed(() => {
  if (activeCategory.value === 'All') return commands.value
  return commands.value.filter((c) => c.category === activeCategory.value)
})

function getCardIcon(name) {
  const map = {
    globe: Globe,
    shield: Shield,
    'refresh-cw': RefreshCw,
    activity: Activity,
    lock: Lock,
    'git-branch': GitBranch,
    smartphone: Smartphone,
    cpu: Cpu,
    'bar-chart-2': BarChart2,
    'alert-triangle': AlertTriangle,
    zap: Zap,
    container: Container,
    'hard-drive': HardDrive,
    terminal: Terminal,
  }
  return map[name] || Terminal
}

async function fetchCommands() {
  loading.value = true
  try {
    const res = await fetch('/api/commands')
    const data = await res.json()
    commands.value = data.commands || []
  } catch (err) {
    notify({ title: 'Failed to Load Commands', message: String(err), type: 'error' })
  } finally {
    loading.value = false
  }
}

function runCard(card) {
  runCommandStream({
    id: card.id,
    title: card.title,
    command: card.command,
    requires_root: card.requires_root,
  })
}

function openCreateModal() {
  form.value = {
    id: null,
    title: '',
    category: 'Custom',
    description: '',
    command: '',
    requires_root: false,
    icon: 'terminal',
  }
  modalOpen.value = true
}

function openEditModal(card) {
  form.value = { ...card }
  modalOpen.value = true
}

async function saveCommandCard() {
  if (!form.value.title.trim() || !form.value.command.trim()) {
    notify({ title: 'Validation Error', message: 'Title and bash command are required.', type: 'warning' })
    return
  }

  try {
    const res = await fetch('/api/commands/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form.value),
    })
    const data = await res.json()
    commands.value = data.commands || []
    modalOpen.value = false
    notify({ title: 'Command Saved', message: data.message, type: 'success' })
  } catch (err) {
    notify({ title: 'Save Failed', message: String(err), type: 'error' })
  }
}

async function deleteCommandCard(card) {
  try {
    const res = await fetch(`/api/commands/${encodeURIComponent(card.id)}`, {
      method: 'DELETE',
    })
    const data = await res.json()
    commands.value = data.commands || []
    notify({ title: 'Command Removed', message: `Removed '${card.title}'.`, type: 'info' })
  } catch (err) {
    notify({ title: 'Delete Failed', message: String(err), type: 'error' })
  }
}

onMounted(() => {
  fetchCommands()
})
</script>

<template>
  <div class="space-y-5">
    <!-- Minimal Header Bar -->
    <div class="flex flex-wrap items-center justify-between gap-3">
      <!-- Category Pills -->
      <div class="flex flex-wrap items-center gap-1.5">
        <button
          v-for="cat in categories"
          :key="cat"
          @click="activeCategory = cat"
          class="px-3 py-1.5 rounded-lg text-xs font-medium border transition-all cursor-pointer"
          :class="
            activeCategory === cat
              ? 'bg-[#121215] text-zinc-100 border-white/15'
              : 'bg-transparent text-zinc-500 border-transparent hover:text-zinc-300 hover:bg-white/[0.03]'
          "
        >
          {{ cat }}
        </button>
      </div>

      <div class="flex items-center gap-2">
        <button
          v-if="drawerState.command"
          @click="openDrawer"
          class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-[#121215] hover:bg-white/[0.05] text-cyan-400 border border-white/[0.07] cursor-pointer"
        >
          <Terminal class="w-3.5 h-3.5" />
          <span>Terminal Output</span>
        </button>

        <button
          @click="openCreateModal"
          class="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-medium bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-300 border border-emerald-500/30 transition-colors cursor-pointer"
        >
          <Plus class="w-3.5 h-3.5" />
          <span>New Command</span>
        </button>
      </div>
    </div>

    <!-- Command Cards Bento Grid -->
    <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
      <div
        v-for="card in filteredCommands"
        :key="card.id"
        class="glass-card rounded-xl p-5 flex flex-col justify-between group"
      >
        <div>
          <div class="flex items-start justify-between gap-3">
            <div class="flex items-center gap-2.5">
              <div class="p-2 rounded-lg bg-white/[0.03] border border-white/[0.06] text-emerald-400">
                <component :is="getCardIcon(card.icon)" class="w-4 h-4" />
              </div>
              <div>
                <span class="text-[10px] font-mono uppercase tracking-wider text-zinc-500">
                  {{ card.category }}
                </span>
                <h3 class="text-xs font-semibold text-zinc-100 leading-snug">{{ card.title }}</h3>
              </div>
            </div>

            <span
              v-if="card.requires_root"
              class="px-1.5 py-0.5 text-[10px] font-mono rounded bg-amber-500/10 text-amber-300 border border-amber-500/25 flex items-center gap-1 shrink-0"
              title="Executes via PolicyKit (pkexec)"
            >
              <Shield class="w-2.5 h-2.5" /> root
            </span>
          </div>

          <p v-if="card.description" class="text-xs text-zinc-400 mt-3 leading-relaxed">
            {{ card.description }}
          </p>

          <div class="mt-3 p-2.5 rounded-lg bg-[#09090B] border border-white/[0.05] font-mono text-[11px] text-zinc-400 line-clamp-2 break-all">
            $ {{ card.command }}
          </div>
        </div>

        <div class="mt-4 pt-3 border-t border-white/[0.05] flex items-center justify-between gap-2">
          <div class="flex items-center gap-1 opacity-75 group-hover:opacity-100 transition-opacity">
            <button
              @click="openEditModal(card)"
              class="p-1.5 rounded-md text-zinc-500 hover:text-zinc-200 hover:bg-white/[0.05] transition-colors cursor-pointer"
              title="Edit"
            >
              <Edit3 class="w-3.5 h-3.5" />
            </button>
            <button
              @click="deleteCommandCard(card)"
              class="p-1.5 rounded-md text-zinc-500 hover:text-rose-400 hover:bg-rose-500/10 transition-colors cursor-pointer"
              title="Delete"
            >
              <Trash2 class="w-3.5 h-3.5" />
            </button>
          </div>

          <button
            @click="runCard(card)"
            class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-white/[0.04] hover:bg-emerald-500/15 text-zinc-200 hover:text-emerald-300 border border-white/[0.07] hover:border-emerald-500/30 transition-all cursor-pointer"
          >
            <Play class="w-3 h-3 text-emerald-400" />
            <span>Run</span>
          </button>
        </div>
      </div>
    </div>

    <!-- Create / Edit Command Modal -->
    <Transition name="fade-slide">
      <div
        v-if="modalOpen"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-xs p-4"
        @click.self="modalOpen = false"
      >
        <div class="w-full max-w-lg rounded-xl bg-[#121215] border border-white/10 shadow-2xl overflow-hidden">
          <div class="px-5 py-3.5 border-b border-white/[0.06] flex items-center justify-between">
            <h3 class="text-xs font-semibold uppercase tracking-wider text-zinc-200">
              {{ form.id ? 'Edit Command' : 'New Command' }}
            </h3>
            <button @click="modalOpen = false" class="text-zinc-500 hover:text-zinc-200 p-1">
              <X class="w-4 h-4" />
            </button>
          </div>

          <div class="p-5 space-y-4 text-xs">
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label class="block text-zinc-400 mb-1 font-medium">Title</label>
                <input
                  v-model="form.title"
                  type="text"
                  placeholder="e.g. Flush DNS Cache"
                  class="w-full px-3 py-2 rounded-lg bg-[#09090B] border border-white/[0.08] text-zinc-100 focus:outline-none focus:border-white/25"
                />
              </div>
              <div>
                <label class="block text-zinc-400 mb-1 font-medium">Category</label>
                <input
                  v-model="form.category"
                  type="text"
                  placeholder="Network & DNS"
                  class="w-full px-3 py-2 rounded-lg bg-[#09090B] border border-white/[0.08] text-zinc-100 focus:outline-none focus:border-white/25"
                />
              </div>
            </div>

            <div>
              <label class="block text-zinc-400 mb-1 font-medium">Description</label>
              <input
                v-model="form.description"
                type="text"
                placeholder="Brief summary"
                class="w-full px-3 py-2 rounded-lg bg-[#09090B] border border-white/[0.08] text-zinc-100 focus:outline-none focus:border-white/25"
              />
            </div>

            <div>
              <label class="block text-zinc-400 mb-1 font-medium">Bash Command</label>
              <textarea
                v-model="form.command"
                rows="3"
                placeholder="resolvectl flush-caches"
                class="w-full px-3 py-2 rounded-lg bg-[#09090B] border border-white/[0.08] text-zinc-100 font-mono focus:outline-none focus:border-white/25"
              />
            </div>

            <div class="flex items-center justify-between pt-1">
              <label class="inline-flex items-center gap-2 cursor-pointer text-zinc-300">
                <input
                  v-model="form.requires_root"
                  type="checkbox"
                  class="rounded border-white/15 bg-[#09090B] text-emerald-500"
                />
                <span>Run as root via <code class="text-amber-300 font-mono">pkexec</code></span>
              </label>
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
              @click="saveCommandCard"
              class="px-3.5 py-1.5 rounded-lg text-xs font-medium bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/30 cursor-pointer"
            >
              Save Command
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>
