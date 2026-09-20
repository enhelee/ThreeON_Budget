/** @type {import('tailwindcss').Config} */
// 한난 디자인 시스템 토큰(Phase 8). 값의 근거는 docs/superpowers/specs/2026-09-21-한난-디자인시스템-design.md §2·§3.
//   brand  = CI 매뉴얼 BS12 공식 RGB 254·0·9 (시안 DESIGN-NOTES 의 빨강은 이미지 추출값 — 쓰지 않는다)
//   중성·상태색 = 시안 globals.css + openai-light.md 시맨틱
// 이름을 짧게 둔 이유: 뷰 10개에 수백 번 쓰인다. `text-ink` `bg-subtle` `border-line` 처럼 읽힌다.
// 같은 값이 src/styles/app.css 의 :root 변수에도 있다(custom.css 용) — 바꿀 땐 두 곳을 함께.
export default {
  // 기존 화면과 동일한 결과를 내야 하므로 버전을 3.4.17 로 고정한다(package.json).
  content: ["./index.html", "./src/**/*.{js,html}"],
  theme: {
    extend: {
      colors: {
        ink: "#0D0D0D",          // text-primary
        sub: "#5D5D5D",          // text-secondary (흰 배경 대비 6.58:1)
        tri: "#767676",          // text-tertiary (캡션·빈 상태 문구). 시안값 #8F8F8F 는 흰 배경 3.23:1 — 12px 캡션 본문에
                                 //   실제로 쓰이므로(«귀속 전표 없음» 등) AA 4.5 를 넘는 값으로 올렸다(4.54:1)
        dis: "#A6A6A6",          // text-disabled (비활성 전용 — 대비 기준 면제)
        line: { DEFAULT: "#E5E5E5", strong: "#C9C9C9", subtle: "#F2F2F2" },
        base: "#FFFFFF",
        subtle: "#F7F7F8",
        overlay: "rgba(13,13,13,0.56)",
        brand: { DEFAULT: "#FE0009", ink: "#000000" },
        ok: { DEFAULT: "#16794A", bg: "#EAF5EF" },
        warn: { DEFAULT: "#8F6000", bg: "#FFF4D6" },   // 시안값 #9A6700 은 warn-bg 위 4.44:1 — 4.5 미달이라 한 단계 어둡게(4.99:1)
        err: { DEFAULT: "#B42318", bg: "#FDECEC" },
        info: { DEFAULT: "#315EAC", bg: "#EAF2FF" },
      },
      borderRadius: { card: "16px", visual: "24px", control: "12px" },
      boxShadow: { float: "0 8px 24px rgba(0,0,0,0.10)" },
      fontFamily: {
        hanan: ['"HananCha"', "Pretendard", '"Apple SD Gothic Neo"', '"Malgun Gothic"', "system-ui", "sans-serif"],
        body: ["Pretendard", '"Apple SD Gothic Neo"', '"Malgun Gothic"', "system-ui", "sans-serif"],
      },
      transitionDuration: { DEFAULT: "180ms" },
    },
  },
  plugins: [],
}
