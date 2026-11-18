<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import * as echarts from 'echarts'
import {
  Cpu,
  MemoryStick,
  HardDrive,
  Wifi,
  BatteryCharging,
  Thermometer,
  Zap,
  RefreshCw,
  Skull,
  ChevronDown,
  ChevronRight,
  Search,
  Sparkles,
  Flame,
  Activity,
  Terminal,
  ShieldAlert,
  Bell,
  Trash2,
} from 'lucide-vue-next'
import { useMetricsStream } from '../composables/useMetricsStream'
import { useToast } from '../composables/useToast'
import { useTerminalDrawer } from '../composables/useTerminalDrawer'
import { formatBytes, formatRate, formatUptime } from '../composables/useFormatters'

const { latest, history } = useMetricsStream()
const { notify } = useToast()
const { showActionOutput } = useTerminalDrawer()

const chartEl = ref(null)
let chartInstance = null

const processGroups = ref([])
const totalProcesses = ref(0)
const loadingProcs = ref(false)
const procSearch = ref('')
const expandedGroups = ref(new Set())
const busyAction = ref('')

// Guard Policies & Notification Engine state
const guardRules = ref([])
const alertsLog = ref([])
const guardActive = ref(true)
const testingNotification = ref(false)
const savingPolicy = ref(false)
let policyPollTimer = null

async function fetchGuardPolicies() {
  try {
    const res = await fetch('/api/system/policies')
    const data = await res.json()
    guardRules.value = data.rules || []
    alertsLog.value = data.alerts_log || []
    guardActive.value = Boolean(data.monitor_active)
  } catch {
    // Non-fatal on initial load
  }
}

async function updatePolicyRule(ruleId, patch) {
  // Optimistic local update
  const target = guardRules.value.find((r) => r.id === ruleId)
  if (target) {
    Object.assign(target, patch)
  }
  savingPolicy.value = true
  try {
    const res = await fetch('/api/system/policies', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        policies: {
          [ruleId]: patch,
        },
      }),
    })
    const data = await res.json()
    guardRules.value = data.rules || guardRules.value
    alertsLog.value = data.alerts_log || alertsLog.value
  } catch (err) {
    notify({ title: 'Policy Save Failed', message: String(err), type: 'error' })
  } finally {
    savingPolicy.value = false
  }
}

async function handleTestNotification() {
  if (testingNotification.value) return
  testingNotification.value = true
  try {
    const res = await fetch('/api/system/policies/test-notification', { method: 'POST' })
    const data = await res.json()
    if (data.state) {
      guardRules.value = data.state.rules || guardRules.value
      alertsLog.value = data.state.alerts_log || alertsLog.value
    }
    notify({
      title: data.success ? 'Desktop Notification Sent' : 'Notification Dispatched',
      message: data.message || 'Check your Ubuntu GNOME notification banner.',
      type: 'success',
    })
  } catch (err) {
    notify({ title: 'Notification Error', message: String(err), type: 'error' })
  } finally {
    testingNotification.value = false
  }
}

async function handleClearAlerts() {
  try {
    const res = await fetch('/api/system/policies/clear-logs', { method: 'POST' })
    const data = await res.json()
    alertsLog.value = data.alerts_log || []
  } catch (err) {
    notify({ title: 'Clear Alerts Error', message: String(err), type: 'error' })
  }
}

// SVG circular ring helper (r = 16, circumference ≈ 100.53)
const RING_CIRCUMFERENCE = 2 * Math.PI * 16

function ringDashOffset(percent) {
  const clamped = Math.max(0, Math.min(100, Number(percent) || 0))
  return RING_CIRCUMFERENCE - (clamped / 100) * RING_CIRCUMFERENCE
}

const filteredGroups = computed(() => {
  const q = procSearch.value.trim().toLowerCase()
  if (!q) return processGroups.value
  return processGroups.value.filter(
    (g) =>
      g.group_name.toLowerCase().includes(q) ||
      g.base_executable.toLowerCase().includes(q) ||
      g.user.toLowerCase().includes(q) ||
      g.pids.some((p) => String(p).includes(q))
  )
})

function toggleGroupExpand(groupName) {
  const next = new Set(expandedGroups.value)
  if (next.has(groupName)) {
    next.delete(groupName)
  } else {
    next.add(groupName)
  }
  expandedGroups.value = next
}

async function fetchGroupedProcesses() {
  loadingProcs.value = true
  try {
    const res = await fetch('/api/system/processes?limit=45')
    const data = await res.json()
    processGroups.value = data.groups || []
    totalProcesses.value = data.total_process_count || 0
  } catch (err) {
    notify({ title: 'Failed to Load Processes', message: String(err), type: 'error' })
  } finally {
    loadingProcs.value = false
  }
}

async function killProcessGroup(pids, label, force = false) {
  busyAction.value = `kill-${label}`
  const sigLabel = force ? 'SIGKILL (-9)' : 'SIGTERM (-15)'
  try {
    const res = await fetch('/api/system/processes/kill', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pids, force }),
    })
    const data = await res.json()
    notify({
      title: data.success ? `${force ? 'Killed' : 'Terminated'} ${label}` : 'Process Signal Error',
      message: data.message || (data.errors || []).join('; '),
      type: data.success ? 'success' : 'error',
    })
    if ((data.errors && data.errors.length > 0) || data.killed_pids?.length > 0) {
      showActionOutput({
        title: `${force ? 'Kill' : 'Terminate'} ${label}`,
        command: `kill ${force ? '-9' : '-15'} ${pids.slice(0, 12).join(' ')}${pids.length > 12 ? ' ...' : ''}`,
        stdout: `${data.message}\nSignaled PIDs (${sigLabel}): ${(data.killed_pids || []).join(', ') || 'none'}`,
        stderr: (data.errors || []).join('\n'),
        success: data.success,
      })
    }
    await fetchGroupedProcesses()
  } catch (err) {
    notify({ title: 'Kill Error', message: String(err), type: 'error' })
  } finally {
    busyAction.value = ''
  }
}

async function handleDropCaches() {
  busyAction.value = 'drop-caches'
  try {
    const res = await fetch('/api/system/rescue/drop-caches', { method: 'POST' })
    const data = await res.json()
    notify({
      title: data.success ? 'Memory Caches Dropped' : 'Cache Drop Cancelled',
      message: data.message,
      type: data.success ? 'success' : 'warning',
    })
    showActionOutput({
      title: 'Drop Kernel Memory Caches',
      command: "pkexec sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'",
      stdout: data.message,
      stderr: data.stderr,
      success: data.success,
    })
  } catch (err) {
    notify({ title: 'Drop Caches Error', message: String(err), type: 'error' })
  } finally {
    busyAction.value = ''
  }
}

async function handleSwapRefresh() {
  busyAction.value = 'swap-refresh'
  try {
    const res = await fetch('/api/system/rescue/swap-refresh', { method: 'POST' })
    const data = await res.json()
    notify({
      title: data.success ? 'Swap Refreshed' : 'Swap Refresh Skipped',
      message: data.message,
      type: data.success ? 'success' : 'warning',
    })
    if (data.stdout || data.stderr) {
      showActionOutput({
        title: 'Swap Refresh',
        command: "pkexec sh -c 'swapoff -a && swapon -a'",
        stdout: data.stdout || data.message,
        stderr: data.stderr,
        success: data.success,
      })
    }
  } catch (err) {
    notify({ title: 'Swap Refresh Error', message: String(err), type: 'error' })
  } finally {
    busyAction.value = ''
  }
}

async function handleToggleFocusMode() {
  const currentState = Boolean(latest.value?.focus_mode_active)
  busyAction.value = 'focus-mode'
  try {
    const res = await fetch('/api/system/rescue/focus-mode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enable: !currentState }),
    })
    const data = await res.json()
    notify({
      title: data.success
        ? data.focus_mode_active
          ? 'Dev Focus Mode Activated'
          : 'Dev Focus Mode Restored'
        : 'Dev Focus Mode Failed',
      message: data.message,
      type: data.success ? 'success' : 'error',
    })
    await fetchGroupedProcesses()
  } catch (err) {
    notify({ title: 'Focus Mode Error', message: String(err), type: 'error' })
  } finally {
    busyAction.value = ''
  }
}

async function handleEnableZram() {
  busyAction.value = 'enable-zram'
  try {
    const res = await fetch('/api/system/rescue/enable-zram', { method: 'POST' })
    const data = await res.json()
    notify({
      title: data.success ? 'ZRAM Swap Enabled' : 'ZRAM Setup Cancelled',
      message: data.message,
      type: data.success ? 'success' : 'warning',
    })
    showActionOutput({
      title: 'Configure ZRAM Swap',
      command: 'pkexec modprobe zram && zramctl --find --size 50% && mkswap && swapon -p 100',
      stdout: data.stdout || data.message,
      stderr: data.stderr,
      success: data.success,
    })
  } catch (err) {
    notify({ title: 'ZRAM Error', message: String(err), type: 'error' })
  } finally {
    busyAction.value = ''
  }
}

function initChart() {
  if (!chartEl.value) return
  chartInstance = echarts.init(chartEl.value)
  chartInstance.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#121215',
      borderColor: 'rgba(255,255,255,0.08)',
      textStyle: { color: '#f4f4f5', fontSize: 11, fontFamily: 'JetBrains Mono' },
    },
    legend: {
      data: ['CPU %', 'RAM %', 'Swap %'],
      textStyle: { color: '#a1a1aa', fontSize: 11 },
      top: 0,
      right: 4,
      icon: 'circle',
      itemWidth: 7,
      itemHeight: 7,
    },
    grid: {
      left: 34,
      right: 12,
      top: 28,
      bottom: 20,
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: history.timestamps,
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
      axisLabel: { color: '#71717a', fontSize: 10, fontFamily: 'JetBrains Mono' },
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 100,
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.04)', type: 'dashed' } },
      axisLabel: { color: '#71717a', fontSize: 10, fontFamily: 'JetBrains Mono', formatter: '{value}%' },
    },
    series: [
      {
        name: 'CPU %',
        type: 'line',
        smooth: true,
        showSymbol: false,
        data: history.cpu,
        lineStyle: { width: 1.5, color: '#22d3ee' },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(34, 211, 238, 0.16)' },
            { offset: 1, color: 'rgba(34, 211, 238, 0.0)' },
          ]),
        },
      },
      {
        name: 'RAM %',
        type: 'line',
        smooth: true,
        showSymbol: false,
        data: history.ramPercent,
        lineStyle: { width: 1.8, color: '#34d399' },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(52, 211, 153, 0.18)' },
            { offset: 1, color: 'rgba(52, 211, 153, 0.0)' },
          ]),
        },
      },
      {
        name: 'Swap %',
        type: 'line',
        smooth: true,
        showSymbol: false,
        data: history.swapPercent,
        lineStyle: { width: 1.2, color: '#fbbf24', type: 'dashed' },
      },
    ],
  })
}

watch(
  () => latest.value?.timestamp,
  () => {
    if (!chartInstance) return
    chartInstance.setOption({
      xAxis: { data: [...history.timestamps] },
      series: [
        { data: [...history.cpu] },
        { data: [...history.ramPercent] },
        { data: [...history.swapPercent] },
      ],
    })
  }
)

function handleResize() {
  chartInstance?.resize()
}

onMounted(() => {
  initChart()
  fetchGroupedProcesses()
  fetchGuardPolicies()
  policyPollTimer = window.setInterval(fetchGuardPolicies, 6000)
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  if (policyPollTimer) {
    clearInterval(policyPollTimer)
  }
  window.removeEventListener('resize', handleResize)
  chartInstance?.dispose()
})
</script>

<template>
  <div class="space-y-5">
    <!-- Minimalist RAM Headroom & Quick Rescue Bar -->
    <div class="glass-panel rounded-xl p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
      <div class="flex items-center gap-3">
        <span
          class="w-2 h-2 rounded-full shrink-0"
          :class="{
            'bg-emerald-400': latest?.memory?.pressure_level === 'optimal' || !latest,
            'bg-amber-400': latest?.memory?.pressure_level === 'elevated',
            'bg-rose-500 animate-pulse': latest?.memory?.pressure_level === 'critical',
          }"
        />
        <span class="text-xs font-semibold text-zinc-100">8GB RAM Guard</span>
        <span
          class="px-2 py-0.5 text-[10px] font-mono uppercase tracking-wider rounded bg-white/[0.04] border border-white/[0.06]"
          :class="{
            'text-emerald-400': latest?.memory?.pressure_level === 'optimal' || !latest,
            'text-amber-400': latest?.memory?.pressure_level === 'elevated',
            'text-rose-400': latest?.memory?.pressure_level === 'critical',
          }"
        >
          {{ latest?.memory?.pressure_level || 'optimal' }}
        </span>
      </div>

      <!-- 3 Minimal Rescue Action Buttons -->
      <div class="flex flex-wrap items-center gap-2">
        <button
          @click="handleDropCaches"
          :disabled="busyAction === 'drop-caches'"
          class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-white/[0.03] hover:bg-emerald-500/15 text-zinc-200 hover:text-emerald-300 border border-white/[0.07] hover:border-emerald-500/30 transition-all cursor-pointer disabled:opacity-50"
          title="pkexec sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'"
        >
          <Sparkles class="w-3.5 h-3.5 text-emerald-400" />
          <span>{{ busyAction === 'drop-caches' ? 'Dropping...' : 'Drop Caches' }}</span>
        </button>

        <button
          @click="handleSwapRefresh"
          :disabled="busyAction === 'swap-refresh'"
          class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-white/[0.03] hover:bg-cyan-500/15 text-zinc-200 hover:text-cyan-300 border border-white/[0.07] hover:border-cyan-500/30 transition-all cursor-pointer disabled:opacity-50"
          title="Cycle swapoff -a && swapon -a"
        >
          <RefreshCw class="w-3.5 h-3.5 text-cyan-400" :class="{ 'animate-spin': busyAction === 'swap-refresh' }" />
          <span>{{ busyAction === 'swap-refresh' ? 'Cycling...' : 'Swap Refresh' }}</span>
        </button>

        <button
          @click="handleToggleFocusMode"
          :disabled="busyAction === 'focus-mode'"
          class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-all cursor-pointer disabled:opacity-50"
          :class="
            latest?.focus_mode_active
              ? 'bg-amber-500/15 text-amber-300 border-amber-500/35'
              : 'bg-white/[0.03] hover:bg-amber-500/10 text-zinc-200 hover:text-amber-300 border border-white/[0.07]'
          "
          title="Pause or restore heavy background daemons (docker, postgresql, redis, snapd)"
        >
          <Flame class="w-3.5 h-3.5 text-amber-400" />
          <span>
            {{
              busyAction === 'focus-mode'
                ? 'Switching...'
                : latest?.focus_mode_active
                ? 'Focus Mode: ON'
                : 'Dev Focus Mode'
            }}
          </span>
        </button>
      </div>
    </div>

    <!-- Primary Telemetry Bento Grid (p-5 cards, gap-5) -->
    <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-5">
      <!-- 1. CPU & Thermal Card -->
      <div class="glass-card rounded-xl p-5 flex flex-col justify-between">
        <div class="flex items-start justify-between">
          <div>
            <span class="text-[11px] font-medium text-zinc-400 uppercase tracking-wider">CPU & Thermal</span>
            <div class="mt-2 flex items-baseline gap-2.5 font-mono tabular-nums">
              <span class="text-2xl font-semibold text-zinc-100">
                {{ latest?.cpu?.total_percent ?? 0 }}<span class="text-sm text-zinc-500 font-normal">%</span>
              </span>
              <span
                v-if="latest?.cpu?.temperature_c"
                class="inline-flex items-center gap-1 text-xs"
                :class="latest.cpu.temperature_c > 80 ? 'text-rose-400' : 'text-amber-400'"
              >
                <Thermometer class="w-3 h-3" />
                {{ latest.cpu.temperature_c }}°C
              </span>
            </div>
          </div>

          <!-- Ultra-thin SVG Circular Progress Ring -->
          <div class="relative w-10 h-10 flex items-center justify-center shrink-0">
            <svg class="w-10 h-10 -rotate-90" viewBox="0 0 40 40">
              <circle
                cx="20"
                cy="20"
                r="16"
                fill="none"
                stroke="rgba(255,255,255,0.06)"
                stroke-width="2.2"
              />
              <circle
                cx="20"
                cy="20"
                r="16"
                fill="none"
                stroke="#22d3ee"
                stroke-width="2.2"
                stroke-linecap="round"
                :stroke-dasharray="RING_CIRCUMFERENCE"
                :stroke-dashoffset="ringDashOffset(latest?.cpu?.total_percent)"
                class="transition-all duration-300"
              />
            </svg>
            <Cpu class="w-3.5 h-3.5 text-cyan-400 absolute" />
          </div>
        </div>

        <!-- 12 Cores Horizontal Micro-Meters with Hover Tooltips -->
        <div class="mt-5">
          <div class="flex items-center justify-between text-[11px] font-mono text-zinc-500 mb-1.5">
            <span>{{ latest?.cpu?.core_count || 12 }} Cores</span>
            <span v-if="latest?.cpu?.freq_mhz">{{ latest.cpu.freq_mhz }} MHz</span>
          </div>
          <div class="h-7 flex items-end gap-1 pt-1 px-1.5 pb-1 rounded-lg bg-zinc-950/80 border border-white/[0.04]">
            <div
              v-for="(pct, idx) in latest?.cpu?.per_core_percent || []"
              :key="idx"
              class="flex-1 h-full flex items-end bg-white/[0.03] rounded-xs overflow-hidden group/core relative"
              :title="`Core ${idx}: ${Math.round(pct)}%`"
            >
              <div
                class="w-full rounded-xs transition-all duration-300"
                :class="pct > 85 ? 'bg-rose-400' : pct > 60 ? 'bg-amber-400' : 'bg-cyan-400'"
                :style="{ height: `${Math.max(10, Math.min(100, pct))}%` }"
              />
            </div>
          </div>
        </div>
      </div>

      <!-- 2. Physical RAM Card -->
      <div class="glass-card rounded-xl p-5 flex flex-col justify-between">
        <div class="flex items-start justify-between">
          <div>
            <span class="text-[11px] font-medium text-zinc-400 uppercase tracking-wider">Physical RAM</span>
            <div class="mt-2 flex items-baseline gap-2 font-mono tabular-nums">
              <span class="text-2xl font-semibold text-zinc-100">
                {{ formatBytes(latest?.memory?.used_bytes) }}
              </span>
              <span class="text-xs text-zinc-500">
                / {{ formatBytes(latest?.memory?.total_bytes) }}
              </span>
            </div>
          </div>

          <!-- Ultra-thin SVG Circular Progress Ring -->
          <div class="relative w-10 h-10 flex items-center justify-center shrink-0">
            <svg class="w-10 h-10 -rotate-90" viewBox="0 0 40 40">
              <circle
                cx="20"
                cy="20"
                r="16"
                fill="none"
                stroke="rgba(255,255,255,0.06)"
                stroke-width="2.2"
              />
              <circle
                cx="20"
                cy="20"
                r="16"
                fill="none"
                stroke="#34d399"
                stroke-width="2.2"
                stroke-linecap="round"
                :stroke-dasharray="RING_CIRCUMFERENCE"
                :stroke-dashoffset="ringDashOffset(latest?.memory?.percent)"
                class="transition-all duration-300"
              />
            </svg>
            <span class="text-[10px] font-mono text-emerald-400 absolute">
              {{ Math.round(latest?.memory?.percent ?? 0) }}%
            </span>
          </div>
        </div>

        <div class="mt-5 space-y-2.5">
          <!-- Ultra-thin linear progress bar -->
          <div class="h-1 w-full bg-zinc-900 rounded-full overflow-hidden">
            <div
              class="h-full bg-emerald-400 transition-all duration-300"
              :style="{ width: `${latest?.memory?.percent || 0}%` }"
            />
          </div>

          <div class="flex items-center justify-between text-[11px] font-mono tabular-nums text-zinc-400">
            <span>Avail <strong class="text-emerald-400 font-medium">{{ formatBytes(latest?.memory?.available_bytes) }}</strong></span>
            <span>Cache <strong class="text-zinc-200 font-medium">{{ formatBytes(latest?.memory?.cached_bytes) }}</strong></span>
            <span>Slab <strong class="text-zinc-200 font-medium">{{ formatBytes(latest?.memory?.slab_bytes) }}</strong></span>
          </div>
        </div>
      </div>

      <!-- 3. Swap & ZRAM Card -->
      <div class="glass-card rounded-xl p-5 flex flex-col justify-between">
        <div class="flex items-start justify-between">
          <div>
            <span class="text-[11px] font-medium text-zinc-400 uppercase tracking-wider">Swap & ZRAM</span>
            <div class="mt-2 flex items-baseline gap-2 font-mono tabular-nums">
              <span class="text-2xl font-semibold text-zinc-100">
                {{ formatBytes(latest?.swap?.used_bytes) }}
              </span>
              <span class="text-xs text-zinc-500">
                / {{ formatBytes(latest?.swap?.total_bytes) }}
              </span>
            </div>
          </div>

          <!-- Ultra-thin SVG Circular Progress Ring -->
          <div class="relative w-10 h-10 flex items-center justify-center shrink-0">
            <svg class="w-10 h-10 -rotate-90" viewBox="0 0 40 40">
              <circle
                cx="20"
                cy="20"
                r="16"
                fill="none"
                stroke="rgba(255,255,255,0.06)"
                stroke-width="2.2"
              />
              <circle
                cx="20"
                cy="20"
                r="16"
                fill="none"
                stroke="#fbbf24"
                stroke-width="2.2"
                stroke-linecap="round"
                :stroke-dasharray="RING_CIRCUMFERENCE"
                :stroke-dashoffset="ringDashOffset(latest?.swap?.percent)"
                class="transition-all duration-300"
              />
            </svg>
            <Zap class="w-3.5 h-3.5 text-amber-400 absolute" />
          </div>
        </div>

        <div class="mt-5 space-y-2.5">
          <div class="h-1 w-full bg-zinc-900 rounded-full overflow-hidden">
            <div
              class="h-full bg-amber-400 transition-all duration-300"
              :style="{ width: `${latest?.swap?.percent || 0}%` }"
            />
          </div>

          <div class="flex items-center justify-between text-[11px] font-mono">
            <div class="flex items-center gap-1.5">
              <span
                class="w-1.5 h-1.5 rounded-full"
                :class="latest?.swap?.zram?.enabled ? 'bg-emerald-400' : 'bg-zinc-600'"
              />
              <span class="text-zinc-400">
                ZRAM:
                <strong class="text-zinc-200 font-medium">
                  {{ latest?.swap?.zram?.enabled ? 'Active' : 'Not configured' }}
                </strong>
              </span>
            </div>

            <span
              v-if="latest?.swap?.zram?.enabled && latest?.swap?.zram?.devices?.length"
              class="text-cyan-400"
            >
              {{ latest.swap.zram.devices[0].compression_ratio }}x ratio
            </span>

            <button
              v-else
              @click="handleEnableZram"
              :disabled="busyAction === 'enable-zram'"
              class="px-2 py-0.5 rounded bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-300 border border-emerald-500/30 text-[10px] font-sans font-medium transition-colors cursor-pointer disabled:opacity-50"
              title="Configure ZRAM compressed swap via pkexec"
            >
              {{ busyAction === 'enable-zram' ? 'Enabling...' : 'Enable ZRAM' }}
            </button>
          </div>
        </div>
      </div>

      <!-- 4. I/O & Power Card (Single-line minimalist metric rows with tabular numbers) -->
      <div class="glass-card rounded-xl p-5 flex flex-col justify-between">
        <div class="flex items-center justify-between">
          <span class="text-[11px] font-medium text-zinc-400 uppercase tracking-wider">I/O & Power</span>
          <Activity class="w-4 h-4 text-emerald-400" />
        </div>

        <div class="mt-3 space-y-2.5 text-xs">
          <!-- Network Row -->
          <div class="flex items-center justify-between gap-2 whitespace-nowrap">
            <span class="inline-flex items-center gap-1.5 text-zinc-400">
              <Wifi class="w-3.5 h-3.5 text-cyan-400 shrink-0" />
              <span>Net</span>
            </span>
            <span class="font-mono tabular-nums text-zinc-200">
              <span class="text-emerald-400">↓</span> {{ formatRate(latest?.network?.download_bytes_per_sec) }}
              <span class="text-zinc-600 mx-1">/</span>
              <span class="text-cyan-400">↑</span> {{ formatRate(latest?.network?.upload_bytes_per_sec) }}
            </span>
          </div>

          <!-- Disk I/O Row -->
          <div class="flex items-center justify-between gap-2 whitespace-nowrap">
            <span class="inline-flex items-center gap-1.5 text-zinc-400">
              <HardDrive class="w-3.5 h-3.5 text-emerald-400 shrink-0" />
              <span>Disk</span>
            </span>
            <span class="font-mono tabular-nums text-zinc-200">
              <span class="text-emerald-400">↓</span> {{ formatRate(latest?.disk_io?.read_bytes_per_sec) }}
              <span class="text-zinc-600 mx-1">/</span>
              <span class="text-amber-400">↑</span> {{ formatRate(latest?.disk_io?.write_bytes_per_sec) }}
            </span>
          </div>

          <!-- Power Row -->
          <div class="flex items-center justify-between gap-2 whitespace-nowrap">
            <span class="inline-flex items-center gap-1.5 text-zinc-400">
              <BatteryCharging class="w-3.5 h-3.5 text-amber-400 shrink-0" />
              <span>Power</span>
            </span>
            <span class="font-mono tabular-nums text-zinc-200">
              <template v-if="latest?.battery?.present">
                {{ latest.battery.percent }}%
                <span v-if="latest.battery.wattage" class="text-amber-400">· {{ latest.battery.wattage }}W</span>
              </template>
              <template v-else>
                AC · {{ formatUptime(latest?.uptime_seconds) }}
              </template>
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- Real-Time ECharts Telemetry Area Chart (No verbose subtitle noise) -->
    <div class="glass-panel rounded-xl p-5">
      <div class="flex items-center justify-between mb-2">
        <h3 class="text-xs font-semibold uppercase tracking-wider text-zinc-400">Live Telemetry</h3>
        <div class="text-xs font-mono tabular-nums text-zinc-400">
          Load {{ (latest?.cpu?.load_avg || [0, 0, 0]).join(' · ') }}
        </div>
      </div>
      <div ref="chartEl" class="w-full h-52" />
    </div>

    <!-- Minimalist Guard Policies & Tray Notification Engine Panel -->
    <div class="glass-panel rounded-xl p-5 space-y-4">
      <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-white/[0.05] pb-3.5">
        <div class="flex items-center gap-2.5">
          <ShieldAlert class="w-4 h-4 text-emerald-400 shrink-0" />
          <h3 class="text-xs font-semibold uppercase tracking-wider text-zinc-200">
            Guard Policies &amp; Tray
          </h3>
          <span
            class="px-2 py-0.5 text-[10px] font-mono rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
            title="Checks vitals every 5s with 10s hysteresis and 5m anti-spam cooldown"
          >
            {{ guardActive ? 'Ubuntu Tray & Guard Active' : 'Standby' }}
          </span>
        </div>

        <div class="flex items-center gap-2">
          <button
            @click="handleTestNotification"
            :disabled="testingNotification"
            class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-white/[0.03] hover:bg-cyan-500/15 text-zinc-200 hover:text-cyan-300 border border-white/[0.07] hover:border-cyan-500/30 transition-all cursor-pointer disabled:opacity-50"
            title="Send a sample native Ubuntu desktop notification via notify-send"
          >
            <Bell class="w-3.5 h-3.5 text-cyan-400" />
            <span>{{ testingNotification ? 'Sending...' : 'Test Desktop Notification' }}</span>
          </button>
        </div>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-12 gap-5">
        <!-- Left 7 Cols: Configurable Guard Policy Sliders & Toggles -->
        <div class="lg:col-span-7 space-y-2.5">
          <div
            v-for="rule in guardRules"
            :key="rule.id"
            class="p-3.5 rounded-lg bg-[#09090B]/90 border border-white/[0.06] flex flex-col gap-2.5 transition-opacity"
            :class="rule.enabled ? 'opacity-100' : 'opacity-55'"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <div class="flex items-center gap-2">
                  <span class="text-xs font-medium text-zinc-100 truncate">{{ rule.name }}</span>
                  <span
                    v-if="rule.id === 'auto_rescue_ram'"
                    class="px-1.5 py-0.5 text-[10px] font-mono rounded bg-amber-500/10 text-amber-300 border border-amber-500/20"
                  >
                    Auto-Remediation
                  </span>
                </div>
                <p class="text-[11px] text-zinc-500 mt-0.5 leading-relaxed">
                  {{ rule.description }}
                </p>
              </div>

              <div class="flex items-center gap-3 shrink-0">
                <span
                  class="px-2 py-0.5 rounded bg-[#121215] border border-white/[0.07] font-mono text-xs tabular-nums"
                  :class="
                    rule.unit === '°C'
                      ? 'text-amber-400'
                      : rule.id === 'auto_rescue_ram'
                      ? 'text-rose-400'
                      : 'text-emerald-400'
                  "
                >
                  {{ rule.threshold }}{{ rule.unit }}
                </span>

                <!-- Minimalist Toggle Switch -->
                <button
                  type="button"
                  @click="updatePolicyRule(rule.id, { enabled: !rule.enabled })"
                  class="w-9 h-5 rounded-full transition-colors p-0.5 cursor-pointer border border-white/[0.08] flex items-center"
                  :class="rule.enabled ? 'bg-emerald-500/30 justify-end' : 'bg-zinc-900 justify-start'"
                  :title="rule.enabled ? 'Disable policy rule' : 'Enable policy rule'"
                >
                  <span
                    class="w-3.5 h-3.5 rounded-full transition-colors"
                    :class="rule.enabled ? 'bg-emerald-400' : 'bg-zinc-500'"
                  />
                </button>
              </div>
            </div>

            <!-- Sleek Threshold Slider -->
            <div class="flex items-center gap-3">
              <span class="text-[10px] font-mono text-zinc-500 w-9">{{ rule.min }}{{ rule.unit }}</span>
              <input
                type="range"
                :min="rule.min"
                :max="rule.max"
                :value="rule.threshold"
                :disabled="!rule.enabled"
                @input="(e) => (rule.threshold = Number(e.target.value))"
                @change="(e) => updatePolicyRule(rule.id, { threshold: Number(e.target.value) })"
                class="w-full h-1 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-emerald-400 disabled:cursor-not-allowed"
              />
              <span class="text-[10px] font-mono text-zinc-500 w-10 text-right">
                {{ rule.max }}{{ rule.unit }}
              </span>
            </div>
          </div>
        </div>

        <!-- Right 5 Cols: Clean Log of Recent Triggered Alerts -->
        <div class="lg:col-span-5 flex flex-col rounded-lg bg-[#09090B]/90 border border-white/[0.06] p-3.5">
          <div class="flex items-center justify-between pb-2.5 mb-2.5 border-b border-white/[0.05]">
            <div class="flex items-center gap-2">
              <span class="text-[11px] font-medium uppercase tracking-wider text-zinc-400">
                Recent Triggered Alerts
              </span>
              <span class="px-1.5 py-0.5 text-[10px] font-mono rounded bg-white/[0.04] text-zinc-400">
                {{ alertsLog.length }}
              </span>
            </div>
            <button
              v-if="alertsLog.length > 0"
              @click="handleClearAlerts"
              class="inline-flex items-center gap-1 text-[11px] text-zinc-500 hover:text-zinc-300 transition-colors cursor-pointer"
              title="Clear alert history"
            >
              <Trash2 class="w-3 h-3" />
              <span>Clear</span>
            </button>
          </div>

          <div
            v-if="alertsLog.length === 0"
            class="flex-1 flex flex-col items-center justify-center py-10 text-center text-zinc-500"
          >
            <Bell class="w-5 h-5 text-zinc-600 mb-2" />
            <p class="text-xs text-zinc-400">No threshold breaches recorded</p>
            <p class="text-[11px] text-zinc-600 mt-0.5">
              Click "Test Desktop Notification" to verify native Ubuntu alerts.
            </p>
          </div>

          <div v-else class="space-y-2 max-h-80 overflow-y-auto pr-1">
            <div
              v-for="alert in alertsLog"
              :key="alert.id"
              class="p-2.5 rounded-lg bg-[#121215] border border-white/[0.05] space-y-1"
            >
              <div class="flex items-center justify-between gap-2">
                <div class="flex items-center gap-1.5 min-w-0">
                  <span
                    class="w-1.5 h-1.5 rounded-full shrink-0"
                    :class="
                      alert.severity === 'critical'
                        ? 'bg-rose-400'
                        : alert.severity === 'warning'
                        ? 'bg-amber-400'
                        : 'bg-cyan-400'
                    "
                  />
                  <span class="text-xs font-medium text-zinc-200 truncate">
                    {{ alert.title }}
                  </span>
                </div>
                <span class="text-[10px] font-mono text-zinc-500 shrink-0">
                  {{ alert.timestamp }}
                </span>
              </div>
              <p class="text-[11px] text-zinc-400 font-mono leading-relaxed break-words">
                {{ alert.message }}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Clean Borderless Process Table with Inline Memory Usage Bar -->
    <div class="glass-panel rounded-xl p-5">
      <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
        <div class="flex items-center gap-2.5">
          <h3 class="text-xs font-semibold uppercase tracking-wider text-zinc-400">Process Groups</h3>
          <span class="px-2 py-0.5 text-[11px] font-mono tabular-nums rounded bg-white/[0.04] text-zinc-300 border border-white/[0.06]">
            {{ totalProcesses }} PIDs
          </span>
        </div>

        <div class="flex items-center gap-2">
          <div class="relative">
            <Search class="w-3.5 h-3.5 text-zinc-500 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              v-model="procSearch"
              type="text"
              placeholder="Filter process or PID..."
              class="pl-8 pr-3 py-1.5 text-xs rounded-lg bg-[#09090B] border border-white/[0.07] text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-white/20 w-52"
            />
          </div>
          <button
            @click="fetchGroupedProcesses"
            :disabled="loadingProcs"
            class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-white/[0.03] hover:bg-white/[0.07] text-zinc-300 border border-white/[0.06] transition-colors cursor-pointer"
          >
            <RefreshCw class="w-3.5 h-3.5" :class="{ 'animate-spin': loadingProcs }" />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      <!-- Borderless Minimal Table -->
      <div class="overflow-x-auto">
        <table class="w-full text-left border-collapse">
          <thead>
            <tr class="text-[11px] font-medium uppercase tracking-wider text-zinc-500 border-b border-white/[0.05]">
              <th class="py-2.5 px-3 font-medium">Application</th>
              <th class="py-2.5 px-3 font-medium">Tasks</th>
              <th class="py-2.5 px-3 font-medium">User</th>
              <th class="py-2.5 px-3 font-medium text-right">CPU</th>
              <th class="py-2.5 px-3 font-medium">Memory (RSS)</th>
              <th class="py-2.5 px-3 font-medium text-right">Action</th>
            </tr>
          </thead>
          <tbody class="text-xs">
            <template v-for="group in filteredGroups" :key="group.group_name">
              <tr
                class="group hover:bg-white/[0.03] transition-colors cursor-pointer"
                @click="toggleGroupExpand(group.group_name)"
              >
                <td class="py-2.5 px-3 font-medium text-zinc-100 rounded-l-lg">
                  <div class="flex items-center gap-2">
                    <component
                      :is="expandedGroups.has(group.group_name) ? ChevronDown : ChevronRight"
                      class="w-3.5 h-3.5 text-zinc-500 shrink-0"
                    />
                    <span class="truncate">{{ group.group_name }}</span>
                  </div>
                </td>
                <td class="py-2.5 px-3 font-mono tabular-nums text-zinc-400">
                  {{ group.process_count }}
                </td>
                <td class="py-2.5 px-3 font-mono text-zinc-500">{{ group.user }}</td>
                <td class="py-2.5 px-3 font-mono tabular-nums text-right text-cyan-400">
                  {{ group.total_cpu_percent }}%
                </td>
                <td class="py-2.5 px-3 w-52">
                  <!-- Inline thin memory usage bar behind row's RAM value -->
                  <div class="relative h-6 rounded-md bg-white/[0.02] overflow-hidden flex items-center justify-between px-2.5 font-mono tabular-nums">
                    <div
                      class="absolute inset-y-0 left-0 transition-all duration-300 pointer-events-none"
                      :class="
                        group.memory_percent > 15
                          ? 'bg-rose-500/20'
                          : group.memory_percent > 7
                          ? 'bg-amber-400/20'
                          : 'bg-emerald-400/15'
                      "
                      :style="{ width: `${Math.min(100, group.memory_percent * 2.2)}%` }"
                    />
                    <span class="relative z-10 font-medium text-emerald-300">
                      {{ formatBytes(group.total_rss_bytes) }}
                    </span>
                    <span class="relative z-10 text-[10px] text-zinc-500">
                      {{ group.memory_percent }}%
                    </span>
                  </div>
                </td>
                <td class="py-2.5 px-3 text-right rounded-r-lg" @click.stop>
                  <div class="inline-flex items-center gap-1.5 opacity-80 group-hover:opacity-100 transition-opacity">
                    <button
                      @click="killProcessGroup(group.pids, group.group_name, false)"
                      class="px-2 py-1 rounded-md bg-white/[0.03] hover:bg-amber-500/15 text-zinc-400 hover:text-amber-300 border border-white/[0.06] hover:border-amber-500/30 transition-colors cursor-pointer text-[11px]"
                      title="Graceful SIGTERM"
                    >
                      End
                    </button>
                    <button
                      @click="killProcessGroup(group.pids, group.group_name, true)"
                      class="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-rose-500/10 hover:bg-rose-500/25 text-rose-300 border border-rose-500/20 transition-colors cursor-pointer text-[11px]"
                      title="Force SIGKILL (-9)"
                    >
                      <Skull class="w-3 h-3" />
                      <span>Kill</span>
                    </button>
                  </div>
                </td>
              </tr>

              <!-- Expanded Subprocess PIDs -->
              <tr v-if="expandedGroups.has(group.group_name)">
                <td colspan="6" class="px-4 py-2">
                  <div class="rounded-lg bg-[#09090B] border border-white/[0.06] overflow-hidden">
                    <table class="w-full text-[11px] font-mono tabular-nums">
                      <thead class="text-zinc-500 border-b border-white/[0.05]">
                        <tr>
                          <th class="py-1.5 px-3 font-normal">PID</th>
                          <th class="py-1.5 px-3 font-normal">Binary</th>
                          <th class="py-1.5 px-3 font-normal">Command</th>
                          <th class="py-1.5 px-3 font-normal text-right">CPU</th>
                          <th class="py-1.5 px-3 font-normal text-right">RSS</th>
                          <th class="py-1.5 px-3 font-normal text-right"></th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr
                          v-for="proc in group.processes"
                          :key="proc.pid"
                          class="hover:bg-white/[0.02]"
                        >
                          <td class="py-1.5 px-3 text-cyan-400">{{ proc.pid }}</td>
                          <td class="py-1.5 px-3 text-zinc-300">{{ proc.name }}</td>
                          <td class="py-1.5 px-3 text-zinc-500 max-w-md truncate" :title="proc.cmdline">
                            {{ proc.cmdline }}
                          </td>
                          <td class="py-1.5 px-3 text-right text-zinc-400">{{ proc.cpu_percent }}%</td>
                          <td class="py-1.5 px-3 text-right text-emerald-400">{{ formatBytes(proc.rss_bytes) }}</td>
                          <td class="py-1.5 px-3 text-right">
                            <button
                              @click="killProcessGroup([proc.pid], `PID ${proc.pid}`, true)"
                              class="px-2 py-0.5 rounded bg-rose-500/10 hover:bg-rose-500/25 text-rose-300 text-[10px] cursor-pointer"
                            >
                              Kill
                            </button>
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
