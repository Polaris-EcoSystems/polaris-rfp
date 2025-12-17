const fs = require('fs')
const path = require('path')

function rmrf(p) {
  try {
    fs.rmSync(p, { recursive: true, force: true })
  } catch {}
}

function mkdirp(p) {
  fs.mkdirSync(p, { recursive: true })
}

function copyDir(src, dest) {
  if (!fs.existsSync(src)) return
  mkdirp(dest)
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const s = path.join(src, entry.name)
    const d = path.join(dest, entry.name)
    if (entry.isDirectory()) copyDir(s, d)
    else if (entry.isSymbolicLink()) {
      const real = fs.readlinkSync(s)
      fs.symlinkSync(real, d)
    } else {
      fs.copyFileSync(s, d)
    }
  }
}

function main() {
  const root = path.resolve(__dirname, '..')
  const nextDir = path.join(root, '.next')
  const standaloneDir = path.join(nextDir, 'standalone')
  const nextStaticDir = path.join(nextDir, 'static')
  const publicDir = path.join(root, 'public')

  const outDir = path.join(root, '.amplify-hosting')
  const outStatic = path.join(outDir, 'static')
  const outCompute = path.join(outDir, 'compute', 'default')

  if (!fs.existsSync(standaloneDir)) {
    console.error('Expected Next standalone output missing:', standaloneDir)
    console.error('Make sure next.config.js has output: "standalone" and build ran.')
    process.exit(1)
  }

  rmrf(outDir)
  mkdirp(outStatic)
  mkdirp(outCompute)

  // Compute: copy standalone server bundle
  copyDir(standaloneDir, outCompute)

  // Static: copy public assets + Next static assets
  if (fs.existsSync(publicDir)) copyDir(publicDir, outStatic)
  if (fs.existsSync(nextStaticDir)) {
    const dest = path.join(outStatic, '_next', 'static')
    copyDir(nextStaticDir, dest)
  }

  const deployManifest = {
    version: 1,
    framework: { name: 'nextjs', version: '15' },
    computeResources: [
      {
        name: 'default',
        entrypoint: 'server.js',
        runtime: 'nodejs20.x',
      },
    ],
    routes: [
      {
        path: '/*',
        target: { kind: 'Compute', src: 'default' },
      },
    ],
  }

  fs.writeFileSync(
    path.join(outDir, 'deploy-manifest.json'),
    JSON.stringify(deployManifest, null, 2),
  )

  console.log('Wrote Amplify Hosting output to', outDir)
}

main()
