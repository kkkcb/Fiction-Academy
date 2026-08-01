import { ref, computed, unref, type Ref } from 'vue'
import { SLASH_COMMANDS, type SlashCommand } from '../utils/format'

export interface SlashCommandHandle {
  popoverOpen: Ref<boolean>
  matchedCommands: Ref<SlashCommand[]>
  activeIndex: Ref<number>
  handleInput: () => void
  handleKeydown: (e: KeyboardEvent) => boolean
  applyCommand: (item?: SlashCommand) => void
  closePopover: () => void
}

export function useSlashCommands(
  inputText: Ref<string>,
  currentPoint: Ref<string | null>,
): SlashCommandHandle {
  const popoverOpen = ref(false)
  const activeIndex = ref(0)

  const matchedCommands = computed(() => {
    const val = unref(inputText)
    const isPoint = !!unref(currentPoint)
    if (!val || !val.startsWith('/') || /\s/.test(val.slice(1))) return [] as SlashCommand[]
    const q = val.toLowerCase()
    return SLASH_COMMANDS.filter(c => (!c.pointOnly || isPoint) && c.cmd.toLowerCase().startsWith(q))
  })

  const handleInput = () => {
    activeIndex.value = 0
    popoverOpen.value = matchedCommands.value.length > 0
  }

  const closePopover = () => {
    popoverOpen.value = false
    activeIndex.value = 0
  }

  const applyCommand = (item?: SlashCommand) => {
    const target = item || matchedCommands.value[activeIndex.value]
    if (!target) return
    inputText.value = target.cmd + ' '
    closePopover()
  }

  const handleKeydown = (e: KeyboardEvent): boolean => {
    const items = matchedCommands.value
    if (!popoverOpen.value || items.length === 0) return false
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      activeIndex.value = (activeIndex.value + 1) % items.length
      return true
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault()
      activeIndex.value = (activeIndex.value - 1 + items.length) % items.length
      return true
    }
    if ((e.key === 'Enter' && !e.shiftKey) || e.key === 'Tab') {
      const target = items[activeIndex.value]
      if (target) {
        e.preventDefault()
        applyCommand(target)
        return true
      }
    }
    if (e.key === 'Escape') {
      e.preventDefault()
      closePopover()
      return true
    }
    return false
  }

  return { popoverOpen, matchedCommands, activeIndex, handleInput, handleKeydown, applyCommand, closePopover }
}
