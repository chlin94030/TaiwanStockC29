"""One research record shared by the validation screen and portable HTML report."""
from __future__ import annotations
import hashlib,html,json
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
from .desk_plan import HZ
from .ten_dimension import PRIORS,BLEND

WINDOWS={'dev':'開發期樣本外','holdout':'保留期','oos':'全期樣本外'}


def bundle_identity(B):
    cached=B.meta.get('_validation_data_id')
    if cached:return cached
    digest=hashlib.sha256()
    meta={k:B.meta.get(k) for k in ('tickers','factors','sig_dates','days','sig_pos','rules','synthetic')}
    digest.update(json.dumps(meta,sort_keys=True,default=str).encode())
    for key in sorted(B.a):
        if key=='SECTOR':continue  # Research derives this array after loading.
        arr=np.ascontiguousarray(B.a[key]);digest.update(key.encode());digest.update(str((arr.shape,arr.dtype)).encode())
        digest.update(memoryview(arr).cast('B'))
    identity=digest.hexdigest();B.meta['_validation_data_id']=identity
    return identity


def recipe_identity(cfg):
    value={k:cfg.get(k) for k in ('research','horizons','costs','kostolany','pools','desk')}
    value.update(priors=PRIORS,blend=BLEND,validation_revision=2)
    return hashlib.sha256(json.dumps(value,sort_keys=True,default=str).encode()).hexdigest()


def validation_state(B,cfg,validation):
    if not validation:return 'pending','尚待驗證','載入正式行情後，執行來源模型與融合模型的同條件比較。'
    if validation.get('data_id')!=bundle_identity(B) or validation.get('recipe_id')!=recipe_identity(cfg):
        return 'unmatched','結果待核對','這份結果缺少相符的資料或策略識別，請重新驗證目前資料。'
    if B.meta.get('synthetic') or validation.get('synthetic'):
        return 'demo','示範流程完成','這是合成資料的測試結果，不能推論真實投資報酬。'
    results=validation.get('results',[])
    if {r.get('horizon') for r in results}!=set(HZ):
        return 'incomplete','驗證未完整','短、中、長線尚未全部產生結果。'
    passed=sum(bool(r.get('accepted')) for r in results)
    if passed==3:return 'passed','3／3 週期通過候選門檻','融合模型通過既定歷史比較門檻，仍需觀察實際交易與未涵蓋規則。'
    return 'review',f'{passed}／3 週期通過候選門檻','未通過的週期維持研究候選，依各週期結果判斷是否採用。'


def comparison_rows(validation):
    out=[]
    for r in (validation or {}).get('results',[]):
        for key,label in WINDOWS.items():
            w=r.get('windows',{}).get(key,{})
            out.append({'週期':HZ.get(r.get('horizon'),r.get('horizon')),'測試期間':label,
                '來源年化報酬':w.get('source_cagr'),'融合年化報酬':w.get('v27_cagr'),
                '年化差異':w.get('delta_cagr'),'來源最大回撤':w.get('source_mdd'),
                '融合最大回撤':w.get('v27_mdd'),'同期0050年化':w.get('bench_cagr'),
                '融合資訊比率':w.get('v27_ir'),
                '週期驗收':'通過' if r.get('accepted') else '未通過'})
    return out


def make_record(B,E,validation=None,source=''):
    state,conclusion,note=validation_state(B,E.cfg,validation)
    snapshots=[E.snapshot(h) for h in HZ]
    models=[{'週期':HZ[s.horizon],'模型':s.title,'母池':s.pool,'模型識別':s.model_id,
             '資金批數':s.batch_count,'續抱門檻':s.keep_rank,'權重':s.weights} for s in snapshots]
    limits=[
        '本驗證比較來源模型與20%十面向融合模型；看盤採用價格確認模式時，不能以此替代該模式的績效。',
        '開發期樣本外與保留期互不重疊；全期樣本外包含兩者，不是第三個獨立樣本。',
        '跨市場即時調整、ATR買進區、防守價、2R減碼與介面資金配置尚未納入這份比較。',
        '回測剩餘資金依原設定投入0050或現金；0050可選的實際配置須另做組合回測。',
        '既有歷史曾用於研究，不能視為全新盲測；公告日代理、名冊完整度與修訂仍可能影響績效。']
    if B.meta.get('synthetic'):limits.insert(0,'本次使用合成示範資料；沒有真實推薦或投資績效結論。')
    return {'title':'Alpha Radar 模型研究報告','version':'V27.1 Focus','generated_at':datetime.now(ZoneInfo('Asia/Taipei')).isoformat(timespec='seconds'),
        'data':{'來源':source,'訊號起日':str(B.sig_dates[0].date()),'訊號迄日':str(B.sig_dates[-1].date()),
                '股票數':len(B.tickers),'合成資料':bool(B.meta.get('synthetic')),'資料識別':bundle_identity(B)},
        'state':state,'conclusion':conclusion,'note':note,'models':models,
        'comparison':comparison_rows(validation) if state not in ('pending','unmatched','incomplete') else [],
        'protocol':(validation or {}).get('protocol','固定20%十面向先驗；兩段與全期CAGR平均改善、每段退步不超過10百分點、全期最大回撤惡化不超過5百分點。'),
        'costs':E.cfg['costs'],'validation_meta':{k:(validation or {}).get(k) for k in ('data_id','recipe_id','dates','generated_at')},
        'dimensions':['成長','獲利品質','估值','相對強勢','趨勢結構','法人籌碼','融資與持股','下檔風險','流動性容量','市場心理'],
        'limitations':limits,'quality':B.meta.get('data_quality',{})}


def _esc(value):return html.escape(str(value) if value is not None else '—')


def _percent(value):
    try:return f'{float(value):+.1%}' if np.isfinite(float(value)) else '—'
    except (TypeError,ValueError):return '—'


def render_report(record):
    data=record['data'];rows=record['comparison'];demo=data['合成資料']
    metrics=''
    if rows:
        heads=['週期','測試期間','來源年化報酬','融合年化報酬','年化差異','來源最大回撤','融合最大回撤','同期0050年化','週期驗收']
        metrics='<div class="scroll"><table><thead><tr>'+''.join('<th>'+_esc(k)+'</th>' for k in heads)+'</tr></thead><tbody>'
        for row in rows:
            metrics+='<tr>'+''.join('<td>'+(_percent(row.get(k)) if k in heads[2:8] else _esc(row.get(k)))+'</td>' for k in heads)+'</tr>'
        metrics+='</tbody></table></div>'
    else:metrics='<div class="empty">尚無與目前資料、策略相符的正式績效結果。年化報酬、最大回撤及超額報酬均保留待測。</div>'
    models=''.join('<tr><td>'+_esc(m['週期'])+'</td><td>'+_esc(m['模型'])+'</td><td>'+_esc(m['母池'])+'</td><td>'+str(m['資金批數'])+'</td></tr>' for m in record['models'])
    weights=''.join('<details><summary>'+_esc(m['週期'])+'完整因子權重</summary><pre>'+_esc(json.dumps(m['權重'],ensure_ascii=False,indent=2))+'</pre></details>' for m in record['models'])
    costs=record['costs'];cost_text=f"單邊手續費 {costs.get('fee',0):.4%} × 折扣 {costs.get('fee_discount',1):.0%}；賣出交易稅 {costs.get('tax',0):.4%}；單邊滑價 {costs.get('slippage',0):.4%}。"
    limits=''.join('<li>'+_esc(x)+'</li>' for x in record['limitations'])
    meta=' · '.join(_esc(data[k]) for k in ('來源','訊號起日','訊號迄日'))
    return '''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Alpha Radar 模型研究報告</title>
<style>*{box-sizing:border-box}body{margin:0;background:#eef2f6;color:#182b40;font:15px/1.85,-apple-system,BlinkMacSystemFont,"PingFang TC",sans-serif;font-family:-apple-system,BlinkMacSystemFont,"PingFang TC",sans-serif;line-height:1.85}main{max-width:1040px;margin:36px auto;padding:44px;background:white;border:1px solid #e0e7ee;border-radius:20px}header{border-bottom:1px solid #dce5ec;padding-bottom:24px}.eyebrow{color:#087f78;font-size:12px;letter-spacing:2px}h1{font-size:32px;line-height:1.3;margin:12px 0}h2{font-size:20px;margin:30px 0 12px}.muted{font-size:13px;color:#6c7f91}.verdict{border-left:4px solid #087f78;background:#eef8f6;padding:20px;margin:25px 0}.verdict b{font-size:23px}.scroll{overflow:auto}table{width:100%;border-collapse:collapse;white-space:nowrap;font-size:13px}td,th{padding:12px;text-align:left;border-bottom:1px solid #e5ebf0}th{color:#5f7386;background:#f5f8fb}.empty{border:1px dashed #b9c9d5;padding:20px;color:#63798a}details{padding:12px 0;border-bottom:1px solid #e5ebf0}pre{white-space:pre-wrap;font-size:12px}button{background:#087f78;color:#fff;border:0;border-radius:8px;padding:12px 18px;cursor:pointer}.demo{color:#885c19;background:#fff6df;padding:12px 16px;border-radius:8px}li{margin:7px 0}@media(max-width:600px){main{margin:0;padding:24px 18px;border-radius:0;border:0}h1{font-size:26px}h2{font-size:18px}}@media print{body{background:white}main{margin:0;padding:0;border:0}button{display:none}details{break-inside:avoid}h2{break-after:avoid}.scroll{overflow:visible}table{white-space:normal;font-size:10px}}</style></head><body><main>
<header><div class="eyebrow">ALPHA RADAR / RESEARCH</div><h1>模型研究報告</h1><div class="muted">'''+_esc(record['version'])+' · '+_esc(record['generated_at'])+'</div></header>'+('<p class="demo">合成示範資料｜供檢視研究流程與報告格式，無真實投資結論。</p>' if demo else '')+f'''
<div class="verdict"><div class="muted">本次研究結論</div><b>{_esc(record['conclusion'])}</b><div>{_esc(record['note'])}</div></div>
<h2>一、研究問題與資料</h2><p>固定來源模型與20%十面向先驗融合後，在相同母池、訊號日、成本與執行條件下，是否改善報酬並控制回撤？</p><p class="muted">{meta} · 共{data['股票數']}檔</p>
<h2>二、策略與測試方法</h2><p>以時間順序訓練與重估，標籤須在訓練日前成熟；比較來源模型與融合候選。最新選股為全成熟資料重新估計，不等於用最新權重回填歷史。</p><div class="scroll"><table><tr><th>週期</th><th>目前看盤模型</th><th>母池</th><th>資金批數</th></tr>{models}</table></div><p>十個研究面向：{_esc('、'.join(record['dimensions']))}。各週期權重不同，完整權重列於附錄。</p><p>{_esc(cost_text)}</p><p><b>候選門檻：</b>{_esc(record['protocol'])}</p>
<h2>三、同條件績效比較</h2>{metrics}<p class="muted">開發期樣本外與保留期互不重疊；全期樣本外包含兩者。年化差異為百分點；資訊比率不是勝率。</p>
<h2>四、如何用於投資參考</h2><p>先在儀表板選一個操作週期，閱讀前三檔入選助力與拖累因素。盤後以買進區、防守價規劃次日；盤中需核對有效成交與資料日期，再評估預定本批資金的1/3。超出買區等拉回，低於買區先等止跌。0050可設為0%，配置限制需另測。</p>
<h2>五、限制與下一步</h2><ul>{limits}</ul><p>下一步依序驗證：跨市場歷史時點資料、價位與出場規則、零0050組合及成本壓力，再以新期間資料檢查穩定性。這些項目尚未完成，不計入本次通過門檻。</p>
<h2>附錄：可核對的模型與資料</h2><p class="muted">資料識別 {_esc(data['資料識別'])}</p>{weights}<details><summary>資料品質與驗證識別</summary><pre>{_esc(json.dumps({'quality':record['quality'],'validation':record['validation_meta']},ensure_ascii=False,indent=2,default=str))}</pre></details><p><button onclick="window.print()">列印／另存 PDF</button></p><footer class="muted">Alpha Radar PRO · 報告由目前載入資料產生；歷史績效不代表未來。</footer></main></body></html>'''
