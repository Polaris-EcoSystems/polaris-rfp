/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Produce a self-contained server bundle for Amplify Hosting (WEB_COMPUTE).
  output: 'standalone',
  turbopack: {
    // Silence "multiple lockfiles" warning by pinning workspace root.
    root: __dirname,
  },
  env: {
    API_BASE_URL: process.env.API_BASE_URL || 'https://api.rfp.polariseco.com',
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
  async headers() {
    const isProd = process.env.NODE_ENV === 'production'
    /** @type {import('next').Header[]} */
    const securityHeaders = [
      { key: 'X-Content-Type-Options', value: 'nosniff' },
      { key: 'X-Frame-Options', value: 'DENY' },
      { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
      {
        key: 'Permissions-Policy',
        value:
          'camera=(), microphone=(), geolocation=(), interest-cohort=(), payment=()',
      },
      // HSTS only makes sense on HTTPS + production.
      ...(isProd
        ? [
            {
              key: 'Strict-Transport-Security',
              value: 'max-age=31536000; includeSubDomains',
            },
          ]
        : []),
    ]

    return [
      {
        source: '/:path*',
        headers: securityHeaders,
      },
    ]
  },
}

module.exports = nextConfig
