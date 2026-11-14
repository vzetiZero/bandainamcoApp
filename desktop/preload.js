// Preload: chỉ đưa địa chỉ API vào trang, không mở Node cho web.
const { contextBridge } = require('electron')

contextBridge.exposeInMainWorld('__API_BASE__', process.env.API_BASE || '')
