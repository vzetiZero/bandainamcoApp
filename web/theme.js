// Theme theme-ui: token + biến thể dùng chung cho toàn UI.
// Đổi màu/nhịp điệu ở đây là đổi cả app; component không hard-code màu.
const accent = '#d61718'
const dark = {
  bg: '#0f1115',
  surface: '#171a21',
  surfaceAlt: '#1e222b',
  border: '#2a2f3a',
  text: '#e8eaee',
  muted: '#98a0ad',
  hover: '#222734',
}
const light = {
  bg: '#f5f6f8',
  surface: '#ffffff',
  surfaceAlt: '#f0f2f5',
  border: '#dfe3e9',
  text: '#14171c',
  muted: '#5b6472',
  hover: '#eef1f5',
}

export const makeTheme = (mode = 'light') => {
  const palette = mode === 'dark' ? dark : light
  return {
    config: { initialColorModeName: 'light', useColorSchemeMediaQuery: false },
    colors: {
      ...palette,
      accent,
      accentSoft: mode === 'dark' ? '#3a1416' : '#fdeceb',
      ok: '#1f9d55',
      okSoft: mode === 'dark' ? '#12291c' : '#e6f6ec',
      warn: '#b7791f',
      warnSoft: mode === 'dark' ? '#2c2415' : '#fdf3e2',
      error: '#d64545',
      errorSoft: mode === 'dark' ? '#2f1717' : '#fdeaea',
      info: '#2b6cb0',
      infoSoft: mode === 'dark' ? '#16202e' : '#e8f0fa',
      modes: { light, dark },
    },
    fonts: {
      body: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
      heading: 'inherit',
      mono: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
    },
    fontSizes: [11, 12, 13, 14, 16, 18, 22, 28],
    fontWeights: { body: 400, medium: 500, bold: 700 },
    lineHeights: { body: 1.5, heading: 1.25 },
    space: [0, 4, 8, 12, 16, 20, 24, 32, 40, 56],
    sizes: { sidebar: 232, content: 1280 },
    radii: { small: 6, default: 10, large: 14, pill: 999 },
    shadows: {
      card: mode === 'dark'
        ? '0 1px 2px rgba(0,0,0,.5)'
        : '0 1px 2px rgba(16,24,40,.06), 0 1px 3px rgba(16,24,40,.1)',
    },
    styles: {
      root: {
        fontFamily: 'body',
        fontSize: 2,
        lineHeight: 'body',
        color: 'text',
        bg: 'bg',
        minHeight: '100vh',
        WebkitFontSmoothing: 'antialiased',
      },
      a: { color: 'accent', textDecoration: 'none' },
      h1: { fontSize: 6, fontWeight: 'bold', m: 0 },
      h2: { fontSize: 5, fontWeight: 'bold', m: 0 },
      h3: { fontSize: 4, fontWeight: 'medium', m: 0 },
      p: { m: 0, my: 2 },
      code: { fontFamily: 'mono', fontSize: 1 },
      table: { borderCollapse: 'collapse', width: '100%' },
      th: {
        textAlign: 'left', fontSize: 1, fontWeight: 'medium', color: 'muted',
        textTransform: 'uppercase', letterSpacing: '.04em',
        borderBottom: '1px solid', borderColor: 'border', p: 2, whiteSpace: 'nowrap',
      },
      td: {
        fontSize: 2, p: 2, borderBottom: '1px solid', borderColor: 'border',
        verticalAlign: 'middle',
      },
    },
    buttons: {
      primary: {
        fontFamily: 'body', fontSize: 2, fontWeight: 'medium', cursor: 'pointer',
        px: 3, py: 2, borderRadius: 'default', border: '1px solid transparent',
        color: 'white', bg: 'accent',
        '&:hover': { filter: 'brightness(.92)' },
        '&:disabled': { opacity: 0.5, cursor: 'not-allowed' },
      },
      secondary: {
        fontFamily: 'body', fontSize: 2, fontWeight: 'medium', cursor: 'pointer',
        px: 3, py: 2, borderRadius: 'default',
        color: 'text', bg: 'surfaceAlt', border: '1px solid', borderColor: 'border',
        '&:hover': { bg: 'hover' },
        '&:disabled': { opacity: 0.5, cursor: 'not-allowed' },
      },
      ghost: {
        fontFamily: 'body', fontSize: 2, cursor: 'pointer',
        px: 2, py: 1, borderRadius: 'small', color: 'muted', bg: 'transparent',
        border: '1px solid transparent',
        '&:hover': { color: 'text', bg: 'surfaceAlt' },
      },
      danger: {
        fontFamily: 'body', fontSize: 2, cursor: 'pointer',
        px: 3, py: 2, borderRadius: 'default', color: 'error',
        bg: 'errorSoft', border: '1px solid', borderColor: 'error',
        '&:hover': { filter: 'brightness(.95)' },
      },
    },
    forms: {
      label: { fontSize: 1, color: 'muted', mb: 1, display: 'block' },
      input: {
        fontFamily: 'body', fontSize: 2, width: '100%', px: 2, py: 2,
        color: 'text', bg: 'surface', border: '1px solid', borderColor: 'border',
        borderRadius: 'small', outline: 'none',
        '&:focus': { borderColor: 'accent' },
      },
      select: {
        fontFamily: 'body', fontSize: 2, width: '100%', px: 2, py: 2,
        color: 'text', bg: 'surface', border: '1px solid', borderColor: 'border',
        borderRadius: 'small',
      },
      textarea: {
        fontFamily: 'mono', fontSize: 1, width: '100%', px: 2, py: 2,
        color: 'text', bg: 'surface', border: '1px solid', borderColor: 'border',
        borderRadius: 'small', resize: 'vertical',
      },
      checkbox: { accentColor: 'accent' },
    },
    cards: {
      panel: {
        bg: 'surface', border: '1px solid', borderColor: 'border',
        borderRadius: 'large', boxShadow: 'card', p: 4,
      },
      flat: {
        bg: 'surfaceAlt', borderRadius: 'default', p: 3,
      },
    },
    badges: {
      base: {
        fontSize: 0, fontWeight: 'medium', px: 2, py: '2px',
        borderRadius: 'pill', display: 'inline-block', whiteSpace: 'nowrap',
      },
      ok: { variant: 'badges.base', color: 'ok', bg: 'okSoft' },
      error: { variant: 'badges.base', color: 'error', bg: 'errorSoft' },
      warn: { variant: 'badges.base', color: 'warn', bg: 'warnSoft' },
      info: { variant: 'badges.base', color: 'info', bg: 'infoSoft' },
      muted: { variant: 'badges.base', color: 'muted', bg: 'surfaceAlt' },
      accent: { variant: 'badges.base', color: 'accent', bg: 'accentSoft' },
    },
    text: {
      muted: { color: 'muted' },
      mono: { fontFamily: 'mono', fontSize: 1 },
      label: { fontSize: 1, color: 'muted', textTransform: 'uppercase', letterSpacing: '.04em' },
    },
  }
}

export default makeTheme('light')
