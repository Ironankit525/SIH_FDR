// Evaluated by Vercel, not shipped as browser configuration. No credentials belong here.
const value = process.env.BACKEND_ORIGIN
if (!value) throw new Error('Set BACKEND_ORIGIN in Vercel to the Render HTTPS origin before deploying.')
const backend = new URL(value)
if (backend.protocol !== 'https:' || backend.username || backend.password || backend.pathname !== '/' || backend.search || backend.hash) {
  throw new Error('BACKEND_ORIGIN must be an HTTPS origin, without credentials, /api, or query parameters.')
}

export const config = {
  framework: 'vite',
  buildCommand: 'npm run build',
  outputDirectory: 'dist',
  rewrites: [
    { source: '/api/:path*', destination: `${backend.origin}/api/:path*` },
    { source: '/((?!api(?:/|$)).*)', destination: '/index.html' },
  ],
}
