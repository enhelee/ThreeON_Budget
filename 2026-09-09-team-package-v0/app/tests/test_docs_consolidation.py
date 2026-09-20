# -*- coding: utf-8 -*-
"""문서 통합(Phase 6-10)이 되돌아오지 않게 고정한다.

계약 문서 넷이 하나(연계계약_CONTRACT.md)가 됐고, Caddy·Streamlit 은 6-8 에서 사라졌다.
문서는 테스트가 없으면 조용히 썩는다 — 옛 이름이 다시 생기거나, 현행 문서가 사라진 구성을
현재형으로 말하기 시작하면 여기서 잡는다. 이력 문서(변경이력·2026-09-08 README·비교분석
보고서)는 과거를 그대로 적는 것이 맞으므로 검사하지 않는다.
"""
import os
import re

PKG = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOCS = os.path.join(PKG, "docs")
APP = os.path.join(PKG, "app")

OLD_CONTRACT_DOCS = ["연계규격_INTEGRATION.md", "연동규격_INTERFACE.md",
                     "연동_통합가이드.md", "연동_필드매핑.md"]
NEW_CONTRACT_DOC = "연계계약_CONTRACT.md"

# 현재형으로 유지되는 문서 — 사라진 구성을 말하면 안 된다.
LIVE_DOCS = ["배포가이드.md", "보안설계.md", "다음_할_일_체크리스트.md", "팀원_실행가이드.md",
             "사내이관_가이드.md", NEW_CONTRACT_DOC]


def _read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


def test_old_contract_docs_are_gone_and_new_one_exists():
    for name in OLD_CONTRACT_DOCS:
        assert not os.path.exists(os.path.join(DOCS, name)), f"{name} 이 다시 생겼습니다 — 연계계약_CONTRACT.md 에 합칩니다"
    assert os.path.isfile(os.path.join(DOCS, NEW_CONTRACT_DOC))


def test_new_contract_doc_keeps_the_live_boundaries():
    """통합하며 잃어버리면 안 되는 것 — 살아 있는 경계와 총액 보존 규칙."""
    body = _read(DOCS, NEW_CONTRACT_DOC)
    for needle in ("/api/export?kind=", "/api/forecast/import", "/api/forecast/export",
                   "import_v2_csv_dir", "총액 보존", "_erp_row", "utf-8-sig"):
        assert needle in body, f"연계계약_CONTRACT.md 에 «{needle}» 가 없습니다"


def test_code_comments_do_not_cite_removed_docs():
    """코드 주석이 없는 문서를 가리키면 다음 사람이 찾다 포기한다."""
    offenders = []
    for root, _, files in os.walk(os.path.join(APP, "src")):
        for f in files:
            if f.endswith(".py"):
                src = _read(root, f)
                for name in OLD_CONTRACT_DOCS:
                    if name.replace(".md", "") in src:
                        offenders.append(f"{f}: {name}")
    src = _read(APP, "server.py")
    for name in OLD_CONTRACT_DOCS:
        if name.replace(".md", "") in src:
            offenders.append(f"server.py: {name}")
    assert not offenders, offenders


def test_live_docs_do_not_describe_removed_infrastructure():
    """Caddy·Streamlit·supervisord 는 6-8 에서 사라졌다 — 현행 문서는 과거형으로만 언급한다.

    과거형 언급(«6-8 에서 삭제», «옛», «시절», «이전에는»)은 허용한다. 검사는 문장 단위로
    금지어가 있는 줄에 과거 표지가 하나도 없을 때만 잡는다.
    """
    banned = re.compile(r"caddy|streamlit|supervisord|forward_auth|basic_auth", re.I)
    past = re.compile(r"6-8|삭제|사라|옛|시절|이전|과거|역사|폐기|제거|없앴|걷어|들어냈|레거시|Phase 6")
    offenders = []
    for name in LIVE_DOCS:
        for i, line in enumerate(_read(DOCS, name).split("\n"), 1):
            if banned.search(line) and not past.search(line):
                offenders.append(f"{name}:{i}: {line.strip()[:80]}")
    assert not offenders, "\n".join(offenders)
