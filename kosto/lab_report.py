"""Portable evidence report: metrics are shown only when a completed trial exists."""
import html


def render(status,audit=None):
    e=lambda x:html.escape(str(x if x is not None else '待測'))
    def pct(v):return f'{v:+.1%}' if v is not None else '待測'
    rows=''
    for h,name in [('short','短線'),('mid','中線'),('long','長線')]:
        seal=status['champions'].get(h) or {};m=seal.get('metric',{})
        rows+='<tr>'+''.join('<td>'+e(x)+'</td>' for x in [name,pct(m.get('cagr')),pct(m.get('bench_cagr')),pct(m.get('mdd')),'可採用' if seal.get('deployable') else '研究候選' if seal else '尚未驗效'])+'</tr>'
    trials=''
    for r in status.get('trials',[]):
        m=r.get('metric',{});p=r['recipe'];trials+='<tr>'+''.join('<td>'+e(x)+'</td>' for x in [p['horizon'],p['id'],p['rule']+str(p['size']),pct(m.get('cagr')),pct(m.get('mdd')),pct(m.get('stress_excess')),r.get('error') or '完成'])+'</tr>'
    limits=''.join('<li>'+e(x)+'</li>' for x in status['limitations'])
    evidence='<p>本次尚無本版完成的投資績效試驗；以下數值保持待測。</p>' if not status['trial_count'] else '<p>開發期只用於選型，保留期評估已鎖定的冠軍；兩者分開列示。</p>'
    audit_text=''
    if audit:audit_text='<p>快照初篩 '+e(audit['data']['股票數'])+'檔，平均因子涵蓋 '+f"{audit['quality']['coverage']:.0%}"+'。這是資料檢核，不能當成投資驗效。</p>'
    if status.get('readiness',{}).get('synthetic'):audit_text='<p style="background:#fff2ce;padding:15px">合成資料｜僅驗證程式流程，以下數字不是真實投資績效。</p>'+audit_text
    if status.get('attachment_review'):
        a=status['attachment_review'];audit_text='<h2>附檔驗證效果核對</h2><p>'+e(a['finding'])+'</p>'+audit_text
    return '''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>V29 策略驗效與優化報告</title><style>body{margin:0;background:#edf3f7;color:#172f43;font:15px/1.85 -apple-system,BlinkMacSystemFont,"PingFang TC",sans-serif}main{max-width:1080px;background:white;margin:30px auto;padding:38px;border-radius:18px}h1{font-size:30px}h2{font-size:20px;margin-top:30px}.lead{padding:22px;border-left:4px solid #087f76;background:#edf8f4}.scroll{overflow:auto}table{width:100%;border-collapse:collapse;white-space:nowrap;font-size:13px}td,th{padding:12px;text-align:left;border-bottom:1px solid #e4ecf1}th{background:#f5f8fa;color:#637f90}small{color:#748c9c}button{background:#087f76;border:0;color:white;padding:12px 18px;border-radius:8px}@media(max-width:600px){main{padding:22px 16px;margin:0;border-radius:0}h1{font-size:25px}}@media print{main{margin:0;padding:0}button{display:none}}</style></head><body><main><small>ALPHA RADAR / V29 STRATEGY LAB</small><h1>策略驗效與持續優化報告</h1><small>'''+e(status['generated_at'])+'</small><div class="lead"><b>'+e(status['status'])+'</b>'+evidence+'</div>'+audit_text+f'''
<h2>一、目前驗證效果</h2><div class="scroll"><table><tr><th>週期</th><th>保留期年化</th><th>同期0050</th><th>最大回撤</th><th>結論</th></tr>{rows}</table></div><p>本次已完成候選試驗 {status['trial_count']} 次。程式測試與資料檢核不計入投資試驗。</p>
<h2>二、研究目標與選型規則</h2><p>{e(status['objective'])}。預先列出母池、因子數、融合比例、續抱門檻與剩餘資金配置。每次訓練只用當時已成熟標籤。開發期至少250個交易日；至少三個區段、區段勝率至少50%、最大回撤不超過45%、來回額外0.5%成本下仍有正超額，才可列冠軍。</p><p>上述門檻是預先設定的研究條件，並非普遍最佳參數；需要在新資料與可交易限制下持續確認。</p>
<h2>三、保留期與正式採用</h2><p>冠軍依開發期選定，保留期只檢查一次並鎖定；失敗不改用同一保留期輪流試其他冠軍。正式採用另需非合成資料、足夠保留期及PIT、歷史名冊、企業行動證據。證據不足仍列研究候選。</p>
<h2>四、完整候選紀錄</h2><div class="scroll"><table><tr><th>週期</th><th>候選</th><th>母池</th><th>開發期年化</th><th>回撤</th><th>成本壓力超額</th><th>狀態</th></tr>{trials or '<tr><td colspan="7">尚無完成試驗</td></tr>'}</table></div>
<h2>五、持續研究與限制</h2><ul>{limits}</ul><p>背景資料建置與研究均可續跑；試驗結果保存在SQLite紀錄。新資料、新模型設定會建立可辨識研究批次，不覆蓋原有試驗結果。研究區提供因子IC／ICIR、成本後淨值、逐區段比較與歷次權重。</p><button onclick="print()">列印／另存PDF</button></main></body></html>'''
