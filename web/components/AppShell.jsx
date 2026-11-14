'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useState } from 'react'
import { Box, Button, Flex, Text } from 'theme-ui'
import { API_BASE } from '@/lib/api'
import { useLogs, usePoll } from '@/lib/hooks'

const NAV = [
  { href: '/', label: 'Tổng quan' },
  { href: '/accounts', label: 'Tài khoản' },
  { href: '/campaigns', label: 'Chiến dịch' },
  { href: '/settings', label: 'Cấu hình' },
]

// Trang có bảng dài (tài khoản, chiến dịch) dùng hết chiều ngang cửa sổ; trang
// còn lại giữ bề ngang đọc thoải mái.
const WIDE_ROUTES = ['/accounts', '/campaigns']

const LOG_TONE = { info: 'text', ok: 'ok', warn: 'warn', error: 'error' }

export default function AppShell({ children }) {
  const pathname = usePathname()
  const logs = useLogs(2000)
  const [open, setOpen] = useState(false)
  const [mode, setMode] = useState('light')
  const health = usePoll('/api/health', 15000)

  useEffect(() => {
    const saved = typeof window !== 'undefined' ? window.localStorage.getItem('ui-mode') : null
    if (saved) setMode(saved)
  }, [])

  const toggleMode = () => {
    const next = mode === 'light' ? 'dark' : 'light'
    setMode(next)
    if (typeof window !== 'undefined') {
      window.localStorage.setItem('ui-mode', next)
      window.dispatchEvent(new Event('ui-mode-change'))
    }
  }

  const apiDown = Boolean(health.error)
  const summary = health.data
  const wide = WIDE_ROUTES.some((route) => pathname.startsWith(route))

  return (
    <Flex sx={{ minHeight: '100vh' }}>
      {/* Sidebar */}
      <Box
        sx={{
          width: 'sidebar', flexShrink: 0, borderRight: '1px solid', borderColor: 'border',
          bg: 'surface', display: 'flex', flexDirection: 'column',
          position: 'sticky', top: 0, height: '100vh',
        }}
      >
        <Flex sx={{ alignItems: 'center', gap: 2, px: 3, py: 4 }}>
          <Box sx={{ width: 10, height: 10, borderRadius: 'pill', bg: 'accent' }} />
          <Box>
            <Text sx={{ display: 'block', fontWeight: 'bold', fontSize: 2, lineHeight: 1.2 }}>
              NAMCO
            </Text>
            <Text sx={{ display: 'block', fontSize: 0, color: 'muted' }}>
              Account Manager
            </Text>
          </Box>
        </Flex>

        <Box sx={{ px: 2, flex: 1 }}>
          {NAV.map((item) => {
            const active = item.href === '/' ? pathname === '/' : pathname.startsWith(item.href)
            return (
              <Link
                key={item.href}
                href={item.href}
                style={{
                  display: 'block', padding: '9px 12px', marginBottom: 2,
                  borderRadius: 8, fontSize: 13, fontWeight: 500,
                  color: active ? 'var(--accent, #d61718)' : 'inherit',
                  background: active ? 'rgba(214,23,24,.10)' : 'transparent',
                  textDecoration: 'none',
                }}
              >
                {item.label}
              </Link>
            )
          })}
        </Box>

        <Box sx={{ p: 3, borderTop: '1px solid', borderColor: 'border', fontSize: 1 }}>
          <Flex sx={{ alignItems: 'center', gap: 2, mb: 2 }}>
            <Box
              sx={{
                width: 8, height: 8, borderRadius: 'pill',
                bg: apiDown ? 'error' : 'ok',
              }}
            />
            <Text sx={{ color: 'muted' }}>
              {apiDown ? 'API chưa chạy' : 'API sẵn sàng'}
            </Text>
          </Flex>
          {summary && (
            <Text sx={{ display: 'block', fontSize: 0, color: 'muted' }}>
              {summary.accounts} tài khoản · {summary.campaigns} chiến dịch
              {summary.recipe_ok ? '' : ' · recipe lỗi'}
            </Text>
          )}
          <Flex sx={{ gap: 1, mt: 3 }}>
            <Button variant="ghost" onClick={toggleMode} sx={{ fontSize: 1, px: 2, py: 1 }}>
              {mode === 'light' ? 'Nền tối' : 'Nền sáng'}
            </Button>
            <Button variant="ghost" onClick={() => setOpen(!open)} sx={{ fontSize: 1, px: 2, py: 1 }}>
              Nhật ký
            </Button>
          </Flex>
        </Box>
      </Box>

      {/* Nội dung */}
      <Box sx={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        {apiDown && (
          <Box sx={{ px: 4, py: 2, bg: 'errorSoft', color: 'error', fontSize: 2 }}>
            Không kết nối được API tại {API_BASE}. Chạy <code>python server.py</code> trong
            thư mục dự án.
          </Box>
        )}
        <Box
          sx={{
            p: 4, width: '100%', mx: 'auto', flex: 1, minHeight: 0,
            display: 'flex', flexDirection: 'column',
            maxWidth: wide ? '100%' : 'content',
          }}
        >
          {children}
        </Box>

        {/* Dock nhật ký */}
        <Box
          sx={{
            borderTop: '1px solid', borderColor: 'border', bg: 'surface',
            maxHeight: open ? 240 : 40, transition: 'max-height .2s ease', overflow: 'hidden',
          }}
        >
          <Flex
            sx={{
              px: 4, py: 2, alignItems: 'center', gap: 2, cursor: 'pointer',
              fontSize: 1, color: 'muted',
            }}
            onClick={() => setOpen(!open)}
          >
            <Text sx={{ flex: 1 }}>Nhật ký {logs.length ? `(${logs.length})` : ''}</Text>
            <Text sx={{ fontSize: 0 }}>{open ? 'thu gọn' : 'mở rộng'}</Text>
          </Flex>
          {open && (
            <Box sx={{ px: 4, pb: 3, maxHeight: 190, overflowY: 'auto' }}>
              {logs.length === 0 && <Text sx={{ fontSize: 1, color: 'muted' }}>Chưa có dòng nào.</Text>}
              {logs.slice(0, 120).map((line) => (
                <Flex key={line.seq} sx={{ gap: 2, fontSize: 1, py: '1px' }}>
                  <Text sx={{ color: 'muted', minWidth: 62 }}>{line.at}</Text>
                  <Text sx={{ color: LOG_TONE[line.level] || 'text', wordBreak: 'break-word' }}>
                    {line.message}
                  </Text>
                </Flex>
              ))}
            </Box>
          )}
        </Box>
      </Box>
    </Flex>
  )
}
