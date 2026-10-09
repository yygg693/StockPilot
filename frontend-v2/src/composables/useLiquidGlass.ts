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
  if (particles.length > 150) particles.splice(0, particles.length - 150)
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
  // Jelly springs - LOW damping for visible wobble oscillation
  const tiltX = new JellySpring(150, 10)   // rotateX
  const tiltY = new JellySpring(150, 10)   // rotateY
  const scaleX = new JellySpring(100, 7)   // horizontal stretch (VERY bouncy)
  const scaleY = new JellySpring(100, 7)   // vertical squash (VERY bouncy)
  const glow = new JellySpring(200, 20)    // glow intensity

  let raf = 0
  let hovering = false
  let pressing = false
  let mouseX = 0.5
  let mouseY = 0.5
  let lastEmit = 0
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
    tiltX.target = 0
    tiltY.target = 0
    scaleX.target = 1
    scaleY.target = 1
    glow.target = 0
  }

  function onMove(e: MouseEvent) {
    const rect = el.getBoundingClientRect()
    mouseX = (e.clientX - rect.left) / rect.width
    mouseY = (e.clientY - rect.top) / rect.height

    // Tilt follows cursor
    tiltX.target = (mouseY - 0.5) * -2 * cfg.maxTilt
    tiltY.target = (mouseX - 0.5) * 2 * cfg.maxTilt

    // Glow position
    el.style.setProperty('--glow-x', (mouseX * 100) + '%')
    el.style.setProperty('--glow-y', (mouseY * 100) + '%')
    el.style.setProperty('--glow-size', cfg.glowSize + 'px')

    // Subtle particles on move (less frequent)
    const now = performance.now()
    if (now - lastEmit > 120) {
      emitParticles(e.clientX, e.clientY, 1, pressing ? 2 : 1)
      lastEmit = now
    }
  }

  function onDown(e: MouseEvent) {
    pressing = true
    // SQUASH: press down = flatten vertically, stretch horizontally
    scaleX.target = cfg.hoverScale * (1 + cfg.squash)
    scaleY.target = cfg.hoverScale * (1 - cfg.squash * 1.4)
    // Kick for immediate response
    scaleX.kick(3)
    scaleY.kick(-4)
    // Small particle burst
    emitParticles(e.clientX, e.clientY, 6, 2.5)
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

    const rx = tiltX.update(dt)
    const ry = tiltY.update(dt)
    const sx = scaleX.update(dt)
    const sy = scaleY.update(dt)
    const g = glow.update(dt)

    // Apply transform: perspective + tilt + squash-stretch
    el.style.transform =
      'perspective(700px) ' +
      'rotateX(' + rx.toFixed(2) + 'deg) ' +
      'rotateY(' + ry.toFixed(2) + 'deg) ' +
      'scaleX(' + sx.toFixed(4) + ') ' +
      'scaleY(' + sy.toFixed(4) + ')'

    el.style.setProperty('--press', g.toFixed(3))

    const allSettled = tiltX.settled && tiltY.settled && scaleX.settled && scaleY.settled
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
