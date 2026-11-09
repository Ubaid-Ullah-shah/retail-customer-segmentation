"""Build household-level retail features and transparent customer segments.

Run from the project root: python src/run_segmentation.py
"""
import os
from pathlib import Path

# Some managed Windows profiles prevent Matplotlib from writing to its default
# user cache. Keep its generated cache inside this project instead.
ROOT = Path(__file__).resolve().parents[1]
MPL_CACHE = ROOT / ".matplotlib"
MPL_CACHE.mkdir(exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPL_CACHE))

import matplotlib
matplotlib.use("Agg")  # Generate PNGs without requiring a desktop GUI/Tk install.
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
OUTPUTS = ROOT / "outputs"


def first_existing(*names: str) -> Path | None:
    for name in names:
        candidate = RAW / name
        if candidate.exists():
            return candidate
    return None


def qcut_or_rank(series: pd.Series, q: int = 4) -> pd.Series:
    """Stable quartiles even when many customers have equal values."""
    return pd.qcut(series.rank(method="first"), q=q, labels=False, duplicates="drop") + 1


def main() -> None:
    transactions_path = first_existing("transaction_data.csv", "transaction_data.csv.zip")
    if transactions_path is None:
        raise FileNotFoundError(
            "Add transaction_data.csv from The Complete Journey to data/raw/ and run again."
        )

    PROCESSED.mkdir(parents=True, exist_ok=True)
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    tx = pd.read_csv(transactions_path, low_memory=False)
    tx.columns = tx.columns.str.upper().str.strip()
    required = {"HOUSEHOLD_KEY", "BASKET_ID", "DAY", "SALES_VALUE"}
    missing = required - set(tx.columns)
    if missing:
        raise ValueError(f"transaction_data.csv is missing columns: {sorted(missing)}")

    # The source is transaction-line grain. Do not deduplicate lines: different products
    # can legitimately appear in the same basket.
    for col in ["SALES_VALUE", "RETAIL_DISC", "COUPON_DISC", "COUPON_MATCH_DISC", "QUANTITY"]:
        if col not in tx:
            tx[col] = 0.0
        tx[col] = pd.to_numeric(tx[col], errors="coerce").fillna(0.0)
    tx["DAY"] = pd.to_numeric(tx["DAY"], errors="coerce")
    tx = tx.dropna(subset=["HOUSEHOLD_KEY", "BASKET_ID", "DAY"]).copy()
    tx["TOTAL_DISCOUNT"] = tx[["RETAIL_DISC", "COUPON_DISC", "COUPON_MATCH_DISC"]].abs().sum(axis=1)
    tx["GROSS_VALUE"] = tx["SALES_VALUE"].clip(lower=0) + tx["TOTAL_DISCOUNT"]
    tx["WEEK_INDEX"] = np.floor(tx["DAY"] / 7).astype(int)
    analysis_end_day = int(tx["DAY"].max())
    cutoff_week = int(tx["WEEK_INDEX"].max()) - 13

    # Returns and zero-value lines are retained in source auditing but excluded from
    # spend and discount-dependence totals to avoid treating refunds as shopping.
    purchase = tx.loc[tx["SALES_VALUE"] > 0].copy()
    base = purchase.groupby("HOUSEHOLD_KEY").agg(
        first_day=("DAY", "min"),
        last_day=("DAY", "max"),
        frequency=("BASKET_ID", "nunique"),
        monetary_value=("SALES_VALUE", "sum"),
        total_discount=("TOTAL_DISCOUNT", "sum"),
        gross_value=("GROSS_VALUE", "sum"),
        total_units=("QUANTITY", "sum"),
        active_weeks=("WEEK_INDEX", "nunique"),
    )
    base["recency_days"] = analysis_end_day - base["last_day"]
    base["avg_basket_value"] = base["monetary_value"] / base["frequency"]
    base["discount_share"] = np.where(
        base["gross_value"] > 0, base["total_discount"] / base["gross_value"], 0
    )

    recent = purchase.assign(period=np.where(purchase["WEEK_INDEX"] > cutoff_week, "recent", "prior"))
    period = recent.groupby(["HOUSEHOLD_KEY", "period"]).agg(
        sales=("SALES_VALUE", "sum"), baskets=("BASKET_ID", "nunique")
    ).unstack(fill_value=0)
    period.columns = [f"{metric}_{period_name}" for metric, period_name in period.columns]
    base = base.join(period, how="left").fillna({"sales_recent": 0, "sales_prior": 0, "baskets_recent": 0, "baskets_prior": 0})
    base["spend_change"] = np.where(
        base["sales_prior"] > 0, (base["sales_recent"] - base["sales_prior"]) / base["sales_prior"], np.nan
    )
    base["frequency_change"] = np.where(
        base["baskets_prior"] > 0,
        (base["baskets_recent"] - base["baskets_prior"]) / base["baskets_prior"], np.nan,
    )

    product_path = first_existing("product.csv")
    if product_path is not None and "PRODUCT_ID" in purchase:
        product = pd.read_csv(product_path, low_memory=False)
        product.columns = product.columns.str.upper().str.strip()
        if {"PRODUCT_ID", "DEPARTMENT"}.issubset(product.columns):
            dept = purchase.merge(product[["PRODUCT_ID", "DEPARTMENT"]], on="PRODUCT_ID", how="left")
            dept_sales = dept.groupby(["HOUSEHOLD_KEY", "DEPARTMENT"], dropna=False)["SALES_VALUE"].sum()
            favorite_dept = dept_sales.groupby(level=0).idxmax().str[1].rename("favorite_department")
            base = base.join(favorite_dept)
            category_breadth = dept.groupby("HOUSEHOLD_KEY")["DEPARTMENT"].nunique().rename("department_breadth")
            commodity_breadth = dept.groupby("HOUSEHOLD_KEY")["COMMODITY_DESC"].nunique().rename("commodity_breadth") if "COMMODITY_DESC" in dept else None
            base = base.join(category_breadth)
            if commodity_breadth is not None:
                base = base.join(commodity_breadth)
    if "favorite_department" not in base:
        base["favorite_department"] = "Unknown"
    for col in ["department_breadth", "commodity_breadth"]:
        if col not in base:
            base[col] = 0
        base[col] = base[col].fillna(0).astype(int)

    # Enrich from optional household, campaign, and coupon source files. These joins
    # retain every purchasing household, including households without a profile/event.
    demographics_path = first_existing("hh_demographic.csv", "household_demographics.csv")
    if demographics_path is not None:
        demographics = pd.read_csv(demographics_path, low_memory=False)
        demographics.columns = demographics.columns.str.upper().str.strip()
        if "HOUSEHOLD_KEY" in demographics:
            base = base.join(demographics.drop_duplicates("HOUSEHOLD_KEY").set_index("HOUSEHOLD_KEY"), how="left")
    campaign_path = first_existing("campaign_table.csv")
    if campaign_path is not None:
        campaigns = pd.read_csv(campaign_path, low_memory=False)
        campaigns.columns = campaigns.columns.str.upper().str.strip()
        if "HOUSEHOLD_KEY" in campaigns:
            campaign_features = campaigns.groupby("HOUSEHOLD_KEY").agg(
                campaigns_received=("CAMPAIGN", "nunique"),
                campaign_types=("DESCRIPTION", "nunique"),
            )
            base = base.join(campaign_features, how="left")
    redemption_path = first_existing("coupon_redempt.csv")
    if redemption_path is not None:
        redemptions = pd.read_csv(redemption_path, low_memory=False)
        redemptions.columns = redemptions.columns.str.upper().str.strip()
        if "HOUSEHOLD_KEY" in redemptions:
            redemption_features = redemptions.groupby("HOUSEHOLD_KEY").agg(
                coupon_redemptions=("COUPON_UPC", "count"),
                redeemed_campaigns=("CAMPAIGN", "nunique"),
            )
            base = base.join(redemption_features, how="left")
    for col in ["campaigns_received", "campaign_types", "coupon_redemptions", "redeemed_campaigns"]:
        if col not in base:
            base[col] = 0
        base[col] = base[col].fillna(0).astype(int)

    base["recency_quartile"] = qcut_or_rank(base["recency_days"])
    base["frequency_quartile"] = qcut_or_rank(base["frequency"])
    base["monetary_quartile"] = qcut_or_rank(base["monetary_value"])
    recency_risk = base["recency_days"].rank(pct=True) * 100
    spend_decline_risk = (-base["spend_change"].fillna(0).clip(-1, 1) * 100).clip(lower=0)
    frequency_decline_risk = (-base["frequency_change"].fillna(0).clip(-1, 1) * 100).clip(lower=0)
    base["at_risk_score"] = (0.50 * recency_risk + 0.25 * spend_decline_risk + 0.25 * frequency_decline_risk).round(1)

    loyal = (
        (base["monetary_quartile"] == base["monetary_quartile"].max())
        & (base["frequency_quartile"] == base["frequency_quartile"].max())
        & (base["recency_days"] <= base["recency_days"].quantile(0.40))
    )
    at_risk = (base["recency_days"] >= base["recency_days"].quantile(0.75)) | (base["at_risk_score"] >= 70)
    discount_dependent = (base["discount_share"] >= 0.35) & (base["frequency"] >= 3)
    base["is_loyal"] = loyal
    base["is_at_risk"] = at_risk
    base["is_discount_dependent"] = discount_dependent
    base["segment"] = np.select(
        [loyal, at_risk, discount_dependent],
        ["loyal", "at_risk", "discount_dependent"],
        default="regular",
    )
    base["lifecycle_stage"] = np.select(
        [loyal, at_risk, base["at_risk_score"] >= 60],
        ["champion", "dormant", "declining"],
        default="active",
    )
    actions = {
        "loyal": "Cross-sell and reward; do not default to discounts.",
        "at_risk": "Test a time-limited win-back message with a holdout group.",
        "discount_dependent": "Target promotions selectively and monitor incremental margin.",
        "regular": "Develop with relevant category recommendations and loyalty enrollment.",
    }
    base["recommended_action"] = base["segment"].map(actions)
    base["analysis_end_day"] = analysis_end_day
    base = base.reset_index().sort_values(["segment", "at_risk_score", "monetary_value"], ascending=[True, False, False])
    base.to_csv(PROCESSED / "customer_features.csv", index=False)
    base.to_csv(PROCESSED / "customer_segments.csv", index=False)

    summary = base.groupby("segment").agg(
        households=("HOUSEHOLD_KEY", "nunique"),
        total_sales_value=("monetary_value", "sum"),
        average_sales_value=("monetary_value", "mean"),
        average_baskets=("frequency", "mean"),
        average_recency_days=("recency_days", "mean"),
        average_discount_share=("discount_share", "mean"),
        average_risk_score=("at_risk_score", "mean"),
    ).reset_index()
    summary.to_csv(OUTPUTS / "segment_summary.csv", index=False)

    # Dashboard-ready supporting tables at the appropriate grain.
    profile_columns = [c for c in ["AGE_DESC", "INCOME_DESC", "HOMEOWNER_DESC", "HH_COMP_DESC"] if c in base]
    if profile_columns:
        profiles = base.groupby(["segment", *profile_columns], dropna=False).agg(
            households=("HOUSEHOLD_KEY", "nunique"),
            total_sales_value=("monetary_value", "sum"),
            average_risk_score=("at_risk_score", "mean"),
        ).reset_index()
        profiles.to_csv(OUTPUTS / "segment_demographic_profiles.csv", index=False)
    if product_path is not None and "PRODUCT_ID" in purchase and "DEPARTMENT" in product:
        department_segment = purchase.merge(product[["PRODUCT_ID", "DEPARTMENT"]], on="PRODUCT_ID", how="left").merge(
            base[["HOUSEHOLD_KEY", "segment"]], on="HOUSEHOLD_KEY", how="left"
        ).groupby(["segment", "DEPARTMENT"], dropna=False).agg(
            sales_value=("SALES_VALUE", "sum"), households=("HOUSEHOLD_KEY", "nunique")
        ).reset_index()
        department_segment.to_csv(OUTPUTS / "department_segment_affinity.csv", index=False)

    plot_data = base.sample(min(len(base), 8000), random_state=42)
    fig, ax = plt.subplots(figsize=(11, 7))
    ax.set_facecolor("#f7f7f7")
    colors = {"loyal": "#246eb9", "at_risk": "#d1495b", "discount_dependent": "#e09f3e", "regular": "#4c956c"}
    for segment, group in plot_data.groupby("segment"):
        sizes = 15 + (group["discount_share"].clip(0, 1) * 165)
        ax.scatter(group["frequency"], group["monetary_value"], s=sizes, alpha=0.65,
                   label=segment.replace("_", " ").title(), color=colors[segment], edgecolors="none")
    ax.set_title("Customer portfolio: frequency, purchase value, and discount reliance")
    ax.set_xlabel("Distinct baskets")
    ax.set_ylabel("Sales value (dataset units)")
    ax.set_ylim(bottom=0)
    ax.legend(title="Segment")
    fig.tight_layout()
    fig.savefig(OUTPUTS / "customer_segments.png", dpi=180)
    print(f"Processed {len(tx):,} transaction lines and created {len(base):,} household segments.")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
