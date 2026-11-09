# Retail Analytics & Customer Segmentation

This project uses Dunnhumby **The Complete Journey** to identify valuable customers, customers at risk of becoming inactive, and customers whose shopping is strongly discount-led.

## Business questions

1. Which households are the most loyal and valuable?
2. Which active households show early signs of churn?
3. Which households only purchase when promotions or coupons are available?
4. Which product departments and campaigns should be used to retain each group?

The unit of analysis is **one household**. The source data does not contain a true cancellation event, so `at_risk` is a behavioral proxy for inactivity, not a confirmed churn label.

## Project structure

```
data/raw/                 # Kaggle CSVs (not committed)
data/processed/           # Generated customer tables
outputs/                  # Generated charts and segment summaries
src/run_segmentation.py   # Reproducible feature engineering + segmentation
sql/customer_features.sql # SQL version of the central analytical model
requirements.txt
```

## 1. Put the data in place

Extract the Kaggle download and copy these files into `data/raw/` (keep the original names):

| File | Used for |
|---|---|
| `transaction_data.csv` | Purchases, baskets, dates, discounts, sales |
| `product.csv` | Department/category preferences |
| `household_demographics.csv` | Optional segment profiling |
| `campaign_table.csv` | Campaign exposure |
| `campaign_desc.csv` | Campaign metadata |
| `coupon.csv`, `coupon_redempt.csv` | Coupon behavior (optional extension) |
| `causal_data.csv` | Promotion/campaign attribution extension |

Only `transaction_data.csv` is required for the first pipeline run. `product.csv` enriches the output with favorite departments.

## 2. Set up and run

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python src/run_segmentation.py
python src/build_dashboard.py
```

The script writes:

- `data/processed/customer_features.csv` — feature table at household grain.
- `data/processed/customer_segments.csv` — scores, labels, and recommended actions.
- `outputs/segment_summary.csv` — segment counts, revenue, discount reliance, and basket behavior.
- `outputs/segment_demographic_profiles.csv` — demographic profile by segment.
- `outputs/department_segment_affinity.csv` — department spend and customer reach by segment.
- `outputs/customer_segments.png` — portfolio chart for presentation or a dashboard.
- `outputs/retail_analytics_dashboard.html` — ready-to-open interactive dashboard; open it in Chrome or Edge.

## Segment definitions

All scores use the full observed transaction history. `analysis_end_day` is the maximum `DAY` in the file, so recency is measured consistently even though calendar dates are absent.

| Segment | Operational rule | Recommended action |
|---|---|---|
| `loyal` | Top 25% of monetary value and frequency, with recent activity (recency at or below 40th percentile) | Retain with personalized cross-sell, early access, and rewards—not blanket discounts. |
| `at_risk` | Long recency, or a high composite risk score from recency, falling recent spend/frequency, and low engagement | Send a time-limited win-back offer; test value-led versus discount-led messaging. |
| `discount_dependent` | Discount share at or above 35% of gross basket value and at least three baskets | Use targeted promotions; measure incrementality and margin before expanding offers. |
| `regular` | Does not meet the above rules | Develop with relevant category recommendations and loyalty enrollment. |

Segment assignment is hierarchical: **loyal → at_risk → discount_dependent → regular**. This prevents a high-value loyal customer who uses some discounts from being put in a purely price-sensitive bucket. The raw flags remain in the output so you can build overlapping audiences if desired.

## Key metrics

- **Recency:** days from a household’s last purchase to the final observed day.
- **Frequency:** distinct baskets per household.
- **Monetary value:** `SALES_VALUE` summed per household; report it as dataset monetary units unless the data dictionary confirms currency.
- **Gross basket value:** sales plus absolute discounts, used only to calculate discount share.
- **Discount share:** absolute retail + coupon discounts / gross basket value.
- **Recent spend change:** last 13 observed weeks compared with the preceding 13 weeks. New or immature households are labelled `NA`, not treated as declining.
- **At-risk score:** a transparent 0–100 proxy combining recency (50%), spend decline (25%), and frequency decline (25%).

## Dashboard specification

Build this in Power BI, Tableau, or Streamlit from `customer_segments.csv` and the transaction tables.

1. **Executive overview:** households, sales, average baskets, segment distribution, and at-risk value.
2. **Customer map:** scatter plot of frequency vs. monetary value; color by segment and size by discount share.
3. **Retention watchlist:** at-risk households sorted by at-risk score; show last purchase day, lost recent spend, favorite department, and action.
4. **Promotion behavior:** discount share by segment and department; compare sales with discount intensity.
5. **Category and campaign view:** department affinity by segment; campaign exposure and coupon redemption as a later extension.

The enhanced customer table also includes lifecycle stage (`champion`, `active`, `declining`, or `dormant`), department and commodity breadth, campaign exposure, and coupon-redemption counts. These are descriptive behavioral features; campaign exposure and redemption must not be presented as campaign-caused sales lift.

Use slicers for department, week, demographic attributes, campaign type, and segment. Do not imply a campaign caused retention without a controlled comparison.

## Suggested analysis narrative

Start with the segment counts and revenue contribution. Then quantify whether at-risk households represent material historical value, and whether discount-dependent customers have lower net value after promotions. Finally, recommend one retention experiment per segment, with holdout groups and a 13-week post-campaign measurement window.

## Validation checks before presenting results

- Check that `BASKET_ID` is not duplicated unexpectedly at the transaction-line grain.
- Check negative/zero quantities and monetary values; the pipeline excludes returns from aggregate sales features but reports their count.
- Confirm whether `SALES_VALUE` is net sales in the supplied data dictionary before calling it revenue or profit.
- Keep the final 13 weeks out of any future churn-model training labels to avoid look-ahead bias.
- Compare segment sizes and sales totals back to raw data after every filter or join.

## Moving from rules to machine learning

After the rules-based version is accepted, create a time-based label: a household is `churned=1` if it makes no purchase during a future 13-week observation window. Train only on features available before the scoring date (RFM, discount share, category breadth, campaign exposure). Use time-based train/validation splits, class weights, precision/recall and lift—not accuracy alone. Keep a rule-based version because it is easier for stakeholders to understand and audit.
