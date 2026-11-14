'use client'

import { useCallback, useMemo, useState } from 'react'
import { Badge, Box, Button, Flex, Input, Select, Text } from 'theme-ui'
import { Empty, Panel, Progress, ScrollTable, StatusBadge, Toolbar, TextField } from '@/components/ui'
import { del, post } from '@/lib/api'
import { useJob, usePoll } from '@/lib/hooks'

const STATUS_OPTIONS = [
  { value: '', label: 'Tất cả trạng thái' },
  { value: 'Hoạt động', label: 'Hoạt động' },
  { value: 'Không hoạt động', label: 'Không hoạt động' },
  { value: 'Chưa kiểm tra', label: 'Chưa kiểm tra' },
]

// Giá trị lọc "chưa vào nhóm" phải khớp GROUP_UNGROUPED của backend.
const NO_GROUP = '__none__'
const NEW_GROUP = '__new__'

export default function AccountsPage() {
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('')
  const [groupFilter, setGroupFilter] = useState('')
  const [selected, setSelected] = useState([])
  const [importText, setImportText] = useState('')
  const [message, setMessage] = useState('')
  const [nameFor, setNameFor] = useState(null)
  const [lastName, setLastName] = useState('')
  const [firstName, setFirstName] = useState('')
  const [targetGroup, setTargetGroup] = useState('')
  const [freshGroup, setFreshGroup] = useState('')
  const [groupDraft, setGroupDraft] = useState('')
  const [importGroup, setImportGroup] = useState('')
  const [importFreshGroup, setImportFreshGroup] = useState('')

  const list = usePoll(
    `/api/accounts?query=${encodeURIComponent(query)}&status=${encodeURIComponent(status)}`
    + `&group=${encodeURIComponent(groupFilter)}`,
    8000,
    [query, status, groupFilter],
  )
  const { job, track } = useJob(() => list.reload())

  const items = list.data?.items || []
  const counts = list.data?.counts || {}
  const groups = list.data?.groups?.groups || []
  const ungrouped = list.data?.groups?.ungrouped || 0
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
    // Nhóm chọn sẵn cho các tài khoản vừa dán: gán ngay khi thêm, khỏi phải tick lại.
    const group = importGroup === NEW_GROUP ? importFreshGroup.trim() : importGroup
    if (importGroup === NEW_GROUP && !group) {
      setMessage('Đặt tên cho nhóm mới trước khi thêm')
      return
    }
    try {
      const result = await post('/api/accounts/import', { text: importText, group })
      setMessage(result.group
        ? `Đã thêm ${result.added} tài khoản vào nhóm “${result.group}” (bỏ qua ${result.skipped})`
        : `Đã thêm ${result.added}, bỏ qua ${result.skipped}`)
      setImportText('')
      setImportFreshGroup('')
      if (group) setGroupFilter(group)   // hiện ngay nhóm vừa thêm
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

  // ---------------- nhóm ----------------
  const createGroup = async (name) => {
    const clean = (name || '').trim()
    if (!clean) return
    try {
      await post('/api/accounts/groups', { name: clean })
      setMessage(`Đã tạo nhóm “${clean}”`)
      setGroupDraft('')
      list.reload()
    } catch (err) {
      setMessage(err.message)
    }
  }

  const deleteGroup = async (name) => {
    if (!window.confirm(`Xoá nhóm “${name}”? Tài khoản trong nhóm vẫn giữ, chỉ bỏ nhóm.`)) return
    try {
      const result = await del(`/api/accounts/groups/${encodeURIComponent(name)}`)
      setMessage(`Đã xoá nhóm “${name}” (${result.cleared} tài khoản bỏ nhóm)`)
      if (groupFilter === name) setGroupFilter('')
      if (targetGroup === name) setTargetGroup('')
      list.reload()
    } catch (err) {
      setMessage(err.message)
    }
  }

  const assignGroup = async (group) => {
    if (!selected.length) {
      setMessage('Chọn tài khoản trước khi đưa vào nhóm')
      return
    }
    const name = (group || '').trim()
    if (targetGroup === NEW_GROUP && !name) {
      setMessage('Đặt tên cho nhóm mới')
      return
    }
    try {
      const result = await post('/api/accounts/group', { emails: selected, group: name })
      setMessage(name
        ? `Đã chuyển ${result.changed} tài khoản vào nhóm “${name}”`
        : `Đã bỏ ${result.changed} tài khoản khỏi nhóm`)
      setSelected([])
      setFreshGroup('')
      list.reload()
    } catch (err) {
      setMessage(err.message)
    }
  }

  const jobDone = useMemo(() => {
    if (!job || job.status === 'running') return null
    return `${job.message || job.status}`
  }, [job])

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }}>
      <Flex sx={{ alignItems: 'flex-end', mb: 4, gap: 3, flexWrap: 'wrap' }}>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Text as="h1" sx={{ fontSize: 6, fontWeight: 'bold' }}>Tài khoản</Text>
          <Text sx={{ color: 'muted', fontSize: 2 }}>
            {counts.total || 0} tài khoản · {counts.active || 0} hoạt động · {counts.inactive || 0} lỗi
            {' · '}{groups.length} nhóm
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

      {/* Cột phải xuống dưới khi cửa sổ hẹp: bảng danh sách luôn đủ chỗ đọc. */}
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: [null, null, 'minmax(0, 1fr) 320px'],
          gap: 3,
          alignItems: 'start',
          flex: 1,
          minHeight: 0,
        }}
      >
        <Box sx={{ minWidth: 0 }}>
          <Panel title="Danh sách" subtitle={`${items.length} dòng hiển thị`}>
            <Toolbar>
              <Input
                placeholder="Tìm theo email"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                sx={{ maxWidth: 240 }}
              />
              <Select
                value={status}
                onChange={(event) => setStatus(event.target.value)}
                sx={{ maxWidth: 176 }}
              >
                {STATUS_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </Select>
              <Select
                value={groupFilter}
                onChange={(event) => setGroupFilter(event.target.value)}
                sx={{ maxWidth: 200 }}
              >
                <option value="">Tất cả nhóm</option>
                <option value={NO_GROUP}>Chưa vào nhóm ({ungrouped})</option>
                {groups.map((group) => (
                  <option key={group.name} value={group.name}>
                    {group.name} ({group.count})
                  </option>
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

            {/* Thanh nhóm: chuyển tài khoản đang chọn vào nhóm có sẵn hoặc nhóm mới. */}
            <Flex
              sx={{
                gap: 2, alignItems: 'center', flexWrap: 'wrap', px: 3, pb: 3,
                borderBottom: '1px solid', borderColor: 'border',
              }}
            >
              <Text sx={{ fontSize: 1, color: 'muted' }}>
                {selected.length ? `${selected.length} tài khoản đã chọn` : 'Chọn tài khoản để xếp nhóm'}
              </Text>
              <Select
                value={targetGroup}
                onChange={(event) => setTargetGroup(event.target.value)}
                sx={{ maxWidth: 190 }}
              >
                <option value="">— Chọn nhóm —</option>
                {groups.map((group) => (
                  <option key={group.name} value={group.name}>{group.name}</option>
                ))}
                <option value={NEW_GROUP}>+ Nhóm mới…</option>
              </Select>
              {targetGroup === NEW_GROUP && (
                <Input
                  placeholder="Tên nhóm mới"
                  value={freshGroup}
                  onChange={(event) => setFreshGroup(event.target.value)}
                  sx={{ maxWidth: 170 }}
                />
              )}
              <Button
                onClick={() => assignGroup(targetGroup === NEW_GROUP ? freshGroup : targetGroup)}
                disabled={!selected.length || !targetGroup}
              >
                Vào nhóm
              </Button>
              <Button
                variant="ghost"
                onClick={() => assignGroup('')}
                disabled={!selected.length}
                title="Bỏ nhóm của các tài khoản đang chọn"
              >
                Bỏ khỏi nhóm
              </Button>
            </Flex>

            <ScrollTable
              maxHeight="max(260px, calc(100vh - 340px))"
              sx={{ '& table': { tableLayout: 'fixed' } }}
            >
              <thead>
                <tr>
                  <th style={{ width: 34 }} />
                  <th style={{ width: '34%' }}>Email</th>
                  <th style={{ width: 120 }}>Nhóm</th>
                  <th style={{ width: 110 }}>Trạng thái</th>
                  <th style={{ width: 130 }}>Kiểm tra gần nhất</th>
                  <th style={{ width: '20%' }}>Tên (hồ sơ)</th>
                  <th style={{ width: 84 }} />
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
                    <td style={{ maxWidth: 0 }}>
                      <Text
                        title={account.email}
                        sx={{
                          display: 'block', fontSize: 2, overflow: 'hidden',
                          textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                        }}
                      >
                        {account.email}
                      </Text>
                      {account.token && <Badge variant="muted" sx={{ mt: 1 }}>token</Badge>}
                    </td>
                    <td>
                      {account.group
                        ? <Badge variant="accent">{account.group}</Badge>
                        : <Text sx={{ fontSize: 1, color: 'muted' }}>—</Text>}
                    </td>
                    <td><StatusBadge status={account.status} /></td>
                    <td><Text sx={{ fontSize: 1, color: 'muted' }}>{account.last_check || '—'}</Text></td>
                    <td style={{ maxWidth: 0 }}>
                      <Text
                        sx={{
                          fontSize: 1, color: 'muted', overflow: 'hidden',
                          textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                        }}
                      >
                        {[account.last_name_kanji, account.first_name_kanji].filter(Boolean).join(' ')
                          || account.nickname || '—'}
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
            </ScrollTable>
            {items.length === 0 && <Empty>Không có tài khoản nào khớp bộ lọc.</Empty>}
          </Panel>
        </Box>

        <Box sx={{ display: 'grid', gap: 3, minWidth: 0 }}>
          <Panel title="Nhóm" subtitle={`${groups.length} nhóm · ${ungrouped} chưa vào nhóm`}>
            <Box sx={{ p: 3 }}>
              <Flex sx={{ gap: 2, mb: 3 }}>
                <Input
                  placeholder="Tên nhóm mới"
                  value={groupDraft}
                  onChange={(event) => setGroupDraft(event.target.value)}
                  onKeyDown={(event) => { if (event.key === 'Enter') createGroup(groupDraft) }}
                />
                <Button onClick={() => createGroup(groupDraft)} disabled={!groupDraft.trim()}>
                  Tạo
                </Button>
              </Flex>
              <Box sx={{ maxHeight: 190, overflowY: 'auto' }}>
                {groups.length === 0 && (
                  <Text sx={{ fontSize: 1, color: 'muted' }}>Chưa có nhóm nào.</Text>
                )}
                {groups.map((group) => (
                  <Flex
                    key={group.name}
                    sx={{
                      alignItems: 'center', gap: 2, py: 1,
                      borderBottom: '1px solid', borderColor: 'border',
                    }}
                  >
                    <Text
                      title={group.name}
                      sx={{
                        flex: 1, minWidth: 0, fontSize: 1, cursor: 'pointer',
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      }}
                      onClick={() => setGroupFilter(group.name)}
                    >
                      {group.name}
                    </Text>
                    <Badge variant="info">{group.count}</Badge>
                    <Button
                      variant="ghost"
                      onClick={() => deleteGroup(group.name)}
                      sx={{ fontSize: 1, px: 1, py: 0 }}
                      title="Xoá nhóm (tài khoản vẫn giữ, chỉ bỏ nhóm)"
                    >
                      Xoá
                    </Button>
                  </Flex>
                ))}
              </Box>
            </Box>
          </Panel>

          <Panel title="Thêm tài khoản" subtitle="Mỗi dòng: email|password|token">
            <Box sx={{ p: 3 }}>
              <Text sx={{ display: 'block', fontSize: 1, color: 'muted', mb: 1 }}>
                Nhóm cho tài khoản sắp thêm
              </Text>
              <Select
                value={importGroup}
                onChange={(event) => setImportGroup(event.target.value)}
                sx={{ mb: 2 }}
              >
                <option value="">— Không vào nhóm —</option>
                {groups.map((group) => (
                  <option key={group.name} value={group.name}>{group.name}</option>
                ))}
                <option value={NEW_GROUP}>+ Nhóm mới…</option>
              </Select>
              {importGroup === NEW_GROUP && (
                <Input
                  placeholder="Tên nhóm mới"
                  value={importFreshGroup}
                  onChange={(event) => setImportFreshGroup(event.target.value)}
                  sx={{ mb: 2 }}
                />
              )}
              <Box
                as="textarea"
                rows={6}
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
