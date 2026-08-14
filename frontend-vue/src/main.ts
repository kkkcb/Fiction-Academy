import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import { reportError } from './utils/errorReport'
import { getTheme, setTheme } from './utils/theme'
import './styles/main.css'

const app = createApp(App)
app.use(createPinia())

app.config.errorHandler = (err, instance, info) => {
  console.error('[Vue Error]', info, err)
  reportError(err, info)
}

window.addEventListener('unhandledrejection', (e) => {
  console.error('[Unhandled Promise]', e.reason)
  reportError(e.reason, '未捕获的 Promise 异常')
})

setTheme(getTheme())

app.mount('#app')
