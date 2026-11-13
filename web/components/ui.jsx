'use client'

import { Badge, Box, Button, Flex, Input, Label, Select, Text } from 'theme-ui'

// Panel: khung nội dung chính, tiêu đề + phụ đề + hành động bên phải.
export function Panel({ title, subtitle, actions, children, sx }) {
  return (
    <Box variant="cards.panel" sx={{ p: 0, overflow: 'hidden', ...sx }}>
      {(title || actions) && (
        <Flex
          sx={{
            px: 4, py: 3, alignItems: 'center', gap: 3,
            borderBottom: '1px solid', borderColor: 'border', bg: 'surface',
          }}
        >
          <Box sx={{ flex: 1, minWidth: 0 }}>
            {title && <Text sx={{ fontSize: 3, fontWeight: 'medium' }}>{title}</Text>}
            {subtitle && (
              <Text sx={{ display: 'block', fontSize: 1, color: 'muted', mt: 1 }}>
                {subtitle}
              </Text>
            )}
          </Box>
          {actions && <Flex sx={{ gap: 2, flexShrink: 0 }}>{actions}</Flex>}
        </Flex>
      )}
      {children}
    </Box>
  )
}

export function Field({ label, hint, children, sx }) {
  return (
    <Box sx={{ mb: 3, ...sx }}>
      {label && <Label>{label}</Label>}
      {children}
      {hint && (
        <Text sx={{ display: 'block', fontSize: 0, color: 'muted', mt: 1 }}>{hint}</Text>
      )}
    </Box>
  )
}

export function TextField({ label, hint, sx, ...props }) {
  return (
    <Field label={label} hint={hint} sx={sx}>
      <Input {...props} />
    </Field>
  )
}

export function SelectField({ label, hint, options, sx, ...props }) {
  return (
    <Field label={label} hint={hint} sx={sx}>
      <Select {...props}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </Select>
    </Field>
  )
}

export function CheckField({ label, hint, sx, ...props }) {
  return (
    <Box sx={{ mb: 2, ...sx }}>
      <Label sx={{ display: 'flex', alignItems: 'center', gap: 2, fontSize: 2, color: 'text' }}>
        <input type="checkbox" {...props} />
        {label}
      </Label>
      {hint && (
        <Text sx={{ display: 'block', fontSize: 0, color: 'muted', ml: 4 }}>{hint}</Text>
      )}
    </Box>
  )
}

export function StatusBadge({ status }) {
  const map = {
    'Hoạt động': 'ok', 'Không hoạt động': 'error', 'Chưa kiểm tra': 'muted',
    'Đang mở': 'ok', 'Chưa mở': 'warn', 'Đã đóng': 'muted', 'Chưa rõ': 'info',
    registered: 'ok', already: 'ok', paused: 'info', dry_run: 'info',
    closed: 'muted', error: 'error', login_failed: 'error', ip_blocked: 'warn',
    unverified: 'warn', skipped: 'muted', done: 'ok', running: 'info',
    cancelled: 'warn',
  }
  const variant = map[status] || 'muted'
  return <Badge variant={variant}>{status || '—'}</Badge>
}

export function Progress({ done, total, sx }) {
  const value = total ? Math.min(100, Math.round((done / total) * 100)) : 0
  return (
    <Flex sx={{ alignItems: 'center', gap: 2, ...sx }}>
      <Box
        sx={{
          flex: 1, height: 6, borderRadius: 'pill', bg: 'surfaceAlt',
          overflow: 'hidden',
        }}
      >
        <Box
          sx={{
            width: `${value}%`, height: '100%', bg: value === 100 ? 'ok' : 'accent',
            transition: 'width .25s ease',
          }}
        />
      </Box>
      <Text sx={{ fontSize: 1, color: 'muted', minWidth: 56, textAlign: 'right' }}>
        {done}/{total}
      </Text>
    </Flex>
  )
}

export function Empty({ children }) {
  return (
    <Box sx={{ p: 5, textAlign: 'center', color: 'muted', fontSize: 2 }}>{children}</Box>
  )
}

export function Toolbar({ children, sx }) {
  return (
    <Flex sx={{ gap: 2, alignItems: 'center', flexWrap: 'wrap', p: 3, ...sx }}>
      {children}
    </Flex>
  )
}

export { Badge, Box, Button, Flex, Input, Label, Select, Text }
