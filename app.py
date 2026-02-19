import streamlit as st
import pandas as pd
from streamlit_echarts import st_echarts
from dune_client.client import DuneClient

st.set_page_config(page_title="RedStone Atom: Venus OEV Analysis", layout="wide")
st.title("RedStone Atom: Venus OEV Analysis")
st.markdown("*Analysis covers liquidations from 7 February 2026 00:00 CET onwards.*")


@st.cache_data(ttl=21600)  # refresh every 6 hours
def load_data():
    dune = DuneClient(st.secrets["DUNE_API_KEY"])
    result = dune.get_latest_result(6702800)
    return pd.DataFrame(result.result.rows)


l_2023 = load_data()

# --- Shared filtering ---
df_filtered = l_2023[
    (l_2023["oev_provider"].isin(["Chainlink", "RedStone"]))
    & (l_2023["oev_to_collateral_ratio"].notna())
].copy()
df_filtered["date"] = pd.to_datetime(df_filtered["block_time"]).dt.date

# =============================================================
# Chart 1: Overall Dollar-Weighted Average OEV/Collateral Ratio
# =============================================================
st.header("Overall Dollar-Weighted Average OEV/Collateral Ratio")

overall_avg = (
    df_filtered.groupby("oev_provider")
    .apply(
        lambda x: (x["oev_to_collateral_ratio"] * x["total_coll_seized_usd"]).sum()
        / x["total_coll_seized_usd"].sum()
        * 100,
        include_groups=False,
    )
    .reset_index(name="weighted_avg_ratio_pct")
)

chart1_data = overall_avg.set_index("oev_provider")["weighted_avg_ratio_pct"].to_dict()
options1 = {
    "title": {"text": "Overall Dollar-Weighted Average OEV/Collateral Ratio by Provider", "left": "center"},
    "tooltip": {"trigger": "axis"},
    "xAxis": {"type": "category", "data": list(chart1_data.keys())},
    "yAxis": {"type": "value", "axisLabel": {"formatter": "{value}%"}},
    "series": [{
        "type": "bar",
        "data": [
            {"value": round(v, 3), "itemStyle": {"color": "#0847F7" if k == "Chainlink" else "#AE0822"}}
            for k, v in chart1_data.items()
        ],
        "label": {"show": True, "position": "top", "formatter": "{c}%"},
        "barWidth": "40%",
    }],
}

_, col_c1, _ = st.columns([1, 2, 1])
with col_c1:
    st_echarts(options=options1, height="400px")

# =============================================================
# Table: RedStone Liquidations (collateral seized > $1)
# =============================================================
st.header("RedStone Liquidations (Collateral Seized > $1)")

redstone_liqs = l_2023[
    (l_2023["oev_provider"] == "RedStone") &
    (l_2023["total_coll_seized_usd"] > 1)
][["tx_hash", "coll_tokens", "debt_tokens", "total_coll_seized_usd", "total_debt_repaid_usd", "oev_bid_usd"]].sort_values("oev_bid_usd", ascending=False)

total_rs_coll = l_2023[
    (l_2023["oev_provider"] == "RedStone") &
    (l_2023["oev_to_collateral_ratio"].notna())
]["total_coll_seized_usd"].sum()

col1, col2 = st.columns(2)
col1.metric("Total RedStone Liquidations (coll > $1)", len(redstone_liqs))
col2.metric("Total Collateral Seized by RedStone", f"${total_rs_coll:,.2f}")

st.dataframe(redstone_liqs, use_container_width=True)

# =============================================================
# Chart 2: OEV Recapture Efficiency (Venus 5% treasury adjusted)
# =============================================================
st.header("OEV Recapture Efficiency")
st.caption("Venus protocol retains a constant 5% treasury fee on every liquidation. Recapture efficiency measures OEV recaptured vs the solver's share only.")

df_oev = l_2023[l_2023["oev_provider"].isin(["Chainlink", "RedStone"])].copy()

stats = df_oev.groupby("oev_provider").agg(
    oev_liquidation_count=("tx_hash", "count"),
    total_collateral_liquidated_usd=("total_coll_seized_usd", "sum"),
    total_debt_repaid_usd=("total_debt_repaid_usd", "sum"),
    total_oev_usd=("oev_bid_usd", "sum"),
).reset_index()

stats["total_actual_bonus_usd"] = stats["total_collateral_liquidated_usd"] - stats["total_debt_repaid_usd"]
stats["treasury_fee_usd"] = 0.05 * stats["total_debt_repaid_usd"]
stats["recapturable_bonus_usd"] = stats["total_actual_bonus_usd"] - stats["treasury_fee_usd"]
stats["realized_LB_pct_without_oev"] = (stats["total_actual_bonus_usd"] / stats["total_collateral_liquidated_usd"]) * 100
stats["realized_LB_pct_with_oev"] = ((stats["total_actual_bonus_usd"] - stats["total_oev_usd"]) / stats["total_collateral_liquidated_usd"]) * 100
stats["oev_recapture_pct"] = (stats["total_oev_usd"] / stats["recapturable_bonus_usd"]) * 100

chart2_data = stats.set_index("oev_provider")["oev_recapture_pct"].to_dict()
options2 = {
    "title": {"text": "OEV Recapture Efficiency by Provider", "left": "center"},
    "tooltip": {"trigger": "axis"},
    "xAxis": {"type": "category", "data": list(chart2_data.keys())},
    "yAxis": {"type": "value", "min": 0, "max": 100, "axisLabel": {"formatter": "{value}%"}},
    "series": [{
        "type": "bar",
        "data": [
            {"value": round(v, 2), "itemStyle": {"color": "#0847F7" if k == "Chainlink" else "#AE0822"}}
            for k, v in chart2_data.items()
        ],
        "label": {"show": True, "position": "top", "formatter": "{c}%"},
        "barWidth": "40%",
    }],
}

_, col_c2, _ = st.columns([1, 2, 1])
with col_c2:
    st_echarts(options=options2, height="400px")

st.divider()

col_cl, col_rs = st.columns(2)
provider_cols = {"Chainlink": col_cl, "RedStone": col_rs}

for _, row in stats.iterrows():
    col = provider_cols[row["oev_provider"]]
    with col:
        st.subheader(row["oev_provider"])
        st.metric("OEV Recapture Efficiency", f"{row['oev_recapture_pct']:.2f}%")
        st.metric("Liquidation Count", int(row["oev_liquidation_count"]))
        st.metric("Total Collateral Liquidated", f"${row['total_collateral_liquidated_usd']:,.2f}")
        st.metric("Total Debt Repaid", f"${row['total_debt_repaid_usd']:,.2f}")
        st.metric("Total Liquidation Bonus", f"${row['total_actual_bonus_usd']:,.2f}")
        st.metric("  └ Treasury Fee (5%, constant)", f"${row['treasury_fee_usd']:,.2f}")
        st.metric("  └ Recapturable Bonus (solver share)", f"${row['recapturable_bonus_usd']:,.2f}")
        st.metric("Total OEV Recaptured", f"${row['total_oev_usd']:,.2f}")
        st.metric("Simulated realized LB % without OEV Solution", f"{row['realized_LB_pct_without_oev']:.3f}%")
        st.metric("Realized LB % with OEV Solution", f"{row['realized_LB_pct_with_oev']:.3f}%")

# =============================================================
# Chart 3: RedStone Collateral Seized by Token
# =============================================================
st.header("RedStone: Total Collateral Seized by Token")

df_rs = l_2023[l_2023["oev_provider"] == "RedStone"].copy()
rs_by_coll = df_rs.groupby("coll_tokens")["total_coll_seized_usd"].sum().reset_index()
rs_by_coll = rs_by_coll[rs_by_coll["total_coll_seized_usd"] >= 5].sort_values("total_coll_seized_usd", ascending=False)

options3 = {
    "title": {"text": "RedStone: Total Collateral Seized by Token", "left": "center"},
    "tooltip": {"trigger": "axis"},
    "xAxis": {"type": "category", "data": rs_by_coll["coll_tokens"].tolist(), "axisLabel": {"rotate": 45}},
    "yAxis": {"type": "value", "axisLabel": {"formatter": "${value}"}},
    "series": [{
        "type": "bar",
        "data": [round(v, 2) for v in rs_by_coll["total_coll_seized_usd"].tolist()],
        "itemStyle": {"color": "#AE0822"},
        "label": {"show": False},
    }],
}

_, col_c3, _ = st.columns([1, 2, 1])
with col_c3:
    st_echarts(options=options3, height="400px")
