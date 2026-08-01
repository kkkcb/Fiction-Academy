import { ref, type Ref } from 'vue'

export interface RuntimeError {
  id: number
  message: string
  info: string
  stack?: string
}

export const runtimeErrors: Ref<RuntimeError[]> = ref([])
let counter = 0

export function reportError(err: unknown, info = ''): void {
  const id = ++counter
  const message = (err as Error | null | undefined)?.message || String(err)
  runtimeErrors.value.push({ id, message, info, stack: (err as Error | null | undefined)?.stack })
  setTimeout(() => {
    runtimeErrors.value = runtimeErrors.value.filter(e => e.id !== id)
  }, 6000)
}
