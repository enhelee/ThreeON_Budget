# ThreeON_Budget

한국지역난방공사 발전플랜트 유지보수 **예산·실적 분석 시스템**(ThreeON 팀). 지사 19곳의 예산계획과 SAP 실적 전표(zrfm2)를 자동으로 맞추고, 마감된 실적으로 정비등급별 표준금액과 2026~2035년 소요를 전망하는 웹 앱 하나.

- **앱과 문서는 전부 [`2026-09-09-team-package-v0/`](2026-09-09-team-package-v0/) 안에 있다.** 그 폴더의 [README](2026-09-09-team-package-v0/README.md)부터 읽는다.
- 저장소 루트에는 Render 배포 설정(`render.yaml`)과 이 안내만 둔다. 2026-09-21 정리 이전에 루트에 있던 초기 버전(Streamlit 앱·v2 전망 앱·실데이터 CSV)은 삭제했다 — 필요하면 git 이력(`git log --diff-filter=D`)에서 꺼낼 수 있다.
- 배포 주소·팀 비밀번호는 저장소에 없다. 팀원용 안내는 [팀공유_최종안내.html](2026-09-09-team-package-v0/docs/팀공유_최종안내.html), 개발자 인수인계는 [HANDOFF.md](2026-09-09-team-package-v0/docs/HANDOFF.md).

> 이 저장소는 public 이다. 실데이터·`.env`·DB 파일은 어떤 경우에도 커밋하지 않는다([보안설계.md](2026-09-09-team-package-v0/docs/보안설계.md)).
