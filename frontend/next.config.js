/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  swcMinify: true,
  env: {
    API_BASE_URL: process.env.API_BASE_URL || 'https://cvsmuhhazj.us-east-1.awsapprunner.com',
    NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL || process.env.API_BASE_URL || 'https://cvsmuhhazj.us-east-1.awsapprunner.com',
  },
  // Amplify configuration
  trailingSlash: true,
  images: {
    unoptimized: true
  },
  // Environment variables for build time
  publicRuntimeConfig: {
    API_BASE_URL: process.env.API_BASE_URL || 'https://cvsmuhhazj.us-east-1.awsapprunner.com',
    NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL || process.env.API_BASE_URL || 'https://cvsmuhhazj.us-east-1.awsapprunner.com',
  },
}

module.exports = nextConfig