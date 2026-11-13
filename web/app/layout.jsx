import './globals.css'
import Providers from './providers'
import AppShell from '@/components/AppShell'

export const metadata = {
  title: 'NAMCO Account Manager',
  description: 'Quản lý tài khoản và chiến dịch NAMCO Parks',
}

export default function RootLayout({ children }) {
  return (
    <html lang="vi">
      <body>
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  )
}
