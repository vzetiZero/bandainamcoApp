'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { Badge, Box, Button, Flex, Input, Select, Text } from 'theme-ui'
import { Empty, Panel, Progress, ScrollTable, StatusBadge, TextField, CheckField } from '@/components/ui'
import { del, get, post, put } from '@/lib/api'
import { useJob, usePoll } from '@/lib/hooks'

const BLANK = { name: '', url: '', opens_at: '', closes_at: '', notes: '' }
// Khớp GROUP_UNGROUPED của backend: lọc tài khoản chưa vào nhóm nào.
const NO_GROUP = '__none__'
// Mã 種類 của Parks2 dạng `<mã_hàng>_<MMDD>_<HHMM>_1`. Danh sách ngày/giờ thật được đọc
// từ trang chiến dịch (`/api/campaigns/slot-options`); các khung dưới chỉ để ghép mã ở
// chế độ "giờ cố định".
const SLOT_ITEM = '159016'
const SLOT_TIMES = ['11:00', '13:30', '16:00', '18:30']
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
  // Mặc định NGẪU NHIÊN: mỗi tài khoản một ngày/giờ, tránh cả loạt cùng một giờ.
  const [slotMode, setSlotMode] = useState('random')
  const [slotDate, setSlotDate] = useState('')
  const [slotTime, setSlotTime] = useState('11:00')
  const [slotCode, setSlotCode] = useState('')
  // Mã 種類 đọc từ trang chiến dịch (nguồn đúng nhất) + các mã người dùng tick.
  const [siteOptions, setSiteOptions] = useState([])
  const [pickedCodes, setPickedCodes] = useState([])
  const [slotOptionsError, setSlotOptionsError] = useState('')
  const [loadingOptions, setLoadingOptions] = useState(false)
  // Mã 種類 dán tay (mỗi dòng một mã) khi không đọc được trang.
  const [slotCodesText, setSlotCodesText] = useState('')
  // Mặc định BẬT: chạy là chốt đơn thật. Tắt khi chỉ muốn điền form rồi tự kiểm tra.
  const [submitEnabled, setSubmitEnabled] = useState(true)
  const [useAccountAddress, setUseAccountAddress] = useState(true)
  const [clearCart, setClearCart] = useState(false)
  const [useProxy, setUseProxy] = useState(true)

  const { job, track } = useJob(() => {
    campaigns.reload()
    sessions.reload()
    accounts.reload()
    // Chạy xong: nạp lại danh sách đã đăng ký để ẩn các tài khoản vừa chốt đơn.
    if (selectedRow !== null) {
      get(`/api/campaigns/${selectedRow}/signups`)
        .then((result) => setSignups(result.signups || []))
        .catch(() => {})
    }
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
  // Tài khoản đã đăng ký chiến dịch đang chọn -> ẩn khỏi danh sách chạy, hiện ở tab
  // "Đã đăng ký" để còn kiểm soát ai chưa chạy.
  const signupEmails = useMemo(
    () => new Set(signups.map((signup) => signup.email)),
    [signups],
  )
  const openAccounts = useMemo(
    () => visibleAccounts.filter((account) => !signupEmails.has(account.email)),
    [visibleAccounts, signupEmails],
  )
  const doneCount = visibleAccounts.length - openAccounts.length
  const current = selectedRow !== null ? items[selectedRow] : null
  const running = job?.status === 'running'

  const loadSignups = async (row) => {
    setSelectedRow(row)
    const result = await get(`/api/campaigns/${row}/signups`).catch(() => ({ signups: [] }))
    setSignups(result.signups || [])
  }

  // Bỏ ghi nhận của một tài khoản: nó quay lại danh sách "chưa chạy" để chạy lại.
  const removeSignup = async (email) => {
    try {
      await del(`/api/campaigns/${selectedRow}/signups/${encodeURIComponent(email)}`)
      await loadSignups(selectedRow)
      setMessage(`Đã bỏ ghi nhận ${email}`)
    } catch (err) {
      setMessage(err.message)
    }
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

  // Danh sách tài khoản sẽ chạy: tick tay thì đúng các tài khoản đó, không tick thì
  // cả danh sách đang xem (đã bỏ tài khoản đăng ký rồi và tài khoản đang lỗi).
  const runTargets = useMemo(() => {
    if (runEmails.length) return runEmails
    return openAccounts
      .filter((account) => account.status !== 'Không hoạt động')
      .map((account) => account.email)
  }, [runEmails, openAccounts])

  // Mã hàng của chiến dịch 熊本店 (159016) — danh sách thật của trang lấy ở "Tải lại".
  const slotItem = SLOT_ITEM

  // Đọc danh sách 種類 thật của trang (ngày/giờ + mã) mỗi khi đổi chiến dịch.
  const loadSlotOptions = useCallback(async () => {
    if (!current?.url) {
      setSiteOptions([])
      setPickedCodes([])
      return
    }
    setLoadingOptions(true)
    setSlotOptionsError('')
    try {
      const data = await get(`/api/campaigns/slot-options?url=${encodeURIComponent(current.url)}`)
      const items = data.items || []
      setSiteOptions(items)
      setPickedCodes(items.map((item) => item.value))   // mặc định chọn hết
      if (!items.length) setSlotOptionsError('Trang không có mã 種類 nào')
    } catch (err) {
      setSiteOptions([])
      setPickedCodes([])
      setSlotOptionsError(err.message)
    } finally {
      setLoadingOptions(false)
    }
  }, [current])

  useEffect(() => { loadSlotOptions() }, [loadSlotOptions])

  const pastedCodes = useMemo(
    () => slotCodesText.split(/[\s,]+/).map((code) => code.trim()).filter(Boolean),
    [slotCodesText],
  )
  // Mã dùng để chia ngẫu nhiên: mã tick từ trang, không có thì dùng mã dán tay.
  const activeCodes = pickedCodes.length ? pickedCodes : pastedCodes
  // Mã slot thực gửi lên ở chế độ cố định: mã dán tay > ghép từ ngày/giờ > rỗng (recipe).
  const slotValue = useMemo(() => {
    const custom = slotCode.trim()
    if (custom) return custom
    if (!slotDate) return ''
    const [, month, day] = slotDate.split('-')
    if (!month || !day) return ''
    return `${slotItem}_${month}${day}_${slotTime.replace(':', '')}_1`
  }, [slotCode, slotDate, slotTime, slotItem])
  // Ngày/giờ mà trang thật sự có (11/21, 11/22, ...) — dùng để cảnh báo khi chọn ngày lạ.
  const availableDates = useMemo(
    () => Array.from(new Set(siteOptions.map((option) => option.when.split(' ')[0]))),
    [siteOptions],
  )
  // Chế độ cố định: mã ghép từ ô ngày/giờ phải có trong trang, không thì chặn chạy.
  const slotValueAvailable = !slotValue || !siteOptions.length
    || siteOptions.some((option) => option.value === slotValue)
  const fixedUnavailable = slotMode === 'fixed' && !slotValueAvailable
  // Mã dán tay mà trang không có (chỉ cảnh báo, vẫn cho chạy nếu người dùng biết rõ).
  const unknownPasted = useMemo(
    () => (siteOptions.length && !pickedCodes.length
      ? pastedCodes.filter((code) => !siteOptions.some((option) => option.value === code))
      : []),
    [pastedCodes, pickedCodes.length, siteOptions],
  )
  const needsCodes = slotMode === 'random' && activeCodes.length === 0
  const canRun = Boolean(current) && runTargets.length > 0 && !needsCodes
    && !fixedUnavailable

  const startRun = async () => {
    if (!current) {
      setMessage('Bấm một dòng trong "Danh sách chiến dịch" để chọn chiến dịch trước')
      return
    }
    if (fixedUnavailable) {
      setMessage(`Trang không có ngày/giờ đó — chỉ có ${availableDates.join(', ') || 'danh sách chưa đọc được'}`)
      return
    }
    if (needsCodes) {
      setMessage('Chế độ ngẫu nhiên: bấm "Tải lại" để lấy mã ngày/giờ từ trang rồi tick ít nhất một mã')
      return
    }
    const targets = runTargets
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
        slot_item: slotItem,
        slot_date: slotDate,
        slot_times: slotMode === 'random' ? [] : [],
        slot_codes: slotMode === 'random' ? activeCodes : [],
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
          <Button
            onClick={startRun}
            disabled={running || !canRun}
            title={canRun ? 'Mở Chrome cho từng tài khoản đã chọn' : 'Chọn chiến dịch, tài khoản và ngày nhận trước'}
          >
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
          <Panel title="Chạy tự động" subtitle={current ? current.name : 'Bấm một dòng trong "Danh sách chiến dịch" để chọn'}>
            <Box sx={{ p: 3 }}>
              <Text sx={{ display: 'block', fontSize: 1, color: 'muted', mb: 1 }}>
                Kiểu chọn ngày/giờ nhận
              </Text>
              <Select
                value={slotMode}
                onChange={(event) => setSlotMode(event.target.value)}
                sx={{ mb: 2 }}
              >
                <option value="fixed">Giờ cố định — mọi tài khoản cùng giờ</option>
                <option value="random">Giờ ngẫu nhiên — mỗi tài khoản một giờ</option>
              </Select>
              {slotMode === 'fixed' && (
                <>
                  <Text sx={{ display: 'block', fontSize: 1, color: 'muted', mb: 1 }}>
                    Ngày nhận hàng
                  </Text>
                  <Flex sx={{ gap: 2, mb: 1 }}>
                    <Input
                      type="date"
                      value={slotDate}
                      onChange={(event) => setSlotDate(event.target.value)}
                      sx={{ flex: 1 }}
                    />
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
                  </Flex>
                  {availableDates.length > 0 && (
                    <Text sx={{ display: 'block', fontSize: 0, color: 'muted', mb: 1 }}>
                      Ngày có trên trang: {availableDates.join(', ')}
                    </Text>
                  )}
                  {!slotValueAvailable && (
                    <Text sx={{ display: 'block', fontSize: 1, color: 'error', mb: 1 }}>
                      Trang không có ngày/giờ này — chọn một trong các ngày ở trên,
                      hoặc đổi sang chế độ ngẫu nhiên để dùng danh sách của trang.
                    </Text>
                  )}
                </>
              )}
              {slotMode === 'random' && (
                <Box sx={{ border: '1px solid', borderColor: 'border', borderRadius: 'small', p: 2, mb: 1 }}>
                  <Flex sx={{ alignItems: 'center', gap: 2, mb: 1 }}>
                    <Text sx={{ flex: 1, fontSize: 1, color: 'muted' }}>
                      Ngày/giờ lấy từ trang ({pickedCodes.length}/{siteOptions.length})
                    </Text>
                    <Button
                      variant="ghost"
                      sx={{ fontSize: 1, px: 1, py: 0 }}
                      disabled={!siteOptions.length}
                      onClick={() => setPickedCodes(
                        pickedCodes.length === siteOptions.length
                          ? []
                          : siteOptions.map((item) => item.value))}
                    >
                      {pickedCodes.length === siteOptions.length && siteOptions.length
                        ? 'Bỏ chọn'
                        : 'Chọn tất cả'}
                    </Button>
                    <Button
                      variant="ghost"
                      sx={{ fontSize: 1, px: 1, py: 0 }}
                      disabled={!current || loadingOptions}
                      onClick={loadSlotOptions}
                    >
                      {loadingOptions ? 'Đang tải…' : 'Tải lại'}
                    </Button>
                  </Flex>
                  {slotOptionsError && (
                    <Text sx={{ display: 'block', fontSize: 0, color: 'error', mb: 1 }}>
                      {slotOptionsError}
                    </Text>
                  )}
                  <Box
                    sx={{
                      display: 'flex', flexWrap: 'wrap', gap: 2,
                      maxHeight: 160, overflowY: 'auto',
                    }}
                  >
                    {siteOptions.map((option) => (
                      <label
                        key={option.value}
                        title={option.label}
                        style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 12 }}
                      >
                        <input
                          type="checkbox"
                          checked={pickedCodes.includes(option.value)}
                          onChange={() => setPickedCodes((current) =>
                            current.includes(option.value)
                              ? current.filter((item) => item !== option.value)
                              : [...current, option.value])}
                        />
                        {option.when}
                      </label>
                    ))}
                    {!siteOptions.length && !loadingOptions && (
                      <Text sx={{ fontSize: 0, color: 'muted' }}>
                        Chưa có mã của trang — bấm &quot;Tải lại&quot;, hoặc dán mã tay bên dưới.
                      </Text>
                    )}
                  </Box>
                  <Text sx={{ display: 'block', fontSize: 0, color: 'muted', mt: 2, mb: 1 }}>
                    Hoặc dán mã 種類 (mỗi dòng một mã) — chỉ dùng khi không đọc được trang.
                  </Text>
                  <Box
                    as="textarea"
                    rows={3}
                    value={slotCodesText}
                    onChange={(event) => setSlotCodesText(event.target.value)}
                    placeholder={'159016_1121_1100_1\n159016_1121_1330_1'}
                    sx={{
                      width: '100%', fontFamily: 'mono', fontSize: 1, p: 2,
                      border: '1px solid', borderColor: 'border', borderRadius: 'small',
                      bg: 'surface', color: 'text',
                    }}
                  />
                  {unknownPasted.length > 0 && (
                    <Text sx={{ display: 'block', fontSize: 0, color: 'error', mt: 1 }}>
                      {unknownPasted.length} mã dán vào không có trên trang ({unknownPasted[0]}…)
                    </Text>
                  )}
                </Box>
              )}
              <Text sx={{ display: 'block', fontSize: 0, color: 'muted', mb: 2 }}>
                Mã hàng: {slotItem}
                {slotMode === 'random'
                  ? ` · chia ngẫu nhiên ${activeCodes.length} mã ngày/giờ`
                  : ` · mã slot: ${slotValue || `mặc định trong recipe (${SLOT_RECIPE_DEFAULT})`}`}
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
              <Flex sx={{ gap: 2, alignItems: 'center', mb: 1 }}>
                <Text sx={{ flex: 1, fontSize: 1, color: 'muted' }}>
                  Tài khoản chưa chạy ({runEmails.length
                    ? `${runEmails.length} chọn`
                    : `${openAccounts.length} sẵn sàng`})
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
                  onClick={() => setRunEmails(openAccounts.map((account) => account.email))}
                >
                  Chọn cả nhóm
                </Button>
              </Flex>
              {doneCount > 0 && (
                <Text sx={{ display: 'block', fontSize: 0, color: 'muted', mb: 2 }}>
                  Đã ẩn {doneCount} tài khoản đã đăng ký — xem ở tab &quot;Đã đăng ký&quot;.
                </Text>
              )}
              <Box sx={{ maxHeight: 220, overflowY: 'auto', border: '1px solid', borderColor: 'border', borderRadius: 'small', p: 2 }}>
                {openAccounts.map((account) => (
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
                {openAccounts.length === 0 && (
                  <Text sx={{ fontSize: 1, color: 'muted' }}>
                    {doneCount > 0
                      ? 'Mọi tài khoản trong nhóm này đã đăng ký chiến dịch rồi.'
                      : 'Nhóm này chưa có tài khoản.'}
                  </Text>
                )}
              </Box>
              {needsCodes && (
                <Text sx={{ display: 'block', fontSize: 1, color: 'error', mb: 1 }}>
                  Tick ít nhất một ngày/giờ ở danh sách trên (bấm &quot;Tải lại&quot; nếu trống).
                </Text>
              )}
              <Box sx={{ mt: 3, pt: 3, borderTop: '1px solid', borderColor: 'border' }}>
                <Text sx={{ display: 'block', fontSize: 1, color: 'muted', mb: 2 }}>
                  Sẽ chạy {runTargets.length} tài khoản cho{' '}
                  <strong>{current ? current.name : '— chưa chọn chiến dịch —'}</strong>
                  {slotMode === 'random'
                    ? ` · ${activeCodes.length} ngày/giờ chia ngẫu nhiên`
                    : ` · ${slotValue ? `giờ ${slotValue.split('_').slice(1, 3).join(' ')}` : 'giờ theo recipe'}`}
                  {submitEnabled ? ' · chốt đơn thật' : ' · chỉ điền, không gửi'}
                </Text>
                <Button sx={{ width: '100%' }} onClick={startRun} disabled={running || !canRun}>
                  {running ? 'Đang chạy…' : `Chạy bằng Chrome (${runTargets.length})`}
                </Button>
              </Box>
            </Box>
          </Panel>

          <Panel
            sx={{ mt: 3 }}
            title="Đã đăng ký"
            subtitle={current ? `${signups.length} tài khoản đã đăng ký` : 'Chọn chiến dịch'}
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
                {[...signups]
                  .sort((a, b) => String(b.at || '').localeCompare(String(a.at || '')))
                  .map((signup) => (
                    <Flex
                      key={signup.email}
                      sx={{ px: 3, py: 2, borderBottom: '1px solid', borderColor: 'border', gap: 2, alignItems: 'center' }}
                    >
                      <Text sx={{ flex: 1, fontSize: 1 }}>{signup.email}</Text>
                      <Text sx={{ fontSize: 0, color: 'muted' }}>{signup.at}</Text>
                      <Button
                        variant="ghost"
                        sx={{ fontSize: 0, px: 1, py: 0 }}
                        title="Bỏ ghi nhận: tài khoản quay lại danh sách chưa chạy"
                        onClick={() => removeSignup(signup.email)}
                      >
                        Bỏ
                      </Button>
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


