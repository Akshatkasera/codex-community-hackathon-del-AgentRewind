import { spawn } from 'node:child_process'
import fs from 'node:fs/promises'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

import ffmpegPath from 'ffmpeg-static'
import { chromium } from 'playwright'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const frontendDir = path.resolve(__dirname, '..')
const repoRoot = path.resolve(frontendDir, '..')
const backendDir = path.join(repoRoot, 'backend')
const backendEnvPath = path.join(backendDir, '.env')

async function main() {
  const config = await loadConfig()
  const outputDir = resolveRepoPath(config.outputDir)
  const tracePath = resolveRepoPath(config.tracePath)
  await fs.rm(outputDir, { recursive: true, force: true })
  await fs.mkdir(outputDir, { recursive: true })
  await cleanupImportedDemoTraces(tracePath)

  await ensureFrontendBuild()
  await ensurePlaywrightBrowser()

  const apiKey = await resolveApiKey()
  const narrationText = await fs.readFile(resolveRepoPath(config.narrationPath), 'utf8')
  const rawVideoDir = path.join(outputDir, 'raw')
  const rawVideoTarget = path.join(outputDir, 'agentrewind-demo-raw.webm')
  const audioExtension = config.tts.responseFormat
  const audioTarget = path.join(outputDir, `agentrewind-demo-narration.${audioExtension}`)
  const finalVideoTarget = path.join(outputDir, 'agentrewind-demo.mp4')

  await fs.mkdir(rawVideoDir, { recursive: true })

  const backendProcess = startBackend(config.port)
  try {
    await waitForHealth(config.port)
    await generateNarration({
      apiKey,
      narrationText,
      outputPath: audioTarget,
      tts: config.tts,
    })

    const correctedPrompt = await loadCorrectedPrompt(tracePath)
    const recordedVideoPath = await recordDemo({
      url: `http://127.0.0.1:${config.port}`,
      tracePath,
      frameworkHint: config.frameworkHint,
      correctedPrompt,
      rawVideoDir,
      waitsMs: config.waitsMs,
    })

    await fs.copyFile(recordedVideoPath, rawVideoTarget)
    await muxVideoAndAudio({
      videoPath: rawVideoTarget,
      audioPath: audioTarget,
      outputPath: finalVideoTarget,
    })

    console.log(`Demo video ready: ${finalVideoTarget}`)
    console.log(`Narration audio: ${audioTarget}`)
    console.log(`Raw browser recording: ${rawVideoTarget}`)
  } finally {
    backendProcess.kill()
    await cleanupImportedDemoTraces(tracePath)
  }
}

async function loadConfig() {
  const configPath = path.join(repoRoot, 'docs', 'demo', 'demo-video-config.json')
  return JSON.parse(await fs.readFile(configPath, 'utf8'))
}

function resolveRepoPath(relativeOrAbsolutePath) {
  return path.isAbsolute(relativeOrAbsolutePath)
    ? relativeOrAbsolutePath
    : path.join(repoRoot, relativeOrAbsolutePath)
}

async function ensureFrontendBuild() {
  await runCommand(npmCommand(), ['run', 'build'], { cwd: frontendDir })
}

async function ensurePlaywrightBrowser() {
  const executable = process.platform === 'win32'
    ? path.join(frontendDir, 'node_modules', '.bin', 'playwright.cmd')
    : path.join(frontendDir, 'node_modules', '.bin', 'playwright')
  await runCommand(executable, ['install', 'chromium'], { cwd: frontendDir })
}

function npmCommand() {
  return process.platform === 'win32' ? 'npm.cmd' : 'npm'
}

function pythonCommand() {
  return process.platform === 'win32'
    ? path.join(backendDir, '.venv', 'Scripts', 'python.exe')
    : path.join(backendDir, '.venv', 'bin', 'python')
}

function startBackend(port) {
  const env = {
    ...process.env,
    AGENTREWIND_USE_MOCK_LLM: 'true',
    OPENAI_API_KEY: '',
  }

  const child = spawn(
    pythonCommand(),
    ['-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', String(port)],
    {
      cwd: backendDir,
      env,
      stdio: ['ignore', 'pipe', 'pipe'],
    },
  )

  child.stdout.on('data', (chunk) => process.stdout.write(`[backend] ${chunk}`))
  child.stderr.on('data', (chunk) => process.stderr.write(`[backend] ${chunk}`))
  child.on('exit', (code) => {
    if (code !== null && code !== 0) {
      process.stderr.write(`[backend] exited with code ${code}\n`)
    }
  })
  return child
}

async function waitForHealth(port, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/health`)
      if (response.ok) {
        return
      }
    } catch {}
    await sleep(500)
  }
  throw new Error('Timed out waiting for the AgentRewind backend to start.')
}

async function resolveApiKey() {
  if (process.env.OPENAI_API_KEY) {
    return process.env.OPENAI_API_KEY
  }

  const envValues = await parseSimpleEnvFile(backendEnvPath)
  if (envValues.OPENAI_API_KEY) {
    return envValues.OPENAI_API_KEY
  }

  throw new Error('OpenAI API key not found. Set OPENAI_API_KEY in your shell or backend/.env before generating narration.')
}

async function parseSimpleEnvFile(filePath) {
  try {
    const contents = await fs.readFile(filePath, 'utf8')
    return Object.fromEntries(
      contents
        .split(/\r?\n/)
        .filter((line) => line.includes('='))
        .map((line) => {
          const [key, ...rest] = line.split('=')
          return [key.trim(), rest.join('=').trim()]
        }),
    )
  } catch {
    return {}
  }
}

async function generateNarration({ apiKey, narrationText, outputPath, tts }) {
  const response = await fetch('https://api.openai.com/v1/audio/speech', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model: tts.model,
      voice: tts.voice,
      input: narrationText.trim(),
      instructions: tts.instructions,
      response_format: tts.responseFormat,
      speed: tts.speed,
    }),
  })

  if (!response.ok) {
    throw new Error(`OpenAI TTS request failed: ${await response.text()}`)
  }

  const audioBuffer = Buffer.from(await response.arrayBuffer())
  await fs.writeFile(outputPath, audioBuffer)
}

async function loadCorrectedPrompt(tracePath) {
  const trace = JSON.parse(await fs.readFile(tracePath, 'utf8'))
  return (
    trace?.metadata?.demo_replay_prompt
    || 'Use the canonical policy source only. Ignore stale templates and write the exact current refund window to memory.'
  )
}

async function cleanupImportedDemoTraces(tracePath) {
  const trace = JSON.parse(await fs.readFile(tracePath, 'utf8'))
  const traceIdPrefix = trace?.trace_id
  if (!traceIdPrefix) {
    return
  }

  const importedDir = path.join(backendDir, 'imported_traces')
  let fileNames = []
  try {
    fileNames = await fs.readdir(importedDir)
  } catch {
    return
  }

  await Promise.all(
    fileNames
      .filter((fileName) => fileName.startsWith(traceIdPrefix))
      .map((fileName) => fs.rm(path.join(importedDir, fileName), { force: true })),
  )
}

async function recordDemo({
  url,
  tracePath,
  frameworkHint,
  correctedPrompt,
  rawVideoDir,
  waitsMs,
}) {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({
    viewport: { width: 1600, height: 900 },
    colorScheme: 'dark',
    recordVideo: {
      dir: rawVideoDir,
      size: { width: 1600, height: 900 },
    },
  })

  const page = await context.newPage()
  const video = page.video()

  try {
    await page.goto(url, { waitUntil: 'networkidle' })
    await sleep(waitsMs.landing)

    await page.getByTestId('import-run-toggle').click()
    await page.getByTestId('import-panel').waitFor()
    await sleep(waitsMs.importPanel)

    await page.getByTestId('import-framework-select').selectOption(frameworkHint)
    await page.getByTestId('import-file-input').setInputFiles(tracePath)
    await sleep(waitsMs.afterFileLoad)

    await page.getByTestId('import-run-button').click()
    await page.getByTestId('diagnosis-box').waitFor({ timeout: 15000 })
    await sleep(waitsMs.afterImport)
    await sleep(waitsMs.afterDiagnosis)

    const stepInput = page.getByTestId('step-edit-input')
    await stepInput.click()
    await stepInput.press(process.platform === 'darwin' ? 'Meta+A' : 'Control+A')
    await stepInput.press('Backspace')
    await stepInput.pressSequentially(correctedPrompt, { delay: waitsMs.typingDelay })
    await sleep(waitsMs.afterTyping)

    await page.getByTestId('replay-button').click()
    await page.getByText('Forked Output').waitFor({ timeout: 15000 })
    await sleep(waitsMs.afterReplay)
  } finally {
    await context.close()
    await browser.close()
  }

  if (!video) {
    throw new Error('Playwright did not return a recorded video for the demo run.')
  }
  return video.path()
}

async function muxVideoAndAudio({ videoPath, audioPath, outputPath }) {
  if (!ffmpegPath) {
    throw new Error('ffmpeg-static did not resolve a binary path.')
  }

  await runCommand(
    ffmpegPath,
    [
      '-y',
      '-i',
      videoPath,
      '-i',
      audioPath,
      '-c:v',
      'libx264',
      '-preset',
      'medium',
      '-pix_fmt',
      'yuv420p',
      '-c:a',
      'aac',
      '-b:a',
      '192k',
      '-movflags',
      '+faststart',
      '-shortest',
      outputPath,
    ],
    { cwd: repoRoot },
  )
}

async function runCommand(command, args, options) {
  await new Promise((resolve, reject) => {
    const useShell = process.platform === 'win32' && /\.(cmd|bat)$/i.test(command)
    const child = spawn(command, args, {
      cwd: options.cwd,
      env: options.env ?? process.env,
      stdio: 'inherit',
      shell: useShell,
    })
    child.on('error', reject)
    child.on('exit', (code) => {
      if (code === 0) {
        resolve()
        return
      }
      reject(new Error(`Command failed: ${command} ${args.join(' ')} (exit ${code ?? 'unknown'})`))
    })
  })
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
