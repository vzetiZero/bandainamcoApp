'use client'

import { useCallback, useMemo, useState } from 'react'
import { Badge, Box, Button, Flex, Input, Select, Text } from 'theme-ui'
import { Empty, Panel, Progress, StatusBadge, Toolbar, TextField, SelectField } from '@/components/ui'
import { del, post } from '@/lib/api'
import { useJob, usePoll } from '@/lib/hooks'

const STATUS_OPTIONS = [
  { value: '', label: 'Tất cả trạng thái' },
  { value: 'Hoạt động', label: 'Hoạt động' },
  { value: 'Không hoạt động', label: 'Không hoạt động' },
  { value: 'Chưa kiểm tra', label: 'Chưa kiểm tra' },
]

export default function AccountsPage() {
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('')
  const [selected, setSelected] = useState([])
  const [importText, setImportText] = useState('')
  const [message, setMessage] = useState('')
  const [nameFor, setNameFor] = useState(null)
  const [lastName, setLastName] = useState('')
  const [firstName, setFirstName] = useState('')

  const list = usePoll(
    `/api/accounts?query=${encodeURIComponent(query)}&status=${encodeURIComponent(status)}`,
    8000,
    [query, status],
  )
  const { job, track } = useJob(() => list.reload())

  const items = list.data?.items || []
  const counts = list.data?.counts || {}
  const allSelected = items.length > 0 && selected.length === items.length

  const toggle = (email) => {
    setSelected((current) =>
      current.includes(email) ? current.filter((item) => item !== email) : [...current, email],
    )
  }

  const checkSelected = useCallback(async () => {
    const body = selected.length ? { emails: selected } : { all: true }
    try {
      const started = await post('/api/accounts/check', body)
      track(started)
      setMessage(selected.length ? `Đang kiểm tra ${selected.length} tài khoản` : 'Đang kiểm tra tất cả')
    } catch (err) {
      setMessage(err.message)
    }
  }, [selected, track])

  const doImport = async () => {
    try {
      const result = await post('/api/accounts/import', { text: importText })
      setMessage(`Đã thêm ${result.added}, bỏ qua ${result.skipped}`)
      setImportText('')
      list.reload()
    } catch (err) {
      setMessage(err.message)
    }
  }

  const removeSelected = async () => {
    if (!selected.length) return
    if (!window.confirm(`Xoá ${selected.length} tài khoản khỏi danh sách?`)) return
    try {
      const result = await del('/api/accounts', { emails: selected })
      setMessage(`Đã xoá ${result.deleted} tài khoản`)
      setSelected([])
      list.reload()
    } catch (err) {
      setMessage(err.message)
    }
  }

  const submitName = async () => {
    try {
      const started = await post(`/api/accounts/${encodeURIComponent(nameFor)}/name`, {
        last_name: lastName,
        first_name: firstName,
      })
      track(started)
      setNameFor(null)
    } catch (err) {
      setMessage(err.message)
    }
  }

  const jobDone = useMemo(() => {
    if (!job || job.status === 'running') return null
    return `${job.message || job.status}`
  }, [job])

  return (
    <Box>
      <Flex sx={{ alignItems: 'flex-end', mb: 4, gap: 3, flexWrap: 'wrap' }}>
        <Box sx={{ flex: 1 }}>
          <Text as="h1" sx={{ fontSize: 6, fontWeight: 'bold' }}>Tài khoản</Text>
          <Text sx={{ color: 'muted', fontSize: 2 }}>
            {counts.total || 0} tài khoản · {counts.active || 0} hoạt động · {counts.inactive || 0} lỗi
          </Text>
        </Box>
        <Flex sx={{ gap: 2 }}>
          <Button variant="secondary" onClick={checkSelected} disabled={job?.status === 'running'}>
            {selected.length ? `Kiểm tra ${selected.length}` : 'Kiểm tra tất cả'}
          </Button>
          <Button variant="danger" onClick={removeSelected} disabled={!selected.length}>
            Xoá
          </Button>
        </Flex>
      </Flex>

      {(job || message) && (
        <Panel sx={{ mb: 3 }} title="Tiến trình" subtitle={jobDone || message}>
          {job && <Box sx={{ p: 4 }}><Progress done={job.done} total={job.total} /></Box>}
        </Panel>
      )}

      <Box sx={{ display: 'grid', gridTemplateColumns: 'minmax(0, 2.2fr) minmax(0, 1fr)', gap: 3 }}>
        <Panel title="Danh sách" subtitle={`${items.length} dòng hiển thị`}>
          <Toolbar>
            <Input
              placeholder="Tìm theo email"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              sx={{ maxWidth: 260 }}
            />
            <Select
              value={status}
              onChange={(event) => setStatus(event.target.value)}
              sx={{ maxWidth: 200 }}
            >
              {STATUS_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </Select>
            <Box sx={{ flex: 1 }} />
            <Button
              variant="ghost"
              onClick={() => setSelected(allSelected ? [] : items.map((item) => item.email))}
            >
              {allSelected ? 'Bỏ chọn' : 'Chọn tất cả'}
            </Button>
          </Toolbar>

          <Box sx={{ overflowX: 'auto' }}>
            <table>
              <thead>
                <tr>
                  <th style={{ width: 36 }} />
                  <th>Email</th>
                  <th>Trạng thái</th>
                  <th>Kiểm tra gần nhất</th>
                  <th>Tên (hồ sơ)</th>
                  <th style={{ width: 120 }} />
                </tr>
              </thead>
              <tbody>
                {items.map((account) => (
                  <tr key={account.email}>
                    <td>
                      <input
                        type="checkbox"
                        checked={selected.includes(account.email)}
                        onChange={() => toggle(account.email)}
                      />
                    </td>
                    <td>
                      <Text sx={{ fontSize: 2 }}>{account.email}</Text>
                      {account.token && <Badge variant="muted" sx={{ ml: 2 }}>token</Badge>}
                    </td>
                    <td><StatusBadge status={account.status} /></td>
                    <td><Text sx={{ fontSize: 1, color: 'muted' }}>{account.last_check || '—'}</Text></td>
                    <td>
                      <Text sx={{ fontSize: 1, color: 'muted' }}>
                        {[account.last_name_kanji, account.first_name_kanji].filter(Boolean).join(' ') || account.nickname || '—'}
                      </Text>
                    </td>
                    <td>
                      <Button
                        variant="ghost"
                        onClick={() => {
                          setNameFor(account.email)
                          setLastName('')
                          setFirstName('')
                        }}
                      >
                        Đổi tên
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Box>
          {items.length === 0 && <Empty>Không có tài khoản nào khớp bộ lọc.</Empty>}
        </Panel>

        <Box>
          <Panel title="Thêm tài khoản" subtitle="Mỗi dòng: email|password|token" sx={{ mb: 3 }}>
            <Box sx={{ p: 3 }}>
              <Box
                as="textarea"
                rows={7}
                value={importText}
                onChange={(event) => setImportText(event.target.value)}
                placeholder={'email1|password1\nemail2|password2'}
                sx={{
                  width: '100%', fontFamily: 'mono', fontSize: 1, p: 2,
                  border: '1px solid', borderColor: 'border', borderRadius: 'small',
                  bg: 'surface', color: 'text',
                }}
              />
              <Flex sx={{ gap: 2, mt: 2 }}>
                <Button onClick={doImport} disabled={!importText.trim()}>Thêm</Button>
                <Button variant="ghost" onClick={() => setImportText('')}>Xoá nội dung</Button>
              </Flex>
            </Box>
          </Panel>

          {nameFor && (
            <Panel title="Đổi tên" subtitle={nameFor}>
              <Box sx={{ p: 3 }}>
                <TextField
                  label="Họ (姓)"
                  value={lastName}
                  onChange={(event) => setLastName(event.target.value)}
                  placeholder="Để trống = giữ nguyên"
                />
                <TextField
                  label="Tên (名)"
                  value={firstName}
                  onChange={(event) => setFirstName(event.target.value)}
                  placeholder="Để trống = giữ nguyên"
                />
                <Flex sx={{ gap: 2 }}>
                  <Button onClick={submitName}>Lưu</Button>
                  <Button variant="ghost" onClick={() => setNameFor(null)}>Huỷ</Button>
                </Flex>
              </Box>
            </Panel>
          )}
        </Box>
      </Box>
    </Box>
  )
}

