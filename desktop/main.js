// Vỏ Electron: nạp bản build tĩnh của Next.js qua protocol `app://`.
//
// Vì sao không nạp http://localhost:3000: bản tĩnh không cần Next server nên app
// không chiếm thêm cổng nào, khởi động nhanh và không phụ thuộc Node ở thời điểm chạy.
// API Python vẫn là backend (mặc định http://127.0.0.1:8787, truyền qua env API_BASE).
const { app, BrowserWindow, Menu, net, protocol, shell } = require('electron')
const fs = require('node:fs')
const path = require('node:path')
const { pathToFileURL } = require('node:url')

const WEB_ROOT = path.resolve(__dirname, '..', 'web', 'out')
const API_BASE = process.env.API_BASE || 'http://127.0.0.1:8787'
const DEV_URL = process.env.UI_URL || '' // đặt UI_URL=http://localhost:3000 để dev UI

protocol.registerSchemesAsPrivileged([
  {
    scheme: 'app',
    privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true },
  },
])

function resolveFile(pathname) {
  let relative = decodeURIComponent(pathname || '/')
  if (relative === '/' || relative === '') {
    relative = '/index.html'
  } else if (relative.endsWith('/')) {
    relative = relative + 'index.html'
  } else if (!path.extname(relative)) {
    relative = relative + '/index.html'
  }
  const target = path.resolve(WEB_ROOT, '.' + relative)
  // Chặn path traversal ra ngoài thư mục build.
  if (!target.startsWith(WEB_ROOT)) return path.join(WEB_ROOT, 'index.html')
  return target
}

function createWindow() {
  const window = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 1024,
    minHeight: 680,
    backgroundColor: '#f5f6f8',
    title: 'NAMCO Account Manager',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      spellcheck: false,
    },
  })

  // Link ngoài (tài liệu, trang chiến dịch…) mở bằng trình duyệt hệ thống.
  window.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('http://') || url.startsWith('https://')) shell.openExternal(url)
    return { action: 'deny' }
  })

  if (DEV_URL) {
    window.loadURL(DEV_URL)
  } else {
    window.loadURL('app://local/')
  }

  // Tự kiểm tra: in ra stdout để launcher biết UI đã render thật.
  window.webContents.on('did-finish-load', async () => {
    try {
      const info = await window.webContents.executeJavaScript(
        '({ title: document.title, nav: document.querySelectorAll("a").length,' +
        ' root: Boolean(document.getElementById("__next")), api: window.__API_BASE__ || "" })',
      )
      console.log('[electron] UI loaded', JSON.stringify(info))
    } catch (error) {
      console.error('[electron] không đọc được trạng thái UI:', error.message)
    }
  })

  window.webContents.on('did-fail-load', (_event, code, description, url) => {
    console.error('[electron] load lỗi', code, description, url)
  })

  return window
}

app.whenReady().then(() => {
  if (!DEV_URL) {
    protocol.handle('app', (request) => {
      const { pathname } = new URL(request.url)
      const filePath = resolveFile(pathname)
      if (fs.existsSync(filePath)) {
        return net.fetch(pathToFileURL(filePath).toString())
      }
      const fallback = path.join(WEB_ROOT, '404.html')
      if (fs.existsSync(fallback)) {
        return net.fetch(pathToFileURL(fallback).toString())
      }
      return new Response('Không tìm thấy UI build. Chạy: cd web && npm run build', {
        status: 404,
        headers: { 'content-type': 'text/plain; charset=utf-8' },
      })
    })
  }

  const menu = Menu.buildFromTemplate([
    {
      label: 'Ứng dụng',
      submenu: [
        { role: 'reload', label: 'Tải lại' },
        { role: 'toggleDevTools', label: 'Công cụ phát triển' },
        { type: 'separator' },
        { role: 'quit', label: 'Thoát' },
      ],
    },
    {
      label: 'API',
      submenu: [
        {
          label: 'Mở tài liệu API',
          click: () => shell.openExternal(API_BASE + '/docs'),
        },
        {
          label: 'Mở thư mục ảnh chụp',
          click: () => shell.openPath(path.resolve(__dirname, '..', 'browser_artifacts')),
        },
      ],
    },
  ])
  Menu.setApplicationMenu(menu)

  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})
