// 말로 묻기 — 음성 → 글자 (Web Worker, 2026-11-03 grace «맥·윈도우 노트북·데스크톱 어디서나 내장 마이크로»)
//
// Whisper(onnx-community/whisper-base, 8bit 약 77MB)를 브라우저 안에서 돌린다. 목소리는 이 컴퓨터 밖으로
// 나가지 않는다 — 바깥에서 받는 것은 처음 한 번 «프로그램·모델 파일»뿐이고 브라우저가 저장해 다시 쓴다.
// 사내망으로 옮길 때는 LIB_URL·MODEL_HOST 를 우리 서버 주소로 바꾸면 바깥 연결이 아예 없어진다.
// 화면이 멈추지 않게 워커에서 돈다(받기 진행률·결과만 메시지로 보낸다).

const LIB_URL = "https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.8.1"
const MODEL = "onnx-community/whisper-base"
const MODEL_HOST = ""        // 비우면 huggingface.co — 사내 서버로 옮기면 "/models/" 같은 주소

let asr = null

async function load() {
  if (asr) return asr
  const tf = await import(/* @vite-ignore */ LIB_URL)
  if (MODEL_HOST) { tf.env.remoteHost = MODEL_HOST; tf.env.remotePathTemplate = "{model}/" }
  tf.env.allowLocalModels = false
  // CPU(wasm) 8bit 한 가지로 — 그래픽 가속(WebGPU)+8bit 조합은 글자가 깨져 나왔다(11/3 확인).
  //   짧은 명령은 CPU 로도 1~2초면 된다.
  const files = {}
  asr = await tf.pipeline("automatic-speech-recognition", MODEL, {
    device: "wasm",
    dtype: "q8",
    progress_callback: p => {
      if (p.status !== "progress" || !p.total) return
      files[p.file] = [p.loaded, p.total]
      const v = Object.values(files)
      const pct = Math.round(100 * v.reduce((a, x) => a + x[0], 0) / v.reduce((a, x) => a + x[1], 0))
      self.postMessage({type: "progress", pct})
    },
  })
  return asr
}

self.onmessage = async ({data}) => {
  try {
    if (data.type === "load") {
      await load()
      self.postMessage({type: "ready"})
    } else if (data.type === "transcribe") {
      const run = await load()
      const out = await run(data.audio, {language: "korean", task: "transcribe", max_new_tokens: 64})
      self.postMessage({type: "text", text: (out?.text || "").trim()})
    }
  } catch (e) {
    self.postMessage({type: "error", message: String(e?.message || e)})
  }
}
