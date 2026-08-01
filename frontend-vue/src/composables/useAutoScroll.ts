import { ref, watch, onUnmounted, type Ref } from 'vue'

const NEAR_THRESHOLD = 120
const RESUME_THRESHOLD = 40

export interface AutoScrollHandle {
  el: Ref<HTMLElement | null>
  isNearBottom: Ref<boolean>
  onScroll: () => void
  scrollToBottom: (force?: boolean) => void
  reset: () => void
}

export function useAutoScroll(): AutoScrollHandle {
  const el = ref<HTMLElement | null>(null)
  const isNearBottom = ref(true)
  let listener: (() => void) | null = null

  const compute = () => {
    const node = el.value
    if (!node) return
    const dist = node.scrollHeight - node.scrollTop - node.clientHeight
    if (!isNearBottom.value && dist < RESUME_THRESHOLD) {
      isNearBottom.value = true
    } else if (isNearBottom.value && dist > NEAR_THRESHOLD) {
      isNearBottom.value = false
    }
  }

  const onScroll = () => compute()

  const scrollToBottom = (force = false) => {
    const node = el.value
    if (!node) return
    if (force || isNearBottom.value) {
      node.scrollTop = node.scrollHeight
    }
  }

  const reset = () => {
    isNearBottom.value = true
  }

  watch(el, (node, oldNode) => {
    if (oldNode && listener) {
      oldNode.removeEventListener('scroll', listener)
    }
    if (node) {
      listener = compute
      node.addEventListener('scroll', listener, { passive: true })
      compute()
    }
  })

  onUnmounted(() => {
    if (el.value && listener) {
      el.value.removeEventListener('scroll', listener)
    }
  })

  return { el, onScroll, scrollToBottom, isNearBottom, reset }
}
