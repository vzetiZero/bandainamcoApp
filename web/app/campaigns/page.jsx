'use client'

import { useMemo, useState } from 'react'
import { Badge, Box, Button, Flex, Input, Select, Text } from 'theme-ui'
import { Empty, Panel, Progress, ScrollTable, StatusBadge, TextField, CheckField } from '@/components/ui'
import { del, get, post, put } from '@/lib/api'
import { useJob, usePoll } from '@/lib/hooks'

const BLANK = { name: '', url: '', opens_at: '', closes_at: '', notes: '' }

// Ô chọn ngày/giờ của trình duyệt dùng dạng "YYYY-MM-DDTHH:MM", còn API lưu
// "YYYY-MM-DD HH:MM" — đổi qua lại ở đây để form luôn hiện đúng giá trị đã lưu.
const toInputTime = (text) => {
  const raw = String(text || '').trim().replace(' ', 'T')
  return /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(raw) ? raw.slice(0, 16) : ''
}
const fromInputTime = (value) => String(value || '').replace('T', ' ')

export default function CampaignsPage() {
  const campaigns = usePoll('/api/campaigns', 15000)
  const accounts = usePoll('/api/accounts', 20000)
  const settings = usePoll('/api/settings', 20000)
  const sessions = usePoll('/api/browser/sessions', 4000)

  const [form, setForm] = useState(BLANK)
  const [editingRow, setEditingRow] = useState(null)
  const [message, setMessage] = useState('')
  const [selectedRow, setSelectedRow] = useState(null)
  const [signups, setSignups] = useState([])
  const [runEmails, setRunEmails] = useState([])
  const [slot, setSlot] = useState('')
  const [submitEnabled, setSubmitEnabled] = useState(false)
  const [useAccountAddress, setUseAccountAddress] = useState(true)
  const [clearCart, setClearCart] = useState(false)
  const [useProxy, setUseProxy] = useState(true)

  const { job, track } = useJob(() => {
    campaigns.reload()
    sessions.reload()
  })

  const items = campaigns.data?.items || []
  const accountItems = accounts.data?.items || []
  const current = selectedRow !== null ? items[selectedRow] : null
  const running = job?.status === 'running'

  const loadSignups = async (row) => {
    setSelectedRow(row)
    const result = await get(`/api/campaigns/${row}/signups`).catch(() => ({ signups: [] }))
    setSignups(result.signups || [])
  }

  const saveCampaign = async () => {
    const payload = {
      ...form,
      opens_at: fromInputTime(form.opens_at),
      closes_at: fromInputTime(form.closes_at),
    }
    try {
      if (editingRow === null) {
        await post('/api/campaigns', payload)
      } else {
        await put(`/api/campaigns/${editingRow}`, payload)
      }
      setForm(BLANK)
      setEditingRow(null)
      campaigns.reload()
      setMessage('Đã lưu chiến dịch')
    } catch (err) {
      setMessage(err.message)
    }
  }

  const editCampaign = (row) => {
    const campaign = items[row]
    setEditingRow(row)
    setForm({
      name: campaign.name || '',
      url: campaign.url || '',
      opens_at: toInputTime(campaign.opens_at),
      closes_at: toInputTime(campaign.closes_at),
      notes: campaign.notes || '',
    })
  }

  const removeCampaign = async (row) => {
    if (!window.confirm('Xoá chiến dịch này?')) return
    try {
      await del(`/api/campaigns/${row}`)
      campaigns.reload()
      if (selectedRow === row) {
        setSelectedRow(null)
        setSignups([])
      }
    } catch (err) {
      setMessage(err.message)
    }
  }

  const toggleRun = (email) => {
    setRunEmails((current) =>
      current.includes(email) ? current.filter((item) => item !== email) : [...current, email],
    )
  }

  const startRun = async () => {
    if (!current) {
      setMessage('Chọn một chiến dịch trong bảng trước')
      return
    }
    const targets = runEmails.length
      ? runEmails
      : accountItems
          .filter((account) => account.status !== 'Không hoạt động')
          .map((account) => account.email)
    if (!targets.length) {
      setMessage('Không có tài khoản nào để chạy')
      return
    }
    try {
      const started = await post('/api/browser/run', {
        campaign_row: selectedRow,
        emails: targets,
        submit: submitEnabled,
        slot,
        use_account_address: useAccountAddress,
        clear_cart: clearCart,
        use_proxy: useProxy,
      })
      track(started)
      setMessage(`Đang chạy cho ${targets.length} tài khoản`)
    } catch (err) {
      setMessage(err.message)
    }
  }

  const closeSessions = async () => {
    await post('/api/browser/sessions/close')
    sessions.reload()
  }

  const slotOptions = useMemo(() => {
    const dates = ['1121', '1122', '1123', '1124']
    const times = ['1100', '1330', '1600', '1830']
    const options = [{ value: '', label: 'Mặc định trong recipe' }]
    dates.forEach((date) => {
      times.forEach((time) => {
        const value = `159016_${date}_${time}_1`
        options.push({ value, label: `${date.slice(2, 4)}/${date.slice(4, 6)} ${time.slice(0, 2)}:${time.slice(2)}` })
      })
    })
    return options
  }, [])

  return (
    <Box>
      <Flex sx={{ alignItems: 'flex-end', mb: 4, gap: 3, flexWrap: 'wrap' }}>
        <Box sx={{ flex: 1 }}>
          <Text as="h1" sx={{ fontSize: 6, fontWeight: 'bold' }}>Chiến dịch</Text>
          <Text sx={{ color: 'muted', fontSize: 2 }}>
            {items.length} chiến dịch · {campaigns.data?.file?.split(/[\\/]/).pop() || 'campaigns.json'} · recipe: {settings.data?.browser?.recipe_path?.split(/[\\/]/).pop() || '—'}
          </Text>
        </Box>
        <Flex sx={{ gap: 2 }}>
          <Button variant="secondary" as="a" href="/api/health" target="_blank">Kiểm tra API</Button>
          <Button onClick={startRun} disabled={running || !current}>
            {running ? 'Đang chạy…' : 'Chạy bằng Chrome'}
          </Button>
        </Flex>
      </Flex>

      {(job || message) && (
        <Panel
          sx={{ mb: 3 }}
          title={job ? job.title : 'Thông báo'}
          subtitle={job ? job.message || job.status : message}
        >
          {job && (
            <Box sx={{ p: 4 }}>
              <Progress done={job.done} total={job.total} />
              <Box sx={{ mt: 3, maxHeight: 180, overflowY: 'auto' }}>
                {job.items.map((item) => (
                  <Flex key={item.email} sx={{ gap: 2, fontSize: 1, py: '2px' }}>
                    <StatusBadge status={item.status || (item.ok ? 'ok' : 'error')} />
                    <Text sx={{ minWidth: 200 }}>{item.email}</Text>
                    <Text sx={{ color: 'muted', flex: 1 }}>{item.message}</Text>
                    {item.proxy && <Text sx={{ color: 'muted', fontSize: 0 }}>{item.proxy}</Text>}
                  </Flex>
                ))}
              </Box>
            </Box>
          )}
        </Panel>
      )}

      <Box sx={{ display: 'grid', gridTemplateColumns: 'minmax(0, 2.1fr) minmax(0, 1fr)', gap: 3 }}>
        <Box>
          <Panel title="Danh sách chiến dịch" subtitle="Bấm một dòng để chọn và xem đăng ký">
            <ScrollTable maxHeight="min(46vh, 420px)">
                <thead>
                  <tr>
                    <th>Tên</th>
                    <th>Trạng thái</th>
                    <th>Còn lại</th>
                    <th>Đã ĐK</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {items.map((campaign, row) => (
                    <tr
                      key={`${campaign.name}-${row}`}
                      onClick={() => loadSignups(row)}
                      style={{
                        cursor: 'pointer',
                        background: selectedRow === row ? 'rgba(214,23,24,.07)' : undefined,
                      }}
                    >
                      <td>
                        <Text sx={{ fontSize: 2 }}>{campaign.name}</Text>
                        <Text sx={{ display: 'block', fontSize: 0, color: 'muted' }}>
                          {campaign.url}
                        </Text>
                      </td>
                      <td><StatusBadge status={campaign.status} /></td>
                      <td><Text sx={{ fontSize: 1, color: 'muted' }}>{campaign.remaining || '—'}</Text></td>
                      <td><Badge variant="info">{campaign.signup_count}</Badge></td>
                      <td>
                        <Flex sx={{ gap: 1, justifyContent: 'flex-end' }}>
                          <Button variant="ghost" onClick={(event) => { event.stopPropagation(); editCampaign(row) }}>
                            Sửa
                          </Button>
                          <Button variant="ghost" onClick={(event) => { event.stopPropagation(); removeCampaign(row) }}>
                            Xoá
                          </Button>
                        </Flex>
                      </td>
                    </tr>
                  ))}
                </tbody>
            </ScrollTable>
            {items.length === 0 && <Empty>Chưa có chiến dịch nào.</Empty>}
          </Panel>

          <Panel sx={{ mt: 3 }} title={editingRow === null ? 'Thêm chiến dịch' : `Sửa dòng ${editingRow + 1}`}>
            <Box sx={{ p: 3, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 3 }}>
              <TextField
                label="Tên chiến dịch"
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
                sx={{ gridColumn: 'span 2' }}
              />
              <TextField
                label="Link chính thức"
                value={form.url}
                onChange={(event) => setForm({ ...form, url: event.target.value })}
                placeholder="https://parks2.bandainamco-am.co.jp/item/…"
                sx={{ gridColumn: 'span 2' }}
              />
              <TextField
                label="Mở đăng ký"
                type="datetime-local"
                value={form.opens_at}
                onChange={(event) => setForm({ ...form, opens_at: event.target.value })}
                hint="Bấm vào ô để chọn ngày và giờ. Để trống nếu chưa biết."
              />
              <TextField
                label="Đóng đăng ký"
                type="datetime-local"
                value={form.closes_at}
                onChange={(event) => setForm({ ...form, closes_at: event.target.value })}
                hint="Giờ đóng tính cả phút — 23:59 là hết ngày."
              />
              <TextField
                label="Ghi chú"
                value={form.notes}
                onChange={(event) => setForm({ ...form, notes: event.target.value })}
                sx={{ gridColumn: 'span 2' }}
              />
              <Flex sx={{ gap: 2, gridColumn: 'span 2' }}>
                <Button onClick={saveCampaign}>Lưu</Button>
                {editingRow !== null && (
                  <Button variant="ghost" onClick={() => { setEditingRow(null); setForm(BLANK) }}>
                    Huỷ
                  </Button>
                )}
              </Flex>
            </Box>
          </Panel>
        </Box>

        <Box>
          <Panel title="Chạy tự động" subtitle={current ? current.name : 'Chọn một chiến dịch'}>
            <Box sx={{ p: 3 }}>
              <Select
                value={slot}
                onChange={(event) => setSlot(event.target.value)}
                sx={{ mb: 3 }}
              >
                {slotOptions.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </Select>
              <CheckField
                label="Dùng địa chỉ riêng của từng tài khoản"
                checked={useAccountAddress}
                onChange={(event) => setUseAccountAddress(event.target.checked)}
                hint="Địa chỉ lấy từ hồ sơ Parks2 đã đọc của chính tài khoản đó; hồ sơ chung chỉ dùng cho phần còn thiếu và thẻ."
              />
              <CheckField
                label="Xoá giỏ cũ trước khi thêm slot"
                checked={clearCart}
                onChange={(event) => setClearCart(event.target.checked)}
                hint="Bật khi đổi khung giờ: giỏ Parks2 giữ theo tài khoản, không xoá thì đơn sẽ gồm cả dòng slot cũ."
              />
              <CheckField
                label="Dùng proxy (proxy.txt)"
                checked={useProxy}
                onChange={(event) => setUseProxy(event.target.checked)}
                hint="Tắt để chạy bằng IP máy. Khi bật, proxy lỗi/chặn IP sẽ tự thử proxy kế tiếp."
              />
              <CheckField
                label="Tự bấm gửi (chốt đơn thật)"
                checked={submitEnabled}
                onChange={(event) => setSubmitEnabled(event.target.checked)}
                hint="BẬT = app bấm 入力内容を確認する → 注文する: đơn 抽選 được gửi thật, không huỷ được. TẮT = dừng ở trang ご注文情報入力 để bạn tự kiểm tra."
              />
              <Text sx={{ display: 'block', fontSize: 1, color: 'muted', mb: 2 }}>
                Tài khoản ({runEmails.length ? `${runEmails.length} chọn` : 'mặc định: tất cả chưa lỗi'})
              </Text>
              <Box sx={{ maxHeight: 220, overflowY: 'auto', border: '1px solid', borderColor: 'border', borderRadius: 'small', p: 2 }}>
                {accountItems.map((account) => (
                  <label
                    key={account.email}
                    style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '3px 0', fontSize: 12 }}
                  >
                    <input
                      type="checkbox"
                      checked={runEmails.includes(account.email)}
                      onChange={() => toggleRun(account.email)}
                    />
                    <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {account.email}
                    </span>
                  </label>
                ))}
              </Box>
              <Button sx={{ mt: 3, width: '100%' }} onClick={startRun} disabled={running || !current}>
                {running ? 'Đang chạy…' : 'Chạy bằng Chrome'}
              </Button>
            </Box>
          </Panel>

          <Panel
            sx={{ mt: 3 }}
            title="Đã đăng ký"
            subtitle={current ? `${signups.length} tài khoản` : 'Chọn chiến dịch'}
            actions={
              sessions.data?.items?.length ? (
                <Button variant="secondary" onClick={closeSessions} sx={{ fontSize: 1, px: 2, py: 1 }}>
                  Đóng {sessions.data.items.length} cửa sổ
                </Button>
              ) : null
            }
          >
            {signups.length > 0 ? (
              <Box sx={{ maxHeight: 240, overflowY: 'auto' }}>
                {signups.map((signup) => (
                  <Flex key={signup.email} sx={{ px: 3, py: 2, borderBottom: '1px solid', borderColor: 'border', gap: 2 }}>
                    <Text sx={{ flex: 1, fontSize: 1 }}>{signup.email}</Text>
                    <Text sx={{ fontSize: 0, color: 'muted' }}>{signup.at}</Text>
                  </Flex>
                ))}
              </Box>
            ) : (
              <Empty>Chưa có ai được ghi nhận.</Empty>
            )}
          </Panel>
        </Box>
      </Box>
    </Box>
  )
}


