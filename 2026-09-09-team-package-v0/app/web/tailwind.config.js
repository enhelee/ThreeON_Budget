/** @type {import('tailwindcss').Config} */
export default {
  // 기존 화면과 동일한 결과를 내야 하므로 버전을 3.4.17 로 고정한다(package.json).
  content: ["./index.html", "./src/**/*.{js,html}"],
  theme: { extend: {} },
  plugins: [],
}
