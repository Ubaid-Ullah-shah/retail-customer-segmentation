"""Create a self-contained interactive retail dashboard from customer_segments.csv."""
from pathlib import Path
import json

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "processed" / "customer_segments.csv"
DESTINATION = ROOT / "outputs" / "retail_analytics_dashboard.html"


def main() -> None:
    if not SOURCE.exists():
        raise FileNotFoundError("Run src/run_segmentation.py before building the dashboard.")
    df = pd.read_csv(SOURCE)
    cols = ["HOUSEHOLD_KEY", "segment", "lifecycle_stage", "monetary_value", "frequency", "recency_days",
            "discount_share", "at_risk_score", "favorite_department", "department_breadth",
            "campaigns_received", "coupon_redemptions", "recommended_action"]
    rows = df[cols].round({"monetary_value": 2, "discount_share": 4, "at_risk_score": 1}).to_dict("records")
    dataset = json.dumps(rows, separators=(",", ":"))
    template = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Retail analytics | Customer segmentation</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
*{box-sizing:border-box}body{margin:0;background:#f5f7fb;color:#14213d;font:15px Arial,sans-serif}.wrap{max-width:1450px;margin:auto;padding:28px}h1{margin:0;font-size:28px}.sub{color:#60708b;margin:7px 0 23px}.toolbar{display:flex;gap:12px;align-items:center;margin:0 0 16px}select{padding:9px;border:1px solid #ccd5e1;border-radius:6px;background:white}.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}.card,.panel{background:white;border:1px solid #e3e9f1;border-radius:10px;padding:17px;box-shadow:0 1px 2px #14213d0d}.label{color:#60708b;font-size:12px;text-transform:uppercase;letter-spacing:.05em}.value{font-size:26px;font-weight:700;margin-top:8px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px}.chart{height:365px}.wide{grid-column:1/-1}.tablewrap{max-height:390px;overflow:auto}table{border-collapse:collapse;width:100%}th,td{padding:10px;text-align:left;border-bottom:1px solid #e8edf3}th{position:sticky;top:0;background:#fff;color:#60708b;font-size:12px}.note{font-size:12px;color:#60708b;margin-top:13px}@media(max-width:800px){.kpis,.grid{grid-template-columns:1fr}.wide{grid-column:auto}}
</style></head><body><main class="wrap"><h1>Retail analytics: customer segmentation</h1><p class="sub">Customer-level view of loyalty, inactivity risk, and discount reliance. At-risk is a behavioral proxy, not a confirmed churn event.</p>
<div class="toolbar"><label for="segment">Customer segment</label><select id="segment"><option value="all">All customers</option><option value="loyal">Loyal</option><option value="at_risk">At risk</option><option value="discount_dependent">Discount dependent</option><option value="regular">Regular</option></select></div>
<section class="kpis"><div class="card"><div class="label">Households</div><div class="value" id="households"></div></div><div class="card"><div class="label">Sales value</div><div class="value" id="sales"></div></div><div class="card"><div class="label">Average baskets</div><div class="value" id="baskets"></div></div><div class="card"><div class="label">Average risk score</div><div class="value" id="risk"></div></div></section>
<section class="grid"><div class="panel"><div id="segmentChart" class="chart"></div></div><div class="panel"><div id="riskChart" class="chart"></div></div><div class="panel"><div id="lifecycleChart" class="chart"></div></div><div class="panel"><div id="engagementChart" class="chart"></div></div><div class="panel wide"><div id="portfolioChart" class="chart"></div></div><div class="panel wide"><h2 style="margin-top:0;font-size:18px">Retention watchlist</h2><div class="tablewrap"><table><thead><tr><th>Household</th><th>Segment</th><th>Lifecycle</th><th>Sales value</th><th>Last-purchase gap</th><th>Risk</th><th>Department breadth</th><th>Campaigns</th><th>Coupons</th><th>Recommended action</th></tr></thead><tbody id="watchlist"></tbody></table></div><p class="note">Lifecycle is a behavioral status based on observed purchase activity. At-risk and dormant indicators are not confirmed churn events.</p></div></section></main>
<script>const data=__DATA__; const colors={loyal:'#246eb9',at_risk:'#d1495b',discount_dependent:'#e09f3e',regular:'#4c956c'};
const money=x=>new Intl.NumberFormat('en-US',{maximumFractionDigits:0}).format(x); const title=x=>x.replaceAll('_',' ').replace(/\\b\\w/g,c=>c.toUpperCase());
function render(){const selected=document.getElementById('segment').value;const d=selected==='all'?data:data.filter(x=>x.segment===selected);const sum=k=>d.reduce((a,x)=>a+(+x[k]||0),0);document.getElementById('households').textContent=money(d.length);document.getElementById('sales').textContent=money(sum('monetary_value'));document.getElementById('baskets').textContent=(sum('frequency')/d.length).toFixed(1);document.getElementById('risk').textContent=(sum('at_risk_score')/d.length).toFixed(1);
const segments=['loyal','at_risk','discount_dependent','regular']; const counts=segments.map(s=>d.filter(x=>x.segment===s).length);Plotly.react('segmentChart',[{x:segments.map(title),y:counts,type:'bar',marker:{color:segments.map(s=>colors[s])},hovertemplate:'%{x}: %{y:,} households<extra></extra>'}],{title:'Households by segment',margin:{t:48,l:55,r:20,b:80},yaxis:{title:'Households'},paper_bgcolor:'white',plot_bgcolor:'white'});
Plotly.react('riskChart',[{x:d.map(x=>x.at_risk_score),type:'histogram',nbinsx:20,marker:{color:'#d1495b'},hovertemplate:'Risk score: %{x}<br>Households: %{y}<extra></extra>'}],{title:'Distribution of at-risk score',margin:{t:48,l:55,r:20,b:50},xaxis:{title:'Risk score'},yaxis:{title:'Households'},paper_bgcolor:'white',plot_bgcolor:'white'});
const stages=['champion','active','declining','dormant'];const life=stages.map((s,i)=>({stage:s,count:d.filter(x=>x.lifecycle_stage===s).length,color:['#246eb9','#4c956c','#e09f3e','#d1495b'][i]})).filter(x=>x.count>0);Plotly.react('lifecycleChart',[{labels:life.map(x=>title(x.stage)),values:life.map(x=>x.count),type:'pie',hole:.55,marker:{colors:life.map(x=>x.color)},hovertemplate:'%{label}: %{value:,} households<extra></extra>'}],{title:'Customer lifecycle stage',margin:{t:48,l:20,r:20,b:20},paper_bgcolor:'white'});
Plotly.react('engagementChart',[{x:segments.map(title),y:segments.map(s=>d.filter(x=>x.segment===s).reduce((a,x)=>a+x.coupon_redemptions,0)),type:'bar',marker:{color:segments.map(s=>colors[s])},hovertemplate:'%{x}: %{y:,} coupon redemptions<extra></extra>'}],{title:'Coupon engagement by segment',margin:{t:48,l:55,r:20,b:80},yaxis:{title:'Coupon redemptions'},paper_bgcolor:'white',plot_bgcolor:'white'});
const traces=segments.map(s=>{const g=d.filter(x=>x.segment===s);return{x:g.map(x=>x.frequency),y:g.map(x=>x.monetary_value),text:g.map(x=>'Household: '+x.HOUSEHOLD_KEY+'<br>Discount share: '+(x.discount_share*100).toFixed(1)+'%'),mode:'markers',name:title(s),marker:{size:g.map(x=>7+x.discount_share*20),color:colors[s],opacity:.62},hovertemplate:'%{text}<br>Baskets: %{x}<br>Sales: %{y:,.0f}<extra></extra>'}});Plotly.react('portfolioChart',traces,{title:'Customer portfolio: purchase frequency and sales value',margin:{t:48,l:70,r:20,b:60},xaxis:{title:'Distinct baskets'},yaxis:{title:'Sales value'},paper_bgcolor:'white',plot_bgcolor:'white'});
document.getElementById('watchlist').innerHTML=[...d].sort((a,b)=>b.at_risk_score-a.at_risk_score||b.monetary_value-a.monetary_value).slice(0,50).map(x=>`<tr><td>${x.HOUSEHOLD_KEY}</td><td>${title(x.segment)}</td><td>${title(x.lifecycle_stage)}</td><td>${money(x.monetary_value)}</td><td>${x.recency_days} days</td><td>${x.at_risk_score}</td><td>${x.department_breadth}</td><td>${x.campaigns_received}</td><td>${x.coupon_redemptions}</td><td>${x.recommended_action}</td></tr>`).join('');}
document.getElementById('segment').addEventListener('change',render);render();</script></body></html>'''
    DESTINATION.write_text(template.replace("__DATA__", dataset), encoding="utf-8")
    print(f"Dashboard created: {DESTINATION}")


if __name__ == "__main__":
    main()
