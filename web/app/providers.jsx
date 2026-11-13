'use client'

import { ThemeProvider } from 'theme-ui'
import { useEffect, useState } from 'react'
import { makeTheme } from '@/theme'

// ThemeProvider là client component. Nền sáng/tối đổi qua sự kiện 'ui-mode-change'
// để mọi nơi (AppShell) không cần context riêng.
export default function Providers({ children }) {
  const [mode, setMode] = useState('light')

  useEffect(() => {
    const read = () => {
      const saved = window.localStorage.getItem('ui-mode')
      setMode(saved === 'dark' ? 'dark' : 'light')
    }
    read()
    window.addEventListener('ui-mode-change', read)
    window.addEventListener('storage', read)
    return () => {
      window.removeEventListener('ui-mode-change', read)
      window.removeEventListener('storage', read)
    }
  }, [])

  return <ThemeProvider theme={makeTheme(mode)}>{children}</ThemeProvider>
}
