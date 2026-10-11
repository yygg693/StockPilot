<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { getParticles, onParticles } from '@/composables/useLiquidGlass'

const canvas = ref<HTMLCanvasElement | null>(null)
let ctx: CanvasRenderingContext2D | null = null
let raf = 0
let running = false

function resize() {
  const c = canvas.value
  if (!c) return
  // Cap DPR at 1.5: this is a full-screen overlay canvas, so a 2x/3x DPR on a
  // 4K display means clearing/drawing millions of pixels every frame. Capping
  // keeps it crisp enough while cutting the per-frame cost dramatically.
  const dpr = Math.min(window.devicePixelRatio || 1, 1.5)
  c.width = window.innerWidth * dpr
  c.height = window.innerHeight * dpr
  c.style.width = window.innerWidth + 'px'
  c.style.height = window.innerHeight + 'px'
  ctx = c.getContext('2d')
  if (ctx) ctx.scale(dpr, dpr)
}

function draw() {
  if (!ctx || !canvas.value) return
  const w = window.innerWidth
  const h = window.innerHeight
  ctx.clearRect(0, 0, w, h)

  const particles = getParticles()
  for (let i = particles.length - 1; i >= 0; i--) {
    const p = particles[i]
    p.x += p.vx
    p.y += p.vy
    p.vy += 0.04  // gravity
    p.vx *= 0.98  // friction
    p.life -= 1 / p.maxLife

    if (p.life <= 0) {
      particles.splice(i, 1)
      continue
    }

    const alpha = p.life * 0.8
    const size = p.size * p.life

    // Glow
    ctx.beginPath()
    ctx.arc(p.x, p.y, size * 2.5, 0, Math.PI * 2)
    ctx.fillStyle = `hsla(${p.hue}, 80%, 65%, ${alpha * 0.15})`
    ctx.fill()

    // Core
    ctx.beginPath()
    ctx.arc(p.x, p.y, size, 0, Math.PI * 2)
    ctx.fillStyle = `hsla(${p.hue}, 85%, 70%, ${alpha})`
    ctx.fill()
  }

  if (particles.length > 0 || running) {
    raf = requestAnimationFrame(draw)
  } else {
    raf = 0
    // Fully hide the canvas when idle so the browser stops compositing this
    // full-screen overlay layer entirely (zero cost at rest).
    if (canvas.value) canvas.value.style.display = 'none'
  }
}

function kick() {
  // Show the overlay only while particles are actually animating.
  if (canvas.value) canvas.value.style.display = 'block'
  if (!raf) {
    running = true
    raf = requestAnimationFrame(draw)
    // Stop after idle
    setTimeout(() => { running = false }, 200)
  }
}

let unsub: (() => void) | null = null

onMounted(() => {
  resize()
  // Start hidden — only shown when a particle burst is triggered.
  if (canvas.value) canvas.value.style.display = 'none'
  window.addEventListener('resize', resize)
  unsub = onParticles(() => kick())
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  if (raf) cancelAnimationFrame(raf)
  unsub?.()
})
</script>

<template>
  <canvas ref="canvas" class="liquid-particle-canvas" />
</template>

<style scoped>
.liquid-particle-canvas {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  pointer-events: none;
  z-index: 9999;
}
</style>
