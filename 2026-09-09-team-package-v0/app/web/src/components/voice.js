// 말로 묻기 — 내장 마이크 녹음 + 말이 끝나면 알아서 멈춤 + 워커(voice_worker.js)로 글자 바꾸기.
// 브라우저 음성 API(SpeechRecognition)는 쓰지 않는다: 크롬은 목소리를 구글로 보내고, 기기 안 방식은
// 되는 브라우저가 적다. 녹음(getUserMedia)은 맥·윈도우·데스크톱의 크롬·엣지·사파리 어디서나 된다
// (https 또는 localhost 에서만 — 브라우저 규칙).

const RATE = 16000                 // Whisper 입력
const MAX_MS = 10000               // 한 번에 최대 10초
const SILENCE_MS = 1300            // 말한 뒤 이만큼 조용하면 끝
const NO_SPEECH_MS = 5000          // 이만큼 아무 말 없으면 그만
const LOUD = 0.02                  // 이보다 크면 «말하는 중»(RMS)

export const voiceSupported = () => !!(navigator.mediaDevices?.getUserMedia && window.MediaRecorder && window.Worker)

let worker = null, pending = null
function getWorker(onProgress) {
  if (!worker) {
    worker = new Worker(new URL("./voice_worker.js", import.meta.url), {type: "module"})
    worker.onmessage = ({data}) => {
      if (data.type === "progress") { onProgress?.(data.pct); return }
      const p = pending; pending = null
      if (!p) return
      data.type === "error" ? p.reject(new Error(data.message)) : p.resolve(data.text ?? "")
    }
  }
  return worker
}
const ask = (msg, onProgress) => new Promise((resolve, reject) => {
  pending = {resolve, reject}
  getWorker(onProgress).postMessage(msg)
})

/** 모델을 미리 받아 둔다(처음 한 번). onProgress(0~100). */
export const prepareVoice = onProgress => ask({type: "load"}, onProgress)

/** 녹음해서 Float32 16kHz 소리를 돌려준다. stop() 으로 일찍 끝낼 수 있다. onLevel(0~1) 은 소리 크기. */
export function record({onLevel} = {}) {
  let stopFn = () => {}
  const done = (async () => {
    const stream = await navigator.mediaDevices.getUserMedia({audio: {channelCount: 1, echoCancellation: true, noiseSuppression: true}})
    const ctx = new AudioContext()
    const src = ctx.createMediaStreamSource(stream)
    const an = ctx.createAnalyser(); an.fftSize = 1024
    src.connect(an)
    const rec = new MediaRecorder(stream)
    const chunks = []
    rec.ondataavailable = e => e.data.size && chunks.push(e.data)
    const stopped = new Promise(r => { rec.onstop = r })
    rec.start()
    const t0 = performance.now()
    let spoke = false, lastLoud = t0, raf = 0
    const buf = new Float32Array(an.fftSize)
    stopFn = () => { if (rec.state !== "inactive") rec.stop() }
    const tick = () => {
      an.getFloatTimeDomainData(buf)
      const rms = Math.sqrt(buf.reduce((a, x) => a + x * x, 0) / buf.length)
      onLevel?.(Math.min(1, rms * 8))
      const now = performance.now()
      if (rms > LOUD) { spoke = true; lastLoud = now }
      if (now - t0 > MAX_MS || (spoke && now - lastLoud > SILENCE_MS) || (!spoke && now - t0 > NO_SPEECH_MS)) { stopFn(); return }
      if (rec.state !== "inactive") raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    await stopped
    cancelAnimationFrame(raf)
    stream.getTracks().forEach(t => t.stop())
    await ctx.close()
    if (!spoke || !chunks.length) return null
    return toMono16k(await new Blob(chunks, {type: rec.mimeType}).arrayBuffer())
  })()
  return {done, stop: () => stopFn()}
}

async function toMono16k(arrayBuf) {
  const tmp = new AudioContext()
  const decoded = await tmp.decodeAudioData(arrayBuf)
  await tmp.close()
  const off = new OfflineAudioContext(1, Math.ceil(decoded.duration * RATE), RATE)
  const s = off.createBufferSource(); s.buffer = decoded; s.connect(off.destination); s.start()
  return (await off.startRendering()).getChannelData(0)
}

/** 소리 → 글자(한국어). */
export const transcribe = (audio, onProgress) => ask({type: "transcribe", audio}, onProgress)
