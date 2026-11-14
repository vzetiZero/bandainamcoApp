/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Electron nạp bản build tĩnh qua protocol `app://` (không cần Next server, không
  // chiếm thêm port). `trailingSlash` để mỗi route thành <route>/index.html.
  output: 'export',
  trailingSlash: true,
  images: { unoptimized: true },
  eslint: { ignoreDuringBuilds: true },
}

export default nextConfig
