// 챗봇·도움말 버튼이 쓰는 캐릭터 그림 — 한 곳에서만 정한다.
// 그림을 바꾸려면 assets/characters/ 의 webp 를 «같은 이름»으로 갈아 끼우면 된다
// (Vite 가 빌드 때 파일 내용 해시를 이름에 붙이므로 /assets 영구 캐시에도 새 그림이 바로 보인다).
// 표정 파일이 없는 캐릭터는 머리 그림으로 대신한다.
import mt from "../assets/characters/mt.webp"
import mtHead from "../assets/characters/mt-head.webp"
import mtThink from "../assets/characters/mt-think.webp"
import mtWow from "../assets/characters/mt-wow.webp"
import gtHead from "../assets/characters/gt-head.webp"
import ycHead from "../assets/characters/yc-head.webp"
import hj from "../assets/characters/hj.webp"
import hjThink from "../assets/characters/hj-think.webp"

export const CHAR_IMG = {
  mt: {full: mt, head: mtHead, think: mtThink, wow: mtWow},
  gt: {full: gtHead, head: gtHead, think: gtHead, wow: gtHead},
  yc: {full: ycHead, head: ycHead, think: ycHead, wow: ycHead},
  hj: {full: hj, head: hj, think: hjThink, wow: hjThink},
}
