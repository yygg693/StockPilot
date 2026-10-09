<script setup lang="ts">
import { ref, onMounted, onUnmounted } from "vue"

const canvas = ref<HTMLCanvasElement>()
let animId = 0

interface P { x: number; y: number; size: number; speedY: number; speedX: number; opacity: number; fadeSpeed: number; phase: number; wobble: number }

onMounted(() => {
  const c = canvas.value
  if (!c) return
  const ctx = c.getContext("2d")
  if (!ctx) return

  let w = 0, h = 0
  let particles: P[] = []
  let particleColor = "201, 169, 98"
  let particleOpacity = 0.35

  function resize() {
    w = c!.width = window.innerWidth
    h = c!.height = window.innerHeight
  }

  function getThemeVars() {
    const cs = getComputedStyle(document.documentElement)
    particleColor = cs.getPropertyValue("--particle-color").trim() || "201, 169, 98"
    particleOpacity = parseFloat(cs.getPropertyValue("--particle-opacity")) || 0.3
  }

  function makeParticle(init: boolean): P {
    return {
      x: Math.random() * w,
      y: init ? Math.random() * h : h + 10,
      size: Math.random() * 1.8 + 0.4,
      speedY: -(Math.random() * 0.25 + 0.08),
      speedX: (Math.random() - 0.5) * 0.15,
      opacity: Math.random() * 0.5 + 0.1,
      fadeSpeed: Math.random() * 0.003 + 0.001,
      phase: Math.random() * Math.PI * 2,
      wobble: Math.random() * 0.3 + 0.1,
    }
  }

  function initParticles() {
    const count = Math.min(Math.floor((w * h) / 18000), 80)
    particles = Array.from({ length: count }, () => makeParticle(true))
  }

  function drawGlow() {
    const cs = getComputedStyle(document.documentElement)
    const g1 = cs.getPropertyValue("--canvas-glow-1").trim()
    const g2 = cs.getPropertyValue("--canvas-glow-2").trim()
    const grad1 = ctx!.createRadialGradient(w * 0.75, h * 0.2, 0, w * 0.75, h * 0.2, w * 0.4)
    grad1.addColorStop(0, g1)
    grad1.addColorStop(1, "transparent")
    ctx!.fillStyle = grad1
    ctx!.fillRect(0, 0, w, h)
    const grad2 = ctx!.createRadialGradient(w * 0.15, h * 0.8, 0, w * 0.15, h * 0.8, w * 0.35)
    grad2.addColorStop(0, g2)
    grad2.addColorStop(1, "transparent")
    ctx!.fillStyle = grad2
    ctx!.fillRect(0, 0, w, h)
  }

  function animate() {
    ctx!.clearRect(0, 0, w, h)
    drawGlow()
    for (const p of particles) {
      p.y += p.speedY
      p.phase += 0.01
      p.x += p.speedX + Math.sin(p.phase) * p.wobble * 0.1
      p.opacity += Math.sin(p.phase * 2) * p.fadeSpeed
      if (p.opacity < 0.02) p.opacity = 0.02
      if (p.opacity > 0.6) p.opacity = 0.6
      if (p.y < -10 || p.x < -10 || p.x > w + 10) Object.assign(p, makeParticle(false))

      const a = p.opacity * particleOpacity
      ctx!.beginPath()
      ctx!.arc(p.x, p.y, p.size, 0, Math.PI * 2)
      ctx!.fillStyle = `rgba(${particleColor}, ${a})`
      ctx!.fill()
      if (p.size > 1.2) {
        ctx!.beginPath()
        ctx!.arc(p.x, p.y, p.size * 2.5, 0, Math.PI * 2)
        ctx!.fillStyle = `rgba(${particleColor}, ${a * 0.15})`
        ctx!.fill()
      }
    }
    // Connection lines
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const dx = particles[i].x - particles[j].x
        const dy = particles[i].y - particles[j].y
        const dist = Math.sqrt(dx * dx + dy * dy)
        if (dist < 100) {
          const a = (1 - dist / 100) * 0.06 * particleOpacity
          ctx!.beginPath()
          ctx!.moveTo(particles[i].x, particles[i].y)
          ctx!.lineTo(particles[j].x, particles[j].y)
          ctx!.strokeStyle = `rgba(${particleColor}, ${a})`
          ctx!.lineWidth = 0.5
          ctx!.stroke()
        }
      }
    }
    animId = requestAnimationFrame(animate)
  }

  resize()
  getThemeVars()
  initParticles()
  animate()
  window.addEventListener("resize", () => { resize(); initParticles() })

  const observer = new MutationObserver(() => getThemeVars())
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] })
})

onUnmounted(() => cancelAnimationFrame(animId))
</script>

<template>
  <canvas ref="canvas" class="particle-bg" />
</template>

<style scoped>
.particle-bg {
  position: fixed; inset: 0; z-index: 0; pointer-events: none;
}
</style>
