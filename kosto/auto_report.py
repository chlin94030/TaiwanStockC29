"""Research output for the independent V28 rules; no inherited performance claim."""
from __future__ import annotations
import html,json
from .auto_market import NAMES,WEIGHTS


def render(record):
    esc=lambda x:html.escape(str(x))
    d=record['data'];quality=record['quality'];table=''
    for factor,name in NAMES.items():
        table+='<tr><td>'+esc(name)+'</td>'+''.join(f'<td>{WEIGHTS[h][factor]:.0%}</td>' for h in WEIGHTS)+'</tr>'
    limits=''.join('<li>'+esc(x)+'</li>' for x in record['limitations'])
    sources=''.join('<tr><td>'+esc(x['dataset'])+'</td><td>'+esc(x.get('date',x.get('retrieved_at','')))+'</td><td>'+esc(x.get('rows',''))+'</td></tr>' for x in quality['sources'])
    return '''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Alpha Radar V28 研究報告</title><style>*{box-sizing:border-box}body{margin:0;background:#f2f6f8;color:#182f42;font:15px/1.85 -apple-system,BlinkMacSystemFont,"PingFang TC",sans-serif}main{max-width:980px;margin:30px auto;background:white;border:1px solid #dae5ec;border-radius:18px;padding:40px}small{color:#6c8392}h1{font-size:30px}h2{font-size:20px;margin-top:30px}.verdict{background:#edf8f4;border-left:4px solid #087f76;padding:22px;border-radius:8px}.scroll{overflow:auto}table{width:100%;border-collapse:collapse;white-space:nowrap;font-size:13px}td,th{padding:11px;text-align:left;border-bottom:1px solid #e2eaf0}th{color:#647d8e;background:#f7fafb}li{margin:7px 0}button{background:#087f76;color:white;border:0;border-radius:8px;padding:12px 16px}@media(max-width:600px){main{margin:0;padding:22px 18px;border:0;border-radius:0}h1{font-size:25px}}@media print{main{margin:0;border:0;padding:0}button{display:none}}</style></head><body><main><small>ALPHA RADAR PRO / V28 AUTO</small><h1>獨立選股模型研究報告</h1><small>'''+esc(record['generated_at'])+'</small><div class="verdict"><b>'+esc(record['conclusion'])+'</b><p>'+esc(record['note'])+'</p></div>'+f'''
<h2>一、產品與研究設計</h2><p>應用程式開啟即讀取隨附的真實市場快照，在背景自動刷新整批行情、營收、估值與可用籌碼。歷史K線逐步補齊，無須匯入資料或等全市場多年研究完成。</p><p>快照資料範圍：{esc(d['訊號起日'])}～{esc(d['訊號迄日'])}，實際初篩{d['股票數']}檔。僅納入四碼普通股、價格至少10元、日成交金額至少2,000萬元。未取得市場不視為已掃描。</p>
<h2>二、獨立模型因子與權重</h2><p>已觀測因子以母池相對百分位計分；估值與淨利率在有足夠同產業公司時依產業比較。缺失因子取中性50分，保留原權重並降低涵蓋率，涵蓋率至少50%才列入初選觀察，並非可直接進場。分數不等於勝率。</p><div class="scroll"><table><tr><th>面向</th><th>短線</th><th>中線</th><th>長線</th></tr>{table}</table></div><p>短／中／長相對強勢分別至少需要6／21／61根實際收盤資料；趨勢分別需20／60／120根。獲利品質採實際財報淨利率；未取得時保持中性並降低涵蓋率。</p>
<h2>三、更新與執行</h2><p>盤中以5秒排程讀取伺服器共享報價，請求在背景執行，避免每位訪客各自重抓行情。保留實際成交時間、逾時判斷與失敗狀態。5秒排程不代表交易所必定每5秒有新成交。盤後停止行情請求，保留模型推薦。</p><p>具有至少60根真實OHLC且模型及報價日期有效時，才顯示技術買區與可分批布局；歷史未齊則顯示價格待確認。較舊快照維持觀察狀態。資金配置中0050可為0%。</p>
<h2>四、驗證狀態</h2><p>目前完成資料日期、欄位、流動性、缺值與來源檢核。完整投資績效仍待以當時可得的歷史營收、財報及價格資料進行時序驗證；不把當日因子倒填歷史，不延用舊模型的報酬數字。年化報酬、最大回撤與勝率均為待驗證。</p>
<h2>五、來源與限制</h2><div class="scroll"><table><tr><th>資料</th><th>取得時間／資料日</th><th>筆數</th></tr>{sources}</table></div><ul>{limits}</ul><p><small>資料識別 {esc(d['資料識別'])}</small></p><button onclick="print()">列印／另存PDF</button></main></body></html>'''
