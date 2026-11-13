'use client'

import Link from 'next/link'
import { Box, Button, Flex, Text } from 'theme-ui'
import { Panel, StatusBadge, Progress, Empty } from '@/components/ui'
import { post } from '@/lib/api'
import { usePoll } from '@/lib/hooks'

const CARD = { bg: 'surface', border: '1px solid', borderColor: 'border', borderRadius: 'large', p: 3 }

function Metric({ label, value, hint, tone }) {
  return (
    <Box sx={CARD}>
      <Text sx={{ display: 'block', fontSize: 0, color: 'muted', textTransform: 'uppercase', letterSpacing: '.05em' }}>
        {label}
      </Text>
      <Text sx={{ display: 'block', fontSize: 6, fontWeight: 'bold', color: tone || 'text', lineHeight: 1.2, mt: 1 }}>
        {value}
      </Text>
      {hint && <Text sx={{ display: 'block', fontSize: 1, color: 'muted', mt: 1 }}>{hint}</Text>}
    </Box>
  )
}

export default function DashboardPage() {
  const health = usePoll('/api/health', 10000)
  const jobs = usePoll('/api/jobs?limit=6', 3000)
  const sessions = usePoll('/api/browser/sessions', 3000)
  const data = health.data

  const closeSessions = async () => {
    await post('/api/browser/sessions/close')
    sessions.reload()
  }

  return (
    <Box>
      <Flex sx={{ alignItems: 'flex-end', gap: 3, mb: 4, flexWrap: 'wrap' }}>
        <Box sx={{ flex: 1 }}>
          <Text as="h1" sx={{ fontSize: 6, fontWeight: 'bold' }}>Tổng quan</Text>
          <Text sx={{ color: 'muted', fontSize: 2 }}>
            Backend Python xử lý logic; giao diện này chỉ gọi API.
          </Text>
        </Box>
        <Flex sx={{ gap: 2 }}>
          <Button as={Link} href="/accounts" variant="secondary">Tài khoản</Button>
          <Button as={Link} href="/campaigns">Chạy chiến dịch</Button>
        </Flex>
      </Flex>

      <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 3, mb: 4 }}>
        <Metric
          label="Tài khoản"
          value={data ? data.accounts : '—'}
          hint="trong danh sách"
        />
        <Metric
          label="Chiến dịch"
          value={data ? data.campaigns : '—'}
          hint="đã lưu"
        />
        <Metric
          label="Recipe"
          value={data ? (data.recipe_ok ? 'OK' : 'Lỗi') : '—'}
          tone={data && !data.recipe_ok ? 'error' : 'ok'}
          hint={data ? data.recipe_message.slice(0, 60) : ''}
        />
        <Metric
          label="Thông tin đặt hàng"
          value={data ? (data.checkout_filled ? 'Đã nhập' : 'Trống') : '—'}
          hint="địa chỉ / thẻ"
        />
      </Box>

      <Box sx={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.4fr) minmax(0, 1fr)', gap: 3 }}>
        <Panel title="Tác vụ gần đây" subtitle="Kiểm tra tài khoản, chạy chiến dịch, kiểm tra proxy">
          {jobs.data && jobs.data.items.length > 0 ? (
            <Box>
              {jobs.data.items.map((job) => (
                <Box
                  key={job.id}
                  sx={{ px: 4, py: 3, borderBottom: '1px solid', borderColor: 'border' }}
                >
                  <Flex sx={{ alignItems: 'center', gap: 2, mb: 2 }}>
                    <StatusBadge status={job.status} />
                    <Text sx={{ flex: 1, fontSize: 2 }}>{job.title}</Text>
                    <Text sx={{ fontSize: 1, color: 'muted' }}>{job.started_at}</Text>
                  </Flex>
                  <Progress done={job.done} total={job.total} />
                  {job.message && (
                    <Text sx={{ display: 'block', fontSize: 1, color: 'muted', mt: 2 }}>
                      {job.message}
                    </Text>
                  )}
                </Box>
              ))}
            </Box>
          ) : (
            <Empty>Chưa có tác vụ nào.</Empty>
          )}
        </Panel>

        <Panel
          title="Cửa sổ Chrome đang mở"
          subtitle="Các tài khoản đang dừng ở bước thanh toán"
          actions={
            sessions.data && sessions.data.items.length > 0 ? (
              <Button variant="secondary" onClick={closeSessions} sx={{ fontSize: 1, px: 2, py: 1 }}>
                Đóng tất cả
              </Button>
            ) : null
          }
        >
          {sessions.data && sessions.data.items.length > 0 ? (
            <Box>
              {sessions.data.items.map((item) => (
                <Flex
                  key={item.email}
                  sx={{ px: 4, py: 3, borderBottom: '1px solid', borderColor: 'border', gap: 2 }}
                >
                  <Text sx={{ flex: 1, fontSize: 2 }}>{item.email}</Text>
                  <Text sx={{ fontSize: 1, color: 'muted' }}>cổng {item.port}</Text>
                </Flex>
              ))}
            </Box>
          ) : (
            <Empty>Không có cửa sổ nào đang chờ.</Empty>
          )}
        </Panel>
      </Box>
    </Box>
  )
}
