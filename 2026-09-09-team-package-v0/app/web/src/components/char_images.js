// 챗봇·도움말 버튼이 쓰는 캐릭터 그림 — 한 곳에서만 정한다.
// 원본: handoff/characters-3d-v2-20261027/assets/*.png(1254px 투명 PNG) → 512px webp, 머리(-head)는 heads/*-happy-head.png(머리만 따로 그린 것) → 256px.
// 그림을 바꾸려면 assets/characters/ 의 webp 를 «같은 이름»으로 갈아 끼우면 된다
// (Vite 가 빌드 때 파일 내용 해시를 이름에 붙이므로 /assets 영구 캐시에도 새 그림이 바로 보인다).
import mt from "../assets/characters/mt.webp"
import mtHead from "../assets/characters/mt-head.webp"
import mtThink from "../assets/characters/mt-think.webp"
import mtWow from "../assets/characters/mt-wow.webp"
import gt from "../assets/characters/gt.webp"
import gtHead from "../assets/characters/gt-head.webp"
import gtHappy from "../assets/characters/gt-happy.webp"
import yc from "../assets/characters/yc.webp"
import ycHead from "../assets/characters/yc-head.webp"
import ycNoForecast from "../assets/characters/yc-no-forecast.webp"
import hj from "../assets/characters/hj.webp"
import hjThink from "../assets/characters/hj-think.webp"

// full 전신 · head 대화창 동그라미 · think 답을 만드는 중 · wow 못 알아들음 · happy 처리 끝 · empty 결과 없음
export const CHAR_IMG = {
  mt: {full: mt, head: mtHead, think: mtThink, wow: mtWow, happy: mt, empty: mtThink},
  gt: {full: gt, head: gtHead, think: gtHead, wow: gtHead, happy: gtHappy, empty: gtHead},
  yc: {full: yc, head: ycHead, think: ycNoForecast, wow: ycNoForecast, happy: yc, empty: ycNoForecast},
  hj: {full: hj, head: hj, think: hjThink, wow: hjThink, happy: hj, empty: hjThink},
}
