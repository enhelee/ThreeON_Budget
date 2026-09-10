"""
사용자가 고른 행/열 기준으로 자유롭게 피벗 테이블을 만든다.
전년대비 증감율 계산 기능 포함.
"""
import pandas as pd


def build_pivot(df: pd.DataFrame, row_dims: list, col_dim: str | None, value_col: str = "금액") -> pd.DataFrame:
    if not row_dims:
        row_dims = ["연도"]
    if col_dim:
        pivot = df.pivot_table(index=row_dims, columns=col_dim, values=value_col, aggfunc="sum", fill_value=0)
    else:
        pivot = df.groupby(row_dims)[value_col].sum().to_frame(value_col)
    return pivot


def yoy_growth(df: pd.DataFrame, group_dims: list, value_col: str = "금액") -> pd.DataFrame:
    """
    group_dims 중 '연도'를 반드시 포함해야 한다.
    연도를 제외한 나머지 차원별로 그룹핑한 뒤, 연도순 정렬해서 전년대비 증감율(%)을 계산한다.
    """
    other_dims = [d for d in group_dims if d != "연도"]
    agg = df.groupby(group_dims)[value_col].sum().reset_index()

    if other_dims:
        agg = agg.sort_values(other_dims + ["연도"])
        agg["전년대비증감율(%)"] = agg.groupby(other_dims)[value_col].pct_change().round(3) * 100
    else:
        agg = agg.sort_values("연도")
        agg["전년대비증감율(%)"] = agg[value_col].pct_change().round(3) * 100

    return agg
