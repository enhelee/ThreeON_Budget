"""설정 (매핑 관리) 화면"""
import glob
import streamlit as st
import pandas as pd
from mapping_config import (
    load_site_type_map, save_site_type_map, SITE_TYPE_OPTIONS,
    _code_prefix3, _find_by_prefix,
)


def render():
    st.caption("설정 · 매핑 관리")
    st.write("이 화면에서 입력한 값은 이 컴퓨터에만 저장되고, 외부로 전송되지 않습니다.")

    st.subheader("사업장 ↔ 지사유형 매핑 (연도별 이력)")
    site_map = load_site_type_map()
    st.caption("**사업장**: 실적데이터의 '사업 영역' 값이 그대로 들어갑니다 (코드일 수 있음, 예: 3070). "
               "**표시명**: 화면에 보여줄 실제 이름을 입력하세요 (예: 동탄지사) — 화면 곳곳에서 이 이름으로 표시됩니다. "
               "지사유형이 바뀐 적이 있다면, 같은 사업장코드에 여러 줄을 추가하고 '적용시작연도'를 다르게 입력하세요.")

    if st.button("업로드된 데이터에서 사업장 코드 목록 가져오기 (직접 타이핑 안 해도 됨)"):
        all_codes = set()
        for f in glob.glob("data_*.csv"):
            try:
                all_codes.update(pd.read_csv(f)["사업장"].dropna().astype(str).unique().tolist())
            except Exception:
                pass

        existing_codes = set(site_map["사업장"].astype(str)) if not site_map.empty else set()
        candidate_codes = sorted(all_codes - existing_codes)
        # 이미 등록된 코드와 앞 3자리가 같은 코드는 등록 없이도 이미 같은 지사로 인식되므로 제외한다.
        registered_list = list(existing_codes)
        candidate_codes = [c for c in candidate_codes if _find_by_prefix(registered_list, c) is None]

        if candidate_codes:
            # 새로 나온 코드들 중 4자리 숫자 코드는 앞 3자리가 같으면 한 그룹으로 묶어,
            # 대표 코드 1개만 등록 후보로 올린다 - 대표 코드에 표시명을 채우면 같은 그룹의
            # 나머지 코드도 자동으로 같은 이름으로 인식된다(get_site_display_name의 접두사 매칭).
            groups: dict[str, list[str]] = {}
            singles = []
            for c in candidate_codes:
                prefix = _code_prefix3(c)
                if prefix is None:
                    singles.append(c)
                else:
                    groups.setdefault(prefix, []).append(c)

            group_summary = []
            representatives = []
            for prefix, members in sorted(groups.items()):
                rep = sorted(members)[0]
                representatives.append(rep)
                if len(members) > 1:
                    group_summary.append({"대표 코드": rep, "묶이는 코드": ", ".join(sorted(members)), "건수": len(members)})

            to_add = singles + representatives
            new_rows = pd.DataFrame([
                {"사업장": c, "표시명": c, "지사유형": SITE_TYPE_OPTIONS[0], "적용시작연도": 1900} for c in to_add
            ])
            site_map = pd.concat([site_map, new_rows], ignore_index=True)
            save_site_type_map(site_map)

            msg = f"새 사업장 코드 {len(to_add)}건을 가져왔습니다"
            if group_summary:
                covered = sum(g["건수"] for g in group_summary)
                msg += f" ({len(group_summary)}개 그룹은 앞 3자리가 같은 코드끼리 묶어 대표 1개만 등록 — 총 {covered}개 코드를 대신함)"
            st.session_state["site_import_message"] = msg + ". 아래 표에서 대표 코드의 '표시명'을 채워주세요."
            st.session_state["site_import_group_summary"] = group_summary
            st.rerun()
        else:
            st.info("새로 가져올 사업장 코드가 없습니다 (이미 등록되어 있거나, 등록된 코드와 같은 지사로 인식됩니다).")

    if st.session_state.get("site_import_message"):
        st.success(st.session_state.pop("site_import_message"))
        summary = st.session_state.pop("site_import_group_summary", None)
        if summary:
            with st.expander("어떤 코드끼리 묶여서 등록됐는지 보기", expanded=True):
                st.dataframe(pd.DataFrame(summary), width="stretch", hide_index=True)

    edited_site = st.data_editor(
        site_map, num_rows="dynamic", width="stretch",
        column_config={
            "지사유형": st.column_config.SelectboxColumn(options=SITE_TYPE_OPTIONS),
            "적용시작연도": st.column_config.NumberColumn(format="%d", step=1),
        },
        key="site_editor",
    )
    if st.button("사업장 매핑 저장"):
        save_site_type_map(edited_site)
        st.success("저장 완료")

    st.divider()
    st.caption("💡 손익/자본 구분은 이제 별도로 입력하지 않아도 됩니다 — 손익예산/자본예산 실적집계표 양식에 있는 "
               "예산과목 목록을 기준으로 자동 판단합니다.")
