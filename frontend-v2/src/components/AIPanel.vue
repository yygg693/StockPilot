<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from "vue"
import { streamAI } from "@/api"

const props = withDefaults(defineProps<{
  context: string
  assetCode?: string
  assetName?: string
  defaultQuestion?: string
  orbSize?: number
}>(), {
  defaultQuestion: "\u5206\u6790\u4e00\u4e0b\u8fd9\u4e2a\u6807\u7684",
  orbSize: 200,
})

interface ChatMsg { role: "user" | "ai"; text: string }
const messages = ref<ChatMsg[]>([])
const thinking = ref(false)
const input = ref("")
const chatEndRef = ref<HTMLDivElement>()
const orbCanvas = ref<HTMLCanvasElement>()

let orbAnim = 0
let particles: any[] = []
let mouseX = 0, mouseY = 0, mouseIn = false

function scrollChat() {
  nextTick(() => { chatEndRef.value?.scrollIntoView({ behavior: "smooth" }) })
}

async function send() {
  const text = input.value.trim()
  if (!text || thinking.value) return
  input.value = ""
  messages.value.push({ role: "user", text })
  thinking.value = true
  scrollChat()

  const aiIdx = messages.value.length
  messages.value.push({ role: "ai", text: "" })

  const history = messages.value.slice(0, -1).map(m => ({
    role: m.role === "ai" ? "assistant" : "user",
    content: m.text,
  }))

  streamAI(
    history,
    props.context,
    (chunk: string) => { messages.value[aiIdx].text += chunk },
    () => { thinking.value = false; scrollChat() },
    (err: string) => {
      messages.value[aiIdx].text = "\u8bf7\u6c42\u5931\u8d25: " + err
      thinking.value = false
      scrollChat()
    }
  )
}

function askDefault() {
  if (thinking.value) return
  input.value = props.defaultQuestion
  send()
}

// --- Particle Orb ---
function initOrb() {
  const canvas = orbCanvas.value
  if (!canvas) return
  const ctx = canvas.getContext("2d")!
  const S = props.orbSize
  const W = canvas.width = S
  const H = canvas.height = S
  const cx = W / 2, cy = H / 2
  const R = S * 0.275

  particles = Array.from({ length: 220 }, () => {
    const theta = Math.random() * Math.PI * 2
    const phi = Math.acos(2 * Math.random() - 1)
    return { theta, phi, r: R + (Math.random() - 0.5) * (R * 0.18), speed: 0.002 + Math.random() * 0.004, size: 1 + Math.random() * 1.8, ox: 0, oy: 0 }
  })

  function draw() {
    ctx.clearRect(0, 0, W, H)
    const t = Date.now() * 0.001
    const active = thinking.value
    const rotSpeed = active ? 0.02 : 0.005

    // Glow
    const glowR = active ? R * 1.27 : R * 0.9
    const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, glowR)
    const alpha = active ? 0.25 : 0.12
    grad.addColorStop(0, `rgba(201,169,98,${alpha})`)
    grad.addColorStop(1, "rgba(201,169,98,0)")
    ctx.fillStyle = grad
    ctx.beginPath()
    ctx.arc(cx, cy, glowR, 0, Math.PI * 2)
    ctx.fill()

    for (const p of particles) {
      p.theta += p.speed * (active ? 3 : 1)
      const x3d = p.r * Math.sin(p.phi) * Math.cos(p.theta + t * rotSpeed * 60)
      const y3d = p.r * Math.cos(p.phi)
      const z3d = p.r * Math.sin(p.phi) * Math.sin(p.theta + t * rotSpeed * 60)
      const scale = 1 / (1 + z3d * 0.003)
      let sx = cx + x3d * scale
      let sy = cy + y3d * scale

      if (mouseIn) {
        const dx = sx - mouseX, dy = sy - mouseY
        const dist = Math.sqrt(dx * dx + dy * dy)
        const repelR = S * 0.3
        if (dist < repelR) {
          const force = (repelR - dist) / repelR * 12
          p.ox += (dx / dist) * force * 0.3
          p.oy += (dy / dist) * force * 0.3
        }
      }
      p.ox *= 0.9
      p.oy *= 0.9
      sx += p.ox
      sy += p.oy

      const depth = (z3d + p.r) / (2 * p.r)
      const a = 0.3 + depth * 0.7
      ctx.beginPath()
      ctx.arc(sx, sy, p.size * scale, 0, Math.PI * 2)
      ctx.fillStyle = active ? `rgba(245,200,66,${a})` : `rgba(201,169,98,${a})`
      ctx.fill()
    }
    orbAnim = requestAnimationFrame(draw)
  }
  draw()
}

function onOrbMouseMove(e: MouseEvent) {
  const rect = orbCanvas.value?.getBoundingClientRect()
  if (!rect) return
  mouseX = e.clientX - rect.left
  mouseY = e.clientY - rect.top
  mouseIn = true
}
function onOrbMouseLeave() { mouseIn = false }
function onOrbClick() {
  for (const p of particles) {
    p.ox += (Math.random() - 0.5) * 20
    p.oy += (Math.random() - 0.5) * 20
  }
  askDefault()
}

onMounted(() => { initOrb() })
onUnmounted(() => { cancelAnimationFrame(orbAnim) })
</script>

<template>
  <div class="ai-panel">
    <div class="ai-panel-head">
      <span class="ai-panel-title">AI &#25237;&#39038;</span>
      <span class="ai-panel-sub" v-if="thinking">&#24605;&#32771;&#20013;...</span>
    </div>

    <div class="orb-wrap" @mousemove="onOrbMouseMove" @mouseleave="onOrbMouseLeave" @click="onOrbClick">
      <canvas ref="orbCanvas" class="orb-canvas"></canvas>
      <span class="orb-hint" v-if="!messages.length && !thinking">&#28857;&#20987;&#25110;&#36755;&#20837;&#38382;&#39064;</span>
    </div>

    <div class="chat-area">
      <div v-if="!messages.length && !thinking" class="chat-empty">
        &#28857;&#20987;&#31890;&#23376;&#25110;&#22312;&#19979;&#26041;&#36755;&#20837;&#38382;&#39064;&#65292;AI&#20026;&#20320;&#35299;&#31572;
      </div>
      <div v-for="(msg, i) in messages" :key="i" class="chat-msg" :class="msg.role">
        <div class="chat-bubble">{{ msg.text }}</div>
      </div>
      <div v-if="thinking" class="chat-msg ai">
        <div class="chat-bubble thinking">
          <span class="dot"></span><span class="dot"></span><span class="dot"></span>
        </div>
      </div>
      <div ref="chatEndRef"></div>
    </div>

    <div class="chat-input-wrap">
      <input v-model="input" class="chat-input" placeholder="&#38382;&#28857;&#20160;&#20040;...&#27604;&#22914;&#29616;&#22312;&#33021;&#20080;&#21527;" @keydown.enter="send" :disabled="thinking" />
      <button class="chat-send" :disabled="thinking || !input.trim()" @click="send">&#21457;&#36865;</button>
    </div>
  </div>
</template>

<style scoped>
.ai-panel { display: flex; flex-direction: column; height: 100%; background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); overflow: hidden; }
.ai-panel-head { display: flex; align-items: center; justify-content: space-between; padding: 14px 18px 10px; }
.ai-panel-title { font-size: 13px; font-weight: 700; color: var(--text-primary); }
.ai-panel-sub { font-size: 11px; color: var(--accent); animation: pulse 1.2s infinite; }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }

.orb-wrap { position: relative; display: flex; align-items: center; justify-content: center; height: 160px; cursor: pointer; flex-shrink: 0; }
.orb-canvas { width: 100%; height: 100%; }
.orb-hint { position: absolute; bottom: 8px; font-size: 10px; color: var(--text-tertiary); pointer-events: none; }

.chat-area { flex: 1; overflow-y: auto; padding: 12px 14px; display: flex; flex-direction: column; gap: 10px; min-height: 120px; }
.chat-empty { font-size: 11.5px; color: var(--text-tertiary); text-align: center; padding: 16px 0; }
.chat-msg { max-width: 88%; }
.chat-msg.user { align-self: flex-end; }
.chat-msg.ai { align-self: flex-start; }
.chat-bubble { padding: 9px 13px; border-radius: 12px; font-size: 12.5px; line-height: 1.6; white-space: pre-wrap; word-break: break-word; }
.chat-msg.user .chat-bubble { background: var(--accent-dim); color: var(--accent); border-bottom-right-radius: 4px; }
.chat-msg.ai .chat-bubble { background: var(--bg-overlay); color: var(--text-secondary); border-bottom-left-radius: 4px; }
.chat-bubble.thinking { display: flex; gap: 4px; padding: 12px 16px; }
.dot { width: 5px; height: 5px; border-radius: 50%; background: var(--accent); animation: bounce 1.2s infinite; }
.dot:nth-child(2) { animation-delay: 0.2s; }
.dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes bounce { 0%,60%,100% { transform: translateY(0); } 30% { transform: translateY(-5px); } }

.chat-input-wrap { display: flex; gap: 8px; padding: 12px 14px; border-top: 1px solid var(--border-subtle); }
.chat-input { flex: 1; background: var(--bg-overlay); border: 1px solid var(--border-default); border-radius: var(--radius-sm); padding: 8px 12px; font-size: 12px; color: var(--text-primary); outline: none; transition: border-color 0.15s; }
.chat-input:focus { border-color: var(--accent); }
.chat-input:disabled { opacity: 0.5; }
.chat-send { padding: 8px 14px; border-radius: var(--radius-sm); border: none; background: var(--accent); color: #111; font-size: 12px; font-weight: 600; cursor: pointer; transition: opacity 0.15s; }
.chat-send:disabled { opacity: 0.4; cursor: not-allowed; }
.chat-send:not(:disabled):hover { opacity: 0.85; }
</style>
