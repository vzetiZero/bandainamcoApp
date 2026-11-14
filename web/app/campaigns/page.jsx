'use client'

import { useMemo, useState } from 'react'
import { Badge, Box, Button, Flex, Input, Select, Text } from 'theme-ui'
import { Empty, Panel, Progress, ScrollTable, StatusBadge, TextField, CheckField } from '@/components/ui'
import { del, get, post, put } from '@/lib/api'
import { useJob, usePoll } from '@/lib/hooks'

const BLANK = { name: '', url: '', opens_at: '', closes_at: '', notes: '' }
// Khớp GROUP_UNGROUPED của backend: lọc tài khoản chưa vào nhóm nào.
const NO_GROUP = '__none__'
// Mã 種類 của Parks2 dạng `<mã_hàng>_<MMDD>_<HHMM>_1`; giờ nhận chỉ có các khung cố
// định, nên chọn giờ trong danh sách còn mã khác thì dán tay ở ô "Mã slot khác".
const SLOT_ITEM = '159016'
const SLOT_TIMES = ['11:00', '11:30', '12:00', '13:30', '16:00', '18:30']
const SLOT_RECIPE_DEFAULT = '159016_1121_1100_1'

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
  const [groupFilter, setGroupFilter] = useState('')
  // Ngày nhận hàng (slot) chọn bằng ô ngày + khung giờ; chế độ "ngẫu nhiên" thì mỗi
  // tài khoản nhận một khung giờ khác nhau (chia đều) thay vì cả loạt cùng một giờ.
  const [slotMode, setSlotMode] = useState('fixed')
  const [slotDate, setSlotDate] = useState('')
  const [slotTime, setSlotTime] = useState('11:00')
  const [slotTimes, setSlotTimes] = useState(SLOT_TIMES)
  const [slotCode, setSlotCode] = useState('')
  // Mặc định BẬT: chạy là chốt đơn thật. Tắt khi chỉ muốn điền form rồi tự kiểm tra.
  const [submitEnabled, setSubmitEnabled] = useState(true)
  const [useAccountAddress, setUseAccountAddress] = useState(true)
  const [clearCart, setClearCart] = useState(false)
  const [useProxy, setUseProxy] = useState(true)

  const { job, track } = useJob(() => {
    campaigns.reload()
    sessions.reload()
  })

  const items = campaigns.data?.items || []
  const accountItems = accounts.data?.items || []
  const groupNames = useMemo(
    () => Array.from(new Set(accountItems.map((account) => account.group).filter(Boolean))).sort(),
    [accountItems],
  )
  const visibleAccounts = useMemo(() => {
    if (!groupFilter) return accountItems
    if (groupFilter === NO_GROUP) return accountItems.filter((account) => !account.group)
    return accountItems.filter((account) => account.group === groupFilter)
  }, [accountItems, groupFilter])
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
    if (slotMode === 'random' && (!slotDate || slotTimes.length === 0)) {
      setMessage('Chế độ ngẫu nhiên cần ngày nhận và ít nhất một khung giờ')
      return
    }
    const targets = runEmails.length
      ? runEmails
      : visibleAccounts
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
        slot: slotMode === 'fixed' ? slotValue : '',
        slot_random: slotMode === 'random',
        slot_item: SLOT_ITEM,
        slot_date: slotDate,
        slot_times: slotMode === 'random' ? slotTimes : [],
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

  // Mã slot thực gửi lên: mã dán tay > mã ghép từ ngày/giờ > rỗng (theo recipe).
  const slotValue = useMemo(() => {
    const custom = slotCode.trim()
    if (custom) return custom
    if (!slotDate) return ''
    const [, month, day] = slotDate.split('-')
    if (!month || !day) return ''
    return `${SLOT_ITEM}_${month}${day}_${slotTime.replace(':', '')}_1`
  }, [slotCode, slotDate, slotTime])

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
                  {item.slot && (
                    <Text sx={{ color: 'muted', fontSize: 0 }}>
                      {item.slot.split('_').slice(1, 3).join(' ')}
                    </Text>
                  )}
                    <Text sx={{ color: 'muted', flex: 1 }}>{item.message}</Text>
                    {item.proxy && <Text sx={{ color: 'muted', fontSize: 0 }}>{item.proxy}</Text>}
                  </Flex>
                ))}
              </Box>
            </Box>
          )}
        </Panel>
      )}

      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: [null, null, 'minmax(0, 2.1fr) minmax(0, 1fr)'],
          gap: 3,
          alignItems: 'start',
        }}
      >
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
              <Text sx={{ display: 'block', fontSize: 1, color: 'muted', mb: 1 }}>
                Ngày nhận hàng
              </Text>
              <Select
                value={slotMode}
                onChange={(event) => setSlotMode(event.target.value)}
                sx={{ mb: 2 }}
              >
                <option value="fixed">Giờ cố định — mọi tài khoản cùng giờ</option>
                <option value="random">Giờ ngẫu nhiên — mỗi tài khoản một giờ</option>
              </Select>
              <Flex sx={{ gap: 2, mb: 1 }}>
                <Input
                  type="date"
                  value={slotDate}
                  onChange={(event) => setSlotDate(event.target.value)}
                  sx={{ flex: 1 }}
                />
                {slotMode === 'fixed' && (
                  <Select
                    value={slotTime}
                    onChange={(event) => setSlotTime(event.target.value)}
                    disabled={!slotDate}
                    sx={{ maxWidth: 108 }}
                    title="Khung giờ nhận tại cửa hàng"
                  >
                    {SLOT_TIMES.map((time) => (
                      <option key={time} value={time}>{time}</option>
                    ))}
                  </Select>
                )}
              </Flex>
              {slotMode === 'random' && (
                <Box sx={{ border: '1px solid', borderColor: 'border', borderRadius: 'small', p: 2, mb: 1 }}>
                  <Flex sx={{ alignItems: 'center', gap: 2, mb: 1 }}>
                    <Text sx={{ flex: 1, fontSize: 1, color: 'muted' }}>
                      Khung giờ được phép ({slotTimes.length})
                    </Text>
                    <Button
                      variant="ghost"
                      sx={{ fontSize: 1, px: 1, py: 0 }}
                      onClick={() => setSlotTimes(slotTimes.length === SLOT_TIMES.length ? [] : SLOT_TIMES)}
                    >
                      {slotTimes.length === SLOT_TIMES.length ? 'Bỏ chọn' : 'Chọn tất cả'}
                    </Button>
                  </Flex>
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 3 }}>
                    {SLOT_TIMES.map((time) => (
                      <label
                        key={time}
                        style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 12 }}
                      >
                        <input
                          type="checkbox"
                          checked={slotTimes.includes(time)}
                          onChange={() => setSlotTimes((current) =>
                            current.includes(time)
                              ? current.filter((item) => item !== time)
                              : [...current, time])}
                        />
                        {time}
                      </label>
                    ))}
                  </Box>
                </Box>
              )}
              <Text sx={{ display: 'block', fontSize: 0, color: 'muted', mb: 2 }}>
                {slotMode === 'random'
                  ? `Mỗi tài khoản nhận 1 trong ${slotTimes.length} khung giờ, chia đều ngẫu nhiên`
                  : `Mã slot: ${slotValue || `mặc định trong recipe (${SLOT_RECIPE_DEFAULT})`}`}
              </Text>
              {slotMode === 'fixed' && (
                <TextField
                  label="Mã slot khác"
                  value={slotCode}
                  onChange={(event) => setSlotCode(event.target.value)}
                  placeholder="Để trống = dùng mã ghép từ ngày/giờ ở trên"
                  hint="Chỉ điền khi site đổi mã; xoá trắng để quay lại mã tự ghép."
                />
              )}
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
                hint="Mặc định BẬT: app bấm 入力内容を確認する → 注文する, đơn 抽選 được gửi thật và không huỷ được. TẮT nếu chỉ muốn dừng ở trang ご注文情報入力 để tự kiểm tra."
              />
              <Flex sx={{ gap: 2, alignItems: 'center', mb: 2 }}>
                <Text sx={{ flex: 1, fontSize: 1, color: 'muted' }}>
                  Tài khoản ({runEmails.length
                    ? `${runEmails.length} chọn`
                    : 'mặc định: cả danh sách đang xem'})
                </Text>
                <Select
                  value={groupFilter}
                  onChange={(event) => { setGroupFilter(event.target.value); setRunEmails([]) }}
                  sx={{ maxWidth: 150, fontSize: 1, py: 1 }}
                  title="Chỉ hiện tài khoản của một nhóm"
                >
                  <option value="">Tất cả nhóm</option>
                  <option value={NO_GROUP}>Chưa vào nhóm</option>
                  {groupNames.map((name) => (
                    <option key={name} value={name}>{name}</option>
                  ))}
                </Select>
                <Button
                  variant="ghost"
                  sx={{ fontSize: 1 }}
                  onClick={() => setRunEmails(visibleAccounts.map((account) => account.email))}
                >
                  Chọn cả nhóm
                </Button>
              </Flex>
              <Box sx={{ maxHeight: 220, overflowY: 'auto', border: '1px solid', borderColor: 'border', borderRadius: 'small', p: 2 }}>
                {visibleAccounts.map((account) => (
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
                    {account.group && (
                      <span style={{ fontSize: 10, color: '#8a94a6' }}>{account.group}</span>
                    )}
                  </label>
                ))}
                {visibleAccounts.length === 0 && (
                  <Text sx={{ fontSize: 1, color: 'muted' }}>Nhóm này chưa có tài khoản.</Text>
                )}
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


