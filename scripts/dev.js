import { spawn } from 'node:child_process'
import { createInterface } from 'node:readline'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const python = join(projectRoot, '.venv', 'Scripts', 'python.exe')
const vite = join(projectRoot, 'frontend', 'node_modules', 'vite', 'bin', 'vite.js')
const taskkill = join(process.env.SystemRoot ?? 'C:\\Windows', 'System32', 'taskkill.exe')

const definitions = [
  {
    name: 'backend',
    command: python,
    args: [
      '-m',
      'uvicorn',
      'ml_project.api.main:app',
      '--reload',
      '--host',
      '127.0.0.1',
      '--port',
      '8000',
    ],
  },
  {
    name: 'frontend',
    command: process.execPath,
    args: [vite, 'frontend', '--config', 'frontend/vite.config.ts', '--strictPort'],
  },
]

const services = []
let stopping = false
let exitCode = 0

function log(name, stream) {
  const lines = createInterface({ input: stream })
  lines.on('line', line => console.log(`[${name}] ${line}`))
}

function waitForClose(child, timeoutMs = 5000) {
  if (child.exitCode !== null || child.signalCode !== null) return Promise.resolve(true)
  return new Promise(resolveClose => {
    const timer = setTimeout(() => {
      child.removeListener('close', onClose)
      resolveClose(false)
    }, timeoutMs)
    const onClose = () => {
      clearTimeout(timer)
      resolveClose(true)
    }
    child.once('close', onClose)
  })
}

function terminateWindowsTree(child) {
  return new Promise((resolveTermination, rejectTermination) => {
    const killer = spawn(taskkill, ['/PID', String(child.pid), '/T', '/F'], {
      stdio: 'ignore',
      windowsHide: true,
    })
    killer.once('error', rejectTermination)
    killer.once('close', code => {
      if (code === 0 || child.exitCode !== null || child.signalCode !== null) {
        resolveTermination()
      } else {
        rejectTermination(new Error(`taskkill exited with code ${code}`))
      }
    })
  })
}

async function stopService(service) {
  const { child, name } = service
  if (child.exitCode !== null || child.signalCode !== null) return

  if (process.platform === 'win32') {
    try {
      await terminateWindowsTree(child)
    } catch (error) {
      console.error(`[${name}] Unable to terminate its process tree: ${error.message}`)
      child.kill()
    }
  } else {
    try {
      process.kill(-child.pid, 'SIGTERM')
    } catch (error) {
      if (error.code !== 'ESRCH') child.kill('SIGTERM')
    }
  }

  if (!(await waitForClose(child))) {
    console.error(`[${name}] Did not exit promptly; forcing termination.`)
    if (process.platform === 'win32') {
      try {
        await terminateWindowsTree(child)
      } catch (error) {
        console.error(`[${name}] Forced process-tree termination failed: ${error.message}`)
      }
    } else {
      try {
        process.kill(-child.pid, 'SIGKILL')
      } catch (error) {
        if (error.code !== 'ESRCH') child.kill('SIGKILL')
      }
    }
    await waitForClose(child)
  }
}

async function shutdown(reason, code = 0) {
  if (stopping) return
  stopping = true
  exitCode = code
  console.log(`Stopping development services (${reason}).`)
  await Promise.all(services.map(stopService))
  process.exitCode = exitCode
}

for (const definition of definitions) {
  const child = spawn(definition.command, definition.args, {
    cwd: projectRoot,
    stdio: ['inherit', 'pipe', 'pipe'],
    windowsHide: true,
    detached: true,
  })
  const service = { ...definition, child }
  services.push(service)
  log(definition.name, child.stdout)
  log(definition.name, child.stderr)
  child.once('error', error => {
    console.error(`[${definition.name}] Failed to start: ${error.message}`)
    void shutdown(`${definition.name} failed to start`, 1)
  })
  child.once('close', (code, signal) => {
    if (!stopping) {
      const failed = code !== 0
      console.error(
        `[${definition.name}] exited ${signal ? `from ${signal}` : `with code ${code}`}.`,
      )
      void shutdown(`${definition.name} exited`, failed ? (code ?? 1) : 0)
    }
  })
}

process.on('SIGINT', () => void shutdown('Ctrl+C', 130))
process.on('SIGTERM', () => void shutdown('SIGTERM', 143))
if (process.platform === 'win32') {
  process.on('SIGBREAK', () => void shutdown('Ctrl+Break', 131))
}
