import { defineConfig } from "vite"
import { resolve } from "node:path"

// 빌드 산출물은 app/static/ 으로 떨어지고 FastAPI(StaticFiles)가 서빙한다.
// base:"/" — SPA 는 루트에서 열린다(/app/ 은 301 로 / 로 보낸다).
export default defineConfig({
  base: "/",
  build: {
    outDir: resolve(import.meta.dirname, "../static"),
    emptyOutDir: true,
    assetsDir: "assets",
  },
})
