import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

st.set_page_config(page_title="RedStone Atom: Venus OEV Analysis", layout="wide")
st.title("RedStone Atom: Venus OEV Analysis")
st.markdown("*Analysis covers liquidations from 7 February 2026 00:00 CET onwards.*")


@st.cache_data
def load_data():
    df = pd.read_csv("venus_streamlit.csv")
    return df


l_2023 = load_data()

# --- Shared filtering ---
df_filtered = l_2023[
    (l_2023["oev_provider"].isin(["Chainlink", "RedStone"]))
    & (l_2023["oev_to_collateral_ratio"].notna())
].copy()
df_filtered["date"] = pd.to_datetime(df_filtered["block_time"]).dt.date

colors = {"Chainlink": "blue", "RedStone": "red"}

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

fig1, ax1 = plt.subplots(figsize=(9, 6))
bar_colors = [colors[p] for p in overall_avg["oev_provider"]]

bars1 = ax1.bar(
    overall_avg["oev_provider"],
    overall_avg["weighted_avg_ratio_pct"],
    color=bar_colors,
    alpha=0.8,
    width=0.5,
)

for bar in bars1:
    height = bar.get_height()
    ax1.text(
        bar.get_x() + bar.get_width() / 2.0,
        height,
        f"{height:.3f}%",
        ha="center",
        va="bottom",
        fontsize=12,
        fontweight="bold",
    )

ax1.set_xlabel("OEV Provider", fontsize=12)
ax1.set_ylabel("Dollar-Weighted Avg OEV to Collateral Ratio (%)", fontsize=12)
ax1.set_title(
    "Overall Dollar-Weighted Average OEV/Collateral Ratio by Provider",
    fontsize=14,
    fontweight="bold",
)
ax1.grid(True, alpha=0.3, axis="y")
ax1.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y:.2f}%"))
fig1.tight_layout()

_, col_c1, _ = st.columns([1, 2, 1])
with col_c1:
    st.pyplot(fig1)

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
# Chart 2: RedStone Collateral Seized by Token
# =============================================================
st.header("RedStone: Total Collateral Seized by Token")

df_rs = l_2023[l_2023["oev_provider"] == "RedStone"].copy()
rs_by_coll = df_rs.groupby("coll_tokens")["total_coll_seized_usd"].sum().reset_index()
rs_by_coll = rs_by_coll[rs_by_coll["total_coll_seized_usd"] >= 5].sort_values("total_coll_seized_usd", ascending=False)

fig2, ax2 = plt.subplots(figsize=(8, 4))

ax2.bar(rs_by_coll["coll_tokens"], rs_by_coll["total_coll_seized_usd"], color="red", alpha=0.8)

ax2.set_xlabel("Collateral Token", fontsize=12)
ax2.set_ylabel("Total Collateral Seized (USD)", fontsize=12)
ax2.set_title("RedStone: Total Collateral Seized by Token", fontsize=14, fontweight="bold")
ax2.grid(True, alpha=0.3, axis="y")
ax2.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"${y:,.0f}"))
plt.sca(ax2)
plt.xticks(rotation=45, ha="right")
fig2.tight_layout()

_, col_c2, _ = st.columns([1, 2, 1])
with col_c2:
    st.pyplot(fig2)

# =============================================================
# Chart 3: OEV Recapture Efficiency (Venus 5% treasury adjusted)
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
        st.metric("Realized LB % without OEV Solution", f"{row['realized_LB_pct_without_oev']:.3f}%")
        st.metric("Realized LB % with OEV Solution", f"{row['realized_LB_pct_with_oev']:.3f}%")

st.divider()

fig3, ax3 = plt.subplots(figsize=(6, 4))
bar_colors3 = [colors[p] for p in stats["oev_provider"]]

bars3 = ax3.bar(stats["oev_provider"], stats["oev_recapture_pct"], color=bar_colors3, alpha=0.8, width=0.5)

for bar in bars3:
    height = bar.get_height()
    ax3.text(
        bar.get_x() + bar.get_width() / 2.0,
        height,
        f"{height:.2f}%",
        ha="center",
        va="bottom",
        fontsize=12,
        fontweight="bold",
    )

ax3.set_ylim(0, 100)
ax3.set_xlabel("OEV Provider", fontsize=12)
ax3.set_ylabel("OEV Recapture Efficiency (%)", fontsize=12)
ax3.set_title("OEV Recapture Efficiency by Provider", fontsize=14, fontweight="bold")
ax3.grid(True, alpha=0.3, axis="y")
ax3.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y:.0f}%"))
fig3.tight_layout()

_, col_c3, _ = st.columns([1, 2, 1])
with col_c3:
    st.pyplot(fig3)
