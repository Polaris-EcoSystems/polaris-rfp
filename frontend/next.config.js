/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Produce a self-contained server bundle for Amplify Hosting (WEB_COMPUTE).
  output: 'standalone',
  env: {
    API_BASE_URL:
      process.env.API_BASE_URL ||
      'https://api.rfp.polariseco.com',
    NEXT_PUBLIC_API_BASE_URL:
      process.env.NEXT_PUBLIC_API_BASE_URL ||
      process.env.API_BASE_URL ||
      'https://api.rfp.polariseco.com',
  },
  // Amplify configuration
  trailingSlash: true,
  images: {
    unoptimized: true,
  },
  // Environment variables for build time
  publicRuntimeConfig: {
    API_BASE_URL:
      process.env.API_BASE_URL ||
      'https://api.rfp.polariseco.com',
    NEXT_PUBLIC_API_BASE_URL:
      process.env.NEXT_PUBLIC_API_BASE_URL ||
      process.env.API_BASE_URL ||
      'https://api.rfp.polariseco.com',
  },
}

module.exports = nextConfig
