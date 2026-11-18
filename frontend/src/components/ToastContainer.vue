<script setup>
import { CheckCircle2, AlertTriangle, XCircle, Info, X } from 'lucide-vue-next'
import { useToast } from '../composables/useToast'

const { toasts, dismiss } = useToast()

function getIcon(type) {
  if (type === 'success') return CheckCircle2
  if (type === 'warning') return AlertTriangle
  if (type === 'error') return XCircle
  return Info
}

function getColors(type) {
  if (type === 'success') return 'border-emerald-500/30 bg-[#121215]/95 text-emerald-400'
  if (type === 'warning') return 'border-amber-500/30 bg-[#121215]/95 text-amber-400'
  if (type === 'error') return 'border-rose-500/30 bg-[#121215]/95 text-rose-400'
  return 'border-cyan-500/30 bg-[#121215]/95 text-cyan-400'
}
</script>

<template>
  <div class="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm w-full pointer-events-none">
    <TransitionGroup name="fade-slide">
      <div
        v-for="t in toasts"
        :key="t.id"
        class="pointer-events-auto flex items-start gap-2.5 p-3 rounded-lg border shadow-2xl backdrop-blur-md"
        :class="getColors(t.type)"
      >
        <component :is="getIcon(t.type)" class="w-4 h-4 shrink-0 mt-0.5" />
        <div class="flex-1 min-w-0">
          <p class="text-xs font-semibold text-zinc-100">{{ t.title }}</p>
          <p v-if="t.message" class="text-[11px] text-zinc-400 mt-0.5 break-words leading-relaxed">
            {{ t.message }}
          </p>
        </div>
        <button
          @click="dismiss(t.id)"
          class="text-zinc-500 hover:text-zinc-300 p-0.5 rounded transition-colors cursor-pointer"
        >
          <X class="w-3.5 h-3.5" />
        </button>
      </div>
    </TransitionGroup>
  </div>
</template>
