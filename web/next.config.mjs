/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // API chạy riêng (python server.py) nên không cần rewrite; client gọi trực tiếp
  // qua NEXT_PUBLIC_API (mặc định http://127.0.0.1:8787).
}

export default nextConfig
