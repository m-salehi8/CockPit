<script setup>
import { ref, watch, nextTick } from 'vue'
import { Terminal, X, CheckCircle2, XCircle, Loader2, Copy, Trash2 } from 'lucide-vue-next'
import { useToast } from '../composables/useToast'

const props = defineProps({
  open: Boolean,
  title: String,
  command: String,
  lines: Array,
  running: Boolean,
  exitCode: Number,
  durationMs: Number,
})

const emit = defineEmits(['close', 'clear'])
const { notify } = useToast()
const outputBox = ref(null)

watch(
  () => props.lines?.length,
  async () => {
    await nextTick()
    if (outputBox.value) {
      outputBox.value.scrollTop = outputBox.value.scrollHeight
    }
  }
)

function copyOutput() {
  const text = (props.lines || []).map((l) => l.text).join('')
  navigator.clipboard.writeText(text)
  notify({ title: 'Copied to Clipboard', message: 'Terminal output copied.', type: 'success' })
}
</script>

<template>
  <Transition name="fade-slide">
    <div
      v-if="open"
      class="fixed inset-0 z-40 flex justify-end bg-black/60 backdrop-blur-xs"
      @click.self="emit('close')"
    >
      <div class="w-full max-w-2xl bg-[#09090B] border-l border-white/10 h-full flex flex-col shadow-2xl">
        <!-- Drawer Header -->
        <div class="px-5 py-3.5 border-b border-white/[0.06] flex items-center justify-between bg-[#121215]">
          <div class="flex items-center gap-2.5 min-w-0">
            <div class="p-1.5 rounded-md bg-white/[0.04] border border-white/[0.08] text-emerald-400">
              <Terminal class="w-3.5 h-3.5" />
            </div>
            <div class="min-w-0">
              <h3 class="text-xs font-semibold text-zinc-100 truncate">
                {{ title || 'Terminal Output' }}
              </h3>
              <p class="text-[11px] font-mono text-zinc-500 truncate mt-0.5">$ {{ command }}</p>
            </div>
          </div>

          <div class="flex items-center gap-1.5">
            <button
              @click="copyOutput"
              class="p-1.5 rounded-md text-zinc-500 hover:text-zinc-200 hover:bg-white/[0.06] transition-colors cursor-pointer"
              title="Copy Output"
            >
              <Copy class="w-3.5 h-3.5" />
            </button>
            <button
              @click="emit('clear')"
              class="p-1.5 rounded-md text-zinc-500 hover:text-zinc-200 hover:bg-white/[0.06] transition-colors cursor-pointer"
              title="Clear Output"
            >
              <Trash2 class="w-3.5 h-3.5" />
            </button>
            <button
              @click="emit('close')"
              class="p-1.5 rounded-md text-zinc-500 hover:text-zinc-200 hover:bg-white/[0.06] transition-colors cursor-pointer"
            >
              <X class="w-4 h-4" />
            </button>
          </div>
        </div>

        <!-- Status Bar -->
        <div class="px-5 py-2 bg-[#0c0c0e] border-b border-white/[0.05] flex items-center justify-between text-[11px]">
          <div class="flex items-center gap-2">
            <span v-if="running" class="inline-flex items-center gap-1.5 text-cyan-400 font-medium">
              <Loader2 class="w-3 h-3 animate-spin" />
              Running...
            </span>
            <span
              v-else-if="exitCode === 0"
              class="inline-flex items-center gap-1.5 text-emerald-400 font-medium"
            >
              <CheckCircle2 class="w-3 h-3" />
              Exit 0
            </span>
            <span
              v-else-if="exitCode !== null && exitCode !== undefined"
              class="inline-flex items-center gap-1.5 text-rose-400 font-medium"
            >
              <XCircle class="w-3 h-3" />
              Exit {{ exitCode }}
            </span>
          </div>
          <span v-if="durationMs !== null && !running" class="text-zinc-500 font-mono tabular-nums">
            {{ durationMs }} ms
          </span>
        </div>

        <!-- Terminal Console Stream -->
        <div
          ref="outputBox"
          class="flex-1 p-5 overflow-y-auto font-mono text-xs leading-relaxed bg-[#09090B] text-zinc-200 select-text"
        >
          <div v-if="!lines || lines.length === 0" class="text-zinc-600">
            Waiting for output stream...
          </div>
          <div
            v-for="(item, idx) in lines"
            :key="idx"
            class="whitespace-pre-wrap break-all"
            :class="{
              'text-rose-400': item.stream === 'stderr',
              'text-emerald-400 font-medium': item.stream === 'meta',
              'text-zinc-200': item.stream === 'stdout',
            }"
          >{{ item.text }}</div>
        </div>
      </div>
    </div>
  </Transition>
</template>
