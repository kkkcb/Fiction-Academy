/**
 * 语音输入：浏览器原生 Web Speech API（Chrome/Edge 内置，实时识别，免费无 Key）。
 * 不支持的浏览器（如 Firefox 桌面版）由调用方禁用入口并提示。
 */
import { ref, onUnmounted } from 'vue'

/* ---- 最小类型声明（原生 API 尚未进 TS 标准 lib） ---- */
interface SRAlternative { transcript: string }
interface SRResult { readonly length: number; isFinal: boolean;[i: number]: SRAlternative }
interface SREvent { resultIndex: number; results: { readonly length: number;[i: number]: SRResult } }
interface SRErrorEvent { error: string }
interface SpeechRecognitionLike {
  lang: string
  continuous: boolean
  interimResults: boolean
  start(): void
  stop(): void
  onresult: ((e: SREvent) => void) | null
  onerror: ((e: SRErrorEvent) => void) | null
  onend: (() => void) | null
}
type SRCtor = new () => SpeechRecognitionLike

export function isVoiceInputSupported(): boolean {
  const w = window as unknown as { SpeechRecognition?: SRCtor; webkitSpeechRecognition?: SRCtor }
  return !!(w.SpeechRecognition || w.webkitSpeechRecognition)
}

export interface VoiceInputOptions {
  onFinalText: (text: string) => void
  onError?: (message: string) => void
}

export function useVoiceInput(opts: VoiceInputOptions) {
  const recording = ref(false)
  const interim = ref('')
  let recognition: SpeechRecognitionLike | null = null
  let wantActive = false
  let emptyEnds = 0   // 无有效结果的自动结束次数（用于熔断无限重连）
  let lastError = ''

  function stop() {
    wantActive = false
    try { recognition?.stop() } catch { /* already stopped */ }
    recognition = null
    recording.value = false
    interim.value = ''
  }

  /** 同一条错误只报一次，避免重连循环刷屏 */
  function reportOnce(msg: string) {
    if (msg === lastError) return
    lastError = msg
    opts.onError?.(msg)
  }

  function start() {
    if (recording.value) return
    const w = window as unknown as { SpeechRecognition?: SRCtor; webkitSpeechRecognition?: SRCtor }
    const Ctor = w.SpeechRecognition || w.webkitSpeechRecognition
    if (!Ctor) {
      opts.onError?.('当前浏览器不支持语音输入，请使用 Chrome 或 Edge')
      return
    }
    recognition = new Ctor()
    recognition.lang = 'zh-CN'
    recognition.continuous = true
    recognition.interimResults = true

    recognition.onresult = (e) => {
      let interimText = ''
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i]
        const t = r[0]?.transcript || ''
        if (r.isFinal) {
          const final = t.trim()
          if (final) {
            emptyEnds = 0
            opts.onFinalText(final)
          }
        } else {
          interimText += t
        }
      }
      interim.value = interimText
    }

    recognition.onerror = (e) => {
      switch (e.error) {
        // 致密不可恢复错误：停止，不进入重连
        case 'not-allowed':
        case 'service-not-allowed':
          reportOnce('麦克风权限被拒绝，请在浏览器地址栏允许麦克风后重试')
          stop()
          return
        case 'audio-capture':
          reportOnce('未检测到麦克风设备')
          stop()
          return
        case 'network':
          reportOnce('语音服务连接失败，请确认使用 Chrome/Edge 且网络可用')
          stop()
          return
        // no-speech / aborted 等瞬态错误：交给 onend 重连逻辑
        default:
          return
      }
    }

    recognition.onend = () => {
      if (!wantActive) return
      // Chrome 静音后自动停止属正常，续上即可；但连续多次结束且没有任何
      // 识别结果说明服务不可达——熔断退出，避免无限重连刷屏
      emptyEnds += 1
      if (emptyEnds > 3) {
        reportOnce('语音服务无响应，已停止（请检查网络或改用 Chrome/Edge）')
        stop()
        return
      }
      try { recognition?.start() } catch { /* restart 竞态可忽略 */ }
    }

    wantActive = true
    emptyEnds = 0
    lastError = ''
    try {
      recognition.start()
    } catch {
      opts.onError?.('无法启动语音识别')
      wantActive = false
      return
    }
    recording.value = true
  }

  function toggle() {
    if (recording.value) stop()
    else start()
  }

  onUnmounted(stop)

  return { recording, interim, start, stop, toggle }
}
