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


@st.cache_data(ttl=86400)  # refresh every 24 hours
def load_coverage_data():
    dune = DuneClient(st.secrets["DUNE_API_KEY"])
    result = dune.get_latest_result(6715606)
    return pd.DataFrame(result.result.rows)


l_2023 = load_data()
oev_cov = load_coverage_data()

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
# Chart 2: Daily OEV Fees Recaptured (time series)
# =============================================================
st.header("Daily OEV Fees Recaptured")

df_daily = l_2023[l_2023["oev_provider"].isin(["Chainlink", "RedStone"])].copy()
df_daily["date"] = pd.to_datetime(df_daily["block_time"]).dt.date

prov_daily = st.radio("Provider", ["RedStone", "Chainlink"], index=0, horizontal=True, key="daily_oev_toggle")

daily_oev = (
    df_daily[df_daily["oev_provider"] == prov_daily]
    .groupby("date")["oev_bid_usd"].sum()
    .reset_index()
    .sort_values("date")
)
color_daily = "#AE0822" if prov_daily == "RedStone" else "#0847F7"

options_daily = {
    "title": {"text": f"Daily OEV Fees Recaptured — {prov_daily}", "left": "center"},
    "tooltip": {"trigger": "axis"},
    "xAxis": {"type": "category", "data": [str(d) for d in daily_oev["date"].tolist()], "axisLabel": {"rotate": 45}},
    "yAxis": {"type": "value", "axisLabel": {"formatter": "${value}"}},
    "series": [{
        "type": "bar",
        "data": [round(v, 2) for v in daily_oev["oev_bid_usd"].tolist()],
        "itemStyle": {"color": color_daily},
        "label": {"show": False},
    }],
}

_, col_daily, _ = st.columns([1, 2, 1])
with col_daily:
    st_echarts(options=options_daily, height="400px")

# =============================================================
# Table: RedStone Liquidations (collateral seized > $1)
# =============================================================
st.header("RedStone Liquidations (Collateral Seized > $1)")

redstone_liqs = l_2023[
    (l_2023["oev_provider"] == "RedStone") &
    (l_2023["total_coll_seized_usd"] > 1)
][["block_time", "tx_hash", "coll_tokens", "debt_tokens", "total_coll_seized_usd", "total_debt_repaid_usd", "oev_bid_usd"]].sort_values("block_time", ascending=False).copy()

redstone_liqs["tx_url"] = "https://bscscan.com/tx/" + redstone_liqs["tx_hash"]
redstone_liqs["block_time"] = pd.to_datetime(redstone_liqs["block_time"]).dt.strftime("%Y-%m-%d %H:%M")
redstone_liqs = redstone_liqs[["block_time", "tx_url", "coll_tokens", "debt_tokens", "total_coll_seized_usd", "total_debt_repaid_usd", "oev_bid_usd"]]

total_rs_coll = l_2023[
    (l_2023["oev_provider"] == "RedStone") &
    (l_2023["oev_to_collateral_ratio"].notna())
]["total_coll_seized_usd"].sum()

col1, col2 = st.columns(2)
col1.metric("Total RedStone Liquidations (coll > $1)", len(redstone_liqs))
col2.metric("Total Collateral Seized by RedStone", f"${total_rs_coll:,.2f}")

st.dataframe(
    redstone_liqs,
    column_config={
        "block_time": st.column_config.TextColumn("Block Time (UTC)"),
        "tx_url": st.column_config.LinkColumn(
            "Transaction",
            display_text="https://bscscan\\.com/tx/(.+)",
        ),
    },
    use_container_width=True,
)

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

cl_row = stats[stats["oev_provider"] == "Chainlink"].iloc[0]
rs_row = stats[stats["oev_provider"] == "RedStone"].iloc[0]

col_cl, col_rs = st.columns(2)
with col_cl:
    st.metric(
        "Chainlink — OEV Recapture Efficiency",
        f"{cl_row['oev_recapture_pct']:.2f}%",
        help="Share of the recapturable liquidation bonus (liquidation bonus minus the 5% Venus treasury fee) that was bid back via OEV.",
    )
with col_rs:
    st.metric(
        "RedStone — OEV Recapture Efficiency",
        f"{rs_row['oev_recapture_pct']:.2f}%",
        help="Share of the recapturable liquidation bonus (liquidation bonus minus the 5% Venus treasury fee) that was bid back via OEV.",
    )

st.divider()

def _usd(v): return f"${v:,.2f}"
def _pct(v): return f"{v:.3f}%"

comparison = pd.DataFrame({
    "Metric": [
        "Liquidation Count",
        "Total Collateral Liquidated",
        "Total Debt Repaid",
        "Total Liquidation Bonus",
        "└ Treasury Fee (5%, constant)",
        "└ Recapturable Bonus (solver share)",
        "Total OEV Recaptured",
        "Simulated LB % without OEV Solution",
        "Realized LB % with OEV Solution",
    ],
    "Chainlink": [
        int(cl_row["oev_liquidation_count"]),
        _usd(cl_row["total_collateral_liquidated_usd"]),
        _usd(cl_row["total_debt_repaid_usd"]),
        _usd(cl_row["total_actual_bonus_usd"]),
        _usd(cl_row["treasury_fee_usd"]),
        _usd(cl_row["recapturable_bonus_usd"]),
        _usd(cl_row["total_oev_usd"]),
        _pct(cl_row["realized_LB_pct_without_oev"]),
        _pct(cl_row["realized_LB_pct_with_oev"]),
    ],
    "RedStone": [
        int(rs_row["oev_liquidation_count"]),
        _usd(rs_row["total_collateral_liquidated_usd"]),
        _usd(rs_row["total_debt_repaid_usd"]),
        _usd(rs_row["total_actual_bonus_usd"]),
        _usd(rs_row["treasury_fee_usd"]),
        _usd(rs_row["recapturable_bonus_usd"]),
        _usd(rs_row["total_oev_usd"]),
        _pct(rs_row["realized_LB_pct_without_oev"]),
        _pct(rs_row["realized_LB_pct_with_oev"]),
    ],
}).set_index("Metric")

st.dataframe(comparison, use_container_width=True)

with st.expander("ℹ️ Metric definitions"):
    st.markdown("""
| Metric | Definition |
|---|---|
| **Liquidation Count** | Number of liquidation transactions attributed to this oracle provider |
| **Total Collateral Liquidated** | Sum of collateral seized across all liquidations (USD) |
| **Total Debt Repaid** | Sum of debt repaid by liquidators (USD) |
| **Total Liquidation Bonus** | Collateral seized − Debt repaid; the gross bonus received by liquidators |
| **Treasury Fee (5%, constant)** | Venus protocol retains 5% of debt repaid as a fixed protocol fee |
| **Recapturable Bonus (solver share)** | Liquidation Bonus − Treasury Fee; the portion a solver can bid back via OEV |
| **Total OEV Recaptured** | Sum of OEV bids paid back to the protocol (USD) |
| **Simulated LB % without OEV Solution** | Gross bonus as % of collateral, as if no OEV bids were made |
| **Realized LB % with OEV Solution** | Net bonus after deducting OEV bids, as % of collateral |
""")

# =============================================================
# OEV Coverage
# =============================================================
st.header("OEV Coverage")
st.caption("Coverage measures what share of eligible liquidation opportunities were actually captured via OEV provider.")

classified = oev_cov[
    (oev_cov["likely_cause_provider"].isin(["RedStone", "Chainlink"]))
    & (oev_cov["total_coll_seized_usd"] > 0.5)
].copy()

rs_captured = classified[
    (classified["likely_cause_provider"] == "RedStone")
    & (classified["oev_provider"] == "RedStone")
]
rs_missed = classified[
    (classified["likely_cause_provider"] == "RedStone")
    & (classified["oev_provider"] == "none")
]
rs_total = len(rs_captured) + len(rs_missed)
rs_capture_rate = len(rs_captured) / rs_total * 100 if rs_total > 0 else 0

col_rs, _ = st.columns(2)
with col_rs:
    st.metric(
        "RedStone — OEV Coverage",
        f"{rs_capture_rate:.1f}%",
        help="% of eligible liquidations (collateral > $0.50, oracle price = RedStone) that were captured via OEV.",
    )
    st.metric("Eligible Liquidations", rs_total)
    st.metric("Captured", f"{len(rs_captured)} (${rs_captured['total_coll_seized_usd'].sum():,.2f})")
    st.metric("Missed", f"{len(rs_missed)} (${rs_missed['total_coll_seized_usd'].sum():,.2f})")

# =============================================================
# Chart 3: Collateral Seized by Token (provider toggle)
# =============================================================
st.header("Total Collateral Seized by Token")

prov3 = st.radio("Provider", ["RedStone", "Chainlink"], index=0, horizontal=True, key="coll_token_toggle")

df_prov3 = l_2023[l_2023["oev_provider"] == prov3].copy()
rs_by_coll = df_prov3.groupby("coll_tokens")["total_coll_seized_usd"].sum().reset_index()
rs_by_coll = rs_by_coll[rs_by_coll["total_coll_seized_usd"] >= 5].sort_values("total_coll_seized_usd", ascending=False)
color3 = "#AE0822" if prov3 == "RedStone" else "#0847F7"

options3 = {
    "title": {"text": f"{prov3}: Total Collateral Seized by Token", "left": "center"},
    "tooltip": {"trigger": "axis"},
    "xAxis": {"type": "category", "data": rs_by_coll["coll_tokens"].tolist(), "axisLabel": {"rotate": 45}},
    "yAxis": {"type": "value", "axisLabel": {"formatter": "${value}"}},
    "series": [{
        "type": "bar",
        "data": [round(v, 2) for v in rs_by_coll["total_coll_seized_usd"].tolist()],
        "itemStyle": {"color": color3},
        "label": {"show": False},
    }],
}

_, col_c3, _ = st.columns([1, 2, 1])
with col_c3:
    st_echarts(options=options3, height="400px")
