/**
 * useLiquidGlass - JELLY physics interaction
 * Squash-and-stretch wobble + cursor-following tilt + subtle particles
 * Inspired by Apple Liquid Glass / Huawei particle effects
 */
import { onMounted, onBeforeUnmount, type Ref } from 'vue'

// ---- Global particle bus (subtle, secondary to jelly) ----
export interface Particle {
  x: number; y: number
  vx: number; vy: number
  life: number; maxLife: number
  size: number
  hue: number
}

const particles: Particle[] = []
let listeners: ((p: Particle[]) => void)[] = []

export function onParticles(fn: (p: Particle[]) => void) {
  listeners.push(fn)
  return () => { listeners = listeners.filter(l => l !== fn) }
}

export function emitParticles(x: number, y: number, count: number, spread = 1.5) {
  for (let i = 0; i < count; i++) {
    const angle = Math.random() * Math.PI * 2
    const speed = Math.random() * spread + 0.3
    particles.push({
      x, y,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed - 0.8,
      life: 1,
      maxLife: 30 + Math.random() * 25,
      size: 1 + Math.random() * 2,
      hue: Math.random() > 0.4 ? 42 : 200,
    })
  }
  if (particles.length > 80) particles.splice(0, particles.length - 80)
  listeners.forEach(fn => fn(particles))
}

export function getParticles() { return particles }

// ---- Bouncy Spring (low damping = more wobble) ----
class JellySpring {
  value = 0
  velocity = 0
  target = 0
  stiffness: number
  damping: number

  constructor(stiffness = 120, damping = 8) {
    this.stiffness = stiffness
    this.damping = damping
  }

  update(dt: number) {
    const force = -this.stiffness * (this.value - this.target)
    const dampForce = -this.damping * this.velocity
    this.velocity += (force + dampForce) * dt
    this.value += this.velocity * dt
    return this.value
  }

  get settled() {
    return Math.abs(this.value - this.target) < 0.0005 && Math.abs(this.velocity) < 0.0005
  }

  // Give it a kick for wobble
  kick(amount: number) {
    this.velocity += amount
  }
}

// ---- Core jelly logic (shared between directive and composable) ----
function attachJelly(el: HTMLElement, cfg: {
  maxTilt: number
  squash: number      // how much squash-stretch on press (0.06 = 6%)
  wobbleKick: number  // initial wobble velocity on release
  glowSize: number
  particleRate: number
  hoverScale: number
}) {
  // Springs — only scale/glow are animated now. We deliberately dropped the
  // rotateX/rotateY + perspective (3D) transform: each liquid element was being
  // promoted to its own compositing layer, which caused app-wide jank on every
  // hover/move. A 2D scale wobble is visually close and vastly cheaper.
  const scaleX = new JellySpring(120, 9)
  const scaleY = new JellySpring(120, 9)
  const glow = new JellySpring(220, 22)

  let raf = 0
  let hovering = false
  let pressing = false
  let mouseX = 0.5
  let mouseY = 0.5
  let lastTime = 0

  scaleX.value = 1; scaleX.target = 1
  scaleY.value = 1; scaleY.target = 1

  function onEnter() {
    hovering = true
    scaleX.target = cfg.hoverScale
    scaleY.target = cfg.hoverScale
    glow.target = 1
    startLoop()
  }

  function onLeave() {
    hovering = false
    pressing = false
    scaleX.target = 1
    scaleY.target = 1
    glow.target = 0
  }

  function onMove(e: MouseEvent) {
    // Event-relative offset + cached clientWidth/Height avoids getBoundingClientRect
    // on every mousemove — that call forces a synchronous layout (a classic jank
    // source when there are dozens of liquid elements on screen).
    const w = el.clientWidth || 1
    const h = el.clientHeight || 1
    mouseX = e.offsetX / w
    mouseY = e.offsetY / h
    el.style.setProperty('--glow-x', (mouseX * 100) + '%')
    el.style.setProperty('--glow-y', (mouseY * 100) + '%')
    el.style.setProperty('--glow-size', cfg.glowSize + 'px')
  }

  function onDown(e: MouseEvent) {
    pressing = true
    scaleX.target = cfg.hoverScale * (1 + cfg.squash)
    scaleY.target = cfg.hoverScale * (1 - cfg.squash * 1.4)
    scaleX.kick(3)
    scaleY.kick(-4)
    glow.target = 1
    // Brief particle burst on press only (no hover emission) so the full-screen
    // particle canvas stays idle during normal navigation.
    emitParticles(e.clientX, e.clientY, 5, 2.2)
  }

  function onUp() {
    if (!pressing) return
    pressing = false
    // RELEASE: spring back with overshoot wobble
    scaleX.target = hovering ? cfg.hoverScale : 1
    scaleY.target = hovering ? cfg.hoverScale : 1
    // Big kick = visible jelly wobble oscillation
    scaleX.kick(-cfg.wobbleKick)
    scaleY.kick(cfg.wobbleKick * 1.3)
  }

  function loop(time: number) {
    const dt = Math.min((time - lastTime) / 1000, 0.032)
    lastTime = time

    const sx = scaleX.update(dt)
    const sy = scaleY.update(dt)
    const g = glow.update(dt)

    // 2D-only transform — no perspective/rotate, so no forced 3D layer.
    el.style.transform = 'scaleX(' + sx.toFixed(4) + ') scaleY(' + sy.toFixed(4) + ')'
    el.style.setProperty('--press', g.toFixed(3))

    const allSettled = scaleX.settled && scaleY.settled && glow.settled
    if (hovering || !allSettled) {
      raf = requestAnimationFrame(loop)
    } else {
      raf = 0
      el.style.transform = ''
    }
  }

  function startLoop() {
    if (!raf) { lastTime = performance.now(); raf = requestAnimationFrame(loop) }
  }

  el.classList.add('liquid-glass')
  el.addEventListener('mouseenter', onEnter)
  el.addEventListener('mouseleave', onLeave)
  el.addEventListener('mousemove', onMove)
  el.addEventListener('mousedown', onDown)
  window.addEventListener('mouseup', onUp)

  return () => {
    el.removeEventListener('mouseenter', onEnter)
    el.removeEventListener('mouseleave', onLeave)
    el.removeEventListener('mousemove', onMove)
    el.removeEventListener('mousedown', onDown)
    window.removeEventListener('mouseup', onUp)
    if (raf) cancelAnimationFrame(raf)
  }
}

// ---- Vue directive: v-liquid ----
export const vLiquid = {
  mounted(el: HTMLElement, binding: any) {
    const opts = binding.value || {}
    const cleanup = attachJelly(el, {
      maxTilt: opts.maxTilt ?? 12,
      squash: opts.squash ?? 0.07,
      wobbleKick: opts.wobbleKick ?? 6,
      glowSize: opts.glowSize ?? 160,
      particleRate: opts.particleRate ?? 1,
      hoverScale: opts.scale ?? 1.03,
    })
    ;(el as any).__liquid_cleanup = cleanup
  },
  unmounted(el: HTMLElement) {
    (el as any).__liquid_cleanup?.()
  }
}

// ---- Composable version ----
export function useLiquidGlass(el: Ref<HTMLElement | null>, options?: {
  maxTilt?: number
  squash?: number
  wobbleKick?: number
  glowSize?: number
  particleRate?: number
  scale?: number
}) {
  let cleanup: (() => void) | null = null

  onMounted(() => {
    if (!el.value) return
    cleanup = attachJelly(el.value, {
      maxTilt: options?.maxTilt ?? 12,
      squash: options?.squash ?? 0.07,
      wobbleKick: options?.wobbleKick ?? 6,
      glowSize: options?.glowSize ?? 160,
      particleRate: options?.particleRate ?? 1,
      hoverScale: options?.scale ?? 1.03,
    })
  })

  onBeforeUnmount(() => {
    cleanup?.()
  })
}
