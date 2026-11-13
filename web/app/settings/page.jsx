'use client'

import { useEffect, useState } from 'react'
import { Badge, Box, Button, Flex, Input, Select, Text } from 'theme-ui'
import { CheckField, Empty, Field, Panel, Progress, SelectField, StatusBadge, TextField } from '@/components/ui'
import { del, get, post, put } from '@/lib/api'
import { useJob, usePoll } from '@/lib/hooks'

export default function SettingsPage() {
  const settings = usePoll('/api/settings', 15000)
  const checkout = usePoll('/api/checkout', 15000)
  const proxy = usePoll('/api/proxy', 15000)
  const { job, track } = useJob(() => proxy.reload())

  const [proxyForm, setProxyForm] = useState({ enabled: false, mode: 'per_request', file: '' })
  const [browserForm, setBrowserForm] = useState({ recipe_path: '', headless: false, parallel: 1, submit: true })
  const [general, setGeneral] = useState(1)
  const [recipeText, setRecipeText] = useState('')
  const [recipeInfo, setRecipeInfo] = useState(null)
  const [message, setMessage] = useState('')
  const [profile, setProfile] = useState({})
  const [card, setCard] = useState({ card_holder: '', card_number: '', card_exp: '', card_cvv: '' })

  useEffect(() => {
    if (settings.data) {
      setProxyForm({
        enabled: settings.data.proxy.enabled,
        mode: settings.data.proxy.mode,
        file: settings.data.proxy.file,
      })
      setBrowserForm({
        recipe_path: settings.data.browser.recipe_path,
        headless: settings.data.browser.headless,
        parallel: settings.data.browser.parallel,
        submit: settings.data.browser.submit,
      })
      setGeneral(settings.data.max_workers)
    }
  }, [settings.data])

  useEffect(() => {
    if (checkout.data?.profile) {
      const filled = {}
      checkout.data.fields.forEach((field) => {
        filled[field.name] = checkout.data.profile[field.name] || ''
      })
      filled.building_none = Boolean(checkout.data.profile.building_none)
      setProfile((current) => ({ ...filled, ...current }))
    }
  }, [checkout.data])

  const loadRecipe = async () => {
    try {
      const raw = await get('/api/browser/recipe')
      setRecipeText(typeof raw === 'string' ? raw : JSON.stringify(raw, null, 2))
    } catch (err) {
      setMessage(err.message)
    }
  }

  const saveRecipe = async () => {
    try {
      await put('/api/browser/recipe', { json: recipeText })
      const info = await get('/api/settings/recipe')
      setRecipeInfo(info)
      setMessage('Đã lưu recipe')
    } catch (err) {
      setMessage(err.message)
    }
  }

  const checkRecipe = async () => {
    const info = await get('/api/settings/recipe')
    setRecipeInfo(info)
    setMessage(info.ok ? 'Recipe hợp lệ' : `${info.errors.length} lỗi trong recipe`)
  }

  const saveProxy = async () => {
    try {
      await put('/api/settings/proxy', proxyForm)
      settings.reload()
      proxy.reload()
      setMessage('Đã lưu cấu hình proxy')
    } catch (err) {
      setMessage(err.message)
    }
  }

  const checkProxies = async () => {
    const started = await post('/api/proxy/check')
    track(started)
  }

  const saveBrowser = async () => {
    try {
      await put('/api/settings/browser', browserForm)
      settings.reload()
      setMessage('Đã lưu cấu hình trình duyệt')
    } catch (err) {
      setMessage(err.message)
    }
  }

  const saveGeneral = async () => {
    const result = await put('/api/settings/general', { max_workers: Number(general) })
    setGeneral(result.max_workers)
    settings.reload()
  }

  const saveCheckout = async () => {
    try {
      const payload = { ...profile, building_none: Boolean(profile.building_none) }
      Object.entries(card).forEach(([key, value]) => {
        if (value) payload[key] = value
      })
      const result = await put('/api/checkout', payload)
      checkout.setData({ ...checkout.data, profile: result.profile })
      setCard({ card_holder: '', card_number: '', card_exp: '', card_cvv: '' })
      setMessage(result.message)
    } catch (err) {
      setMessage(err.message)
    }
  }

  const clearCheckout = async () => {
    if (!window.confirm('Xoá hồ sơ đặt hàng/thẻ đã lưu?')) return
    await del('/api/checkout').catch(() => null)
    setMessage('Đã xoá hồ sơ đặt hàng')
  }

  const customer = settings.data?.browser || {}

  return (
    <Box>
      <Flex sx={{ alignItems: 'flex-end', mb: 4, gap: 3 }}>
        <Box sx={{ flex: 1 }}>
          <Text as="h1" sx={{ fontSize: 6, fontWeight: 'bold' }}>Cấu hình</Text>
          <Text sx={{ color: 'muted', fontSize: 2 }}>
            Proxy, trình duyệt, recipe và thông tin đặt hàng — tất cả lưu ở backend Python.
          </Text>
        </Box>
        {message && <Badge variant="info">{message}</Badge>}
      </Flex>

      <Box sx={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)', gap: 3 }}>
        {/* Proxy */}
        <Panel title="Proxy" subtitle={`${proxy.data?.items?.length || 0} proxy trong file`}>
          <Box sx={{ p: 3 }}>
            <CheckField
              label="Bật proxy cho mọi request"
              checked={proxyForm.enabled}
              onChange={(event) => setProxyForm({ ...proxyForm, enabled: event.target.checked })}
            />
            <SelectField
              label="Chế độ"
              value={proxyForm.mode}
              onChange={(event) => setProxyForm({ ...proxyForm, mode: event.target.value })}
              options={[
                { value: 'per_request', label: 'Luân phiên theo request' },
                { value: 'per_session', label: 'Mỗi tài khoản 1 proxy' },
              ]}
            />
            <TextField
              label="File proxy"
              value={proxyForm.file}
              onChange={(event) => setProxyForm({ ...proxyForm, file: event.target.value })}
              hint="Định dạng: ip:port:username:password"
            />
            <Flex sx={{ gap: 2, mt: 2, flexWrap: 'wrap' }}>
              <Button onClick={saveProxy}>Lưu</Button>
              <Button variant="secondary" onClick={checkProxies} disabled={job?.status === 'running'}>
                Kiểm tra proxy
              </Button>
              <Button
                variant="ghost"
                onClick={async () => { await post('/api/proxy/reset-blocks'); proxy.reload() }}
              >
                Bỏ tạm nghỉ
              </Button>
            </Flex>
            {job && <Box sx={{ mt: 3 }}><Progress done={job.done} total={job.total} /></Box>}
            <Box sx={{ mt: 3, maxHeight: 200, overflowY: 'auto' }}>
              {(proxy.data?.items || []).map((item) => (
                <Flex key={`${item.host}:${item.port}`} sx={{ gap: 2, fontSize: 1, py: '2px' }}>
                  <Text sx={{ minWidth: 24, color: 'muted' }}>{item.index}</Text>
                  <Text sx={{ flex: 1 }}>{item.host}:{item.port}</Text>
                  <Text sx={{ color: 'muted' }}>{item.username}</Text>
                  {item.blocked_seconds > 0 && <Badge variant="warn">{item.blocked_seconds}s</Badge>}
                </Flex>
              ))}
              {!proxy.data?.items?.length && <Empty>Chưa có proxy nào.</Empty>}
            </Box>
          </Box>
        </Panel>

        {/* Trình duyệt */}
        <Panel title="Trình duyệt tự động" subtitle={customer.chrome ? `Chrome: ${customer.chrome}` : 'Chưa tìm thấy Chrome'}>
          <Box sx={{ p: 3 }}>
            <TextField
              label="File recipe"
              value={browserForm.recipe_path}
              onChange={(event) => setBrowserForm({ ...browserForm, recipe_path: event.target.value })}
            />
            <Flex sx={{ gap: 3, flexWrap: 'wrap' }}>
              <Field label="Chrome song song" sx={{ flex: 1, minWidth: 140 }}>
                <Input
                  type="number"
                  min={1}
                  max={settings.data?.browser?.max_parallel || 3}
                  value={browserForm.parallel}
                  onChange={(event) => setBrowserForm({ ...browserForm, parallel: Number(event.target.value) })}
                />
              </Field>
              <Field label="Luồng kiểm tra" sx={{ flex: 1, minWidth: 140 }}>
                <Input
                  type="number"
                  min={1}
                  max={settings.data?.max_workers_limit || 10}
                  value={general}
                  onChange={(event) => setGeneral(Number(event.target.value))}
                  onBlur={saveGeneral}
                />
              </Field>
            </Flex>
            <CheckField
              label="Chrome ẩn (headless)"
              checked={browserForm.headless}
              onChange={(event) => setBrowserForm({ ...browserForm, headless: event.target.checked })}
            />
            <CheckField
              label="Tự bấm gửi (submit)"
              checked={browserForm.submit}
              onChange={(event) => setBrowserForm({ ...browserForm, submit: event.target.checked })}
            />
            <Flex sx={{ gap: 2, mt: 2, flexWrap: 'wrap' }}>
              <Button onClick={saveBrowser}>Lưu</Button>
              <Button variant="secondary" onClick={checkRecipe}>Kiểm tra recipe</Button>
              <Button variant="ghost" onClick={loadRecipe}>Mở recipe</Button>
            </Flex>
            {recipeInfo && (
              <Box sx={{ mt: 3, fontSize: 1 }}>
                {recipeInfo.ok ? (
                  <Badge variant="ok">Recipe hợp lệ</Badge>
                ) : (
                  <Box>
                    <Badge variant="error">{recipeInfo.errors.length} lỗi</Badge>
                    {recipeInfo.errors.slice(0, 6).map((error) => (
                      <Text key={error} sx={{ display: 'block', color: 'error', mt: 1 }}>{error}</Text>
                    ))}
                  </Box>
                )}
              </Box>
            )}
          </Box>
        </Panel>
      </Box>

      {/* Recipe editor */}
      <Panel
        sx={{ mt: 3 }}
        title="Recipe (JSON)"
        subtitle="Selector nằm trong dữ liệu, không hard-code. Sửa rồi bấm Lưu — API validate trước khi ghi."
        actions={<Button variant="secondary" onClick={saveRecipe}>Lưu recipe</Button>}
      >
        <Box sx={{ p: 3 }}>
          <Box
            as="textarea"
            rows={16}
            value={recipeText}
            onChange={(event) => setRecipeText(event.target.value)}
            placeholder='Bấm "Mở recipe" để nạp nội dung file…'
            sx={{
              width: '100%', fontFamily: 'mono', fontSize: 1, p: 2,
              border: '1px solid', borderColor: 'border', borderRadius: 'small',
              bg: 'surface', color: 'text',
            }}
          />
        </Box>
      </Panel>

      {/* Thông tin đặt hàng */}
      <Panel
        sx={{ mt: 3 }}
        title="Thông tin đặt hàng & thanh toán"
        subtitle={checkout.data?.profile?.summary || 'Chưa nhập'}
        actions={
          <Flex sx={{ gap: 2 }}>
            <Button variant="danger" onClick={clearCheckout}>Xoá</Button>
            <Button onClick={saveCheckout}>Lưu</Button>
          </Flex>
        }
      >
        <Box sx={{ p: 3, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 3 }}>
          {(checkout.data?.fields || []).map((field) =>
            field.name === 'pref' ? (
              <Field key={field.name} label={field.label}>
                <Select
                  value={profile.pref || ''}
                  onChange={(event) => setProfile({ ...profile, pref: event.target.value })}
                >
                  <option value="">—</option>
                  {(checkout.data?.prefectures || []).map((prefecture) => (
                    <option key={prefecture} value={prefecture}>{prefecture}</option>
                  ))}
                </Select>
              </Field>
            ) : (
              <TextField
                key={field.name}
                label={field.label}
                value={profile[field.name] || ''}
                onChange={(event) => setProfile({ ...profile, [field.name]: event.target.value })}
              />
            ),
          )}
        </Box>
        <Box sx={{ px: 3, pb: 2 }}>
          <CheckField
            label="ビル・マンション名・部屋番号なし (không có toà nhà/phòng)"
            checked={Boolean(profile.building_none)}
            onChange={(event) => setProfile({ ...profile, building_none: event.target.checked })}
          />
        </Box>
        <Box sx={{ px: 3, pb: 4 }}>
          <Text sx={{ display: 'block', fontSize: 1, color: 'muted', mb: 2 }}>
            Thẻ thanh toán — để trống nghĩa là giữ giá trị đã lưu (API không trả lại số thẻ/CVV).
          </Text>
          <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 3 }}>
            {(checkout.data?.card_fields || []).map((field) => (
              <TextField
                key={field.name}
                label={field.label}
                type={field.name === 'card_cvv' ? 'password' : 'text'}
                value={card[field.name] || ''}
                placeholder={checkout.data?.profile?.has_card && field.name === 'card_number'
                  ? checkout.data.profile.card_number
                  : ''}
                onChange={(event) => setCard({ ...card, [field.name]: event.target.value })}
              />
            ))}
          </Box>
          <Text sx={{ display: 'block', fontSize: 0, color: 'muted', mt: 2 }}>
            {checkout.data?.profile?.encrypted ? 'Lưu mã hoá DPAPI' : 'Chưa mã hoá'}
            {checkout.data?.profile?.gaps?.length
              ? ` · còn thiếu: ${checkout.data.profile.gaps.join(', ')}`
              : ''}
          </Text>
        </Box>
      </Panel>
    </Box>
  )
}
