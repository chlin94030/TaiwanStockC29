"""Offline preview using the same real dated snapshot and independent model as the app."""
from pathlib import Path
import sys,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from plotly.offline import get_plotlyjs
from kosto.auto_market import AutoMarket,audit_record,safe
from kosto.auto_report import render
from kosto.desk_plan import build_plan,HZ,PROFILES
from kosto.desk_chips import chips
from kosto import ta
from kosto.strategy_lab import Lab
from kosto.lab_report import render as lab_report
from lab_preview import upgrade

ROOT=Path(__file__).resolve().parents[1]


def export(out):
    market=AutoMarket(ROOT,online=False);data={h:market.picks(h) for h in HZ}
    picks={h:f.loc[f.eligible].head(10).ticker.tolist() for h,f in data.items()}
    keys=list(dict.fromkeys(t for h in HZ for t in picks[h]));stocks={}
    for t in keys:
        rec=next(f.loc[f.ticker.eq(t)].iloc[0].to_dict() for f in data.values() if f.ticker.eq(t).any())
        f=market.history(t,schedule=False)
        if f.empty:
            f=pd.DataFrame([r for r in market.payload['history'] if r['ticker']==t])
            if not f.empty:f['date']=pd.to_datetime(f.date);f=f.set_index('date').sort_index()
        plans={h:build_plan(f,h) if not f.empty and {'open','high','low','volume'}.issubset(f.columns) else None for h in HZ}
        plans={h:p.as_dict() if p else dict.fromkeys(['buy_low','buy_high','alert','take1','entry','chase']) for h,p in plans.items()}
        charts={}
        for per in ['D','W','M']:
            if not f.empty and {'open','high','low','volume'}.issubset(f.columns):
                q=ta.indicators(ta.resample(f,per)).tail(252)
            else:
                q=f.resample({'D':'D','W':'W-FRI','M':'ME'}[per]).last().dropna(subset=['close']) if not f.empty else pd.DataFrame(columns=['close'])
            charts[per]={'x':[str(x.date()) for x in q.index],**{k:q[k].tolist() for k in q if k!='ticker'}}
        chip={'table':[{'法人':name,'最新日(張)':rec.get(k),'近5日(張)':None,'近20日(張)':None} for k,name in [('foreign','外資'),('trust','投信'),('dealer','自營商')]],
            'notes':['法人為最近已公布日資料，未提供未觀測的多日合計'],
            'balances':{name:{'value':rec.get(k),'date':rec['date']} for k,name in [('mbal','融資餘額'),('sbal','融券餘額')]},
            'holders':{'value':None,'date':'尚未接入'}}
        stocks[t]={'ticker':t,'name':rec['name'],'group':rec['group'],'segment':rec['segment'],'price':rec['price'],
            'scores':{h:f.loc[f.ticker.eq(t)].iloc[0].to_dict() for h,f in data.items()},'plans':plans,'charts':charts,'chips':chip}
    report=audit_record(market);payload=safe({'stocks':stocks,'selections':picks,'profiles':PROFILES,'exposures':{h:1 for h in HZ},
        'date':max((str(r['date'])[:10] for r in market.payload['price']),default='—'),'report':report,'report_html':render(report)})
    lab=Lab(ROOT).report()
    lab['attachment_review']={'finding':'使用者附檔僅完成資料檢核，初篩753檔，短線平均因子涵蓋50%；年化報酬、回撤、勝率均為待驗證。V28固定先驗並未透過投資績效搜尋選出最佳權重。'}
    payload['lab']=lab;payload['report_html']=lab_report(lab,report)
    template=(ROOT/'scripts'/'focus_preview.html').read_text()
    replacements={
      'V27.1 FOCUS':'V28 AUTO','操作示範｜價格、排名及籌碼皆為合成資料，無真實買入訊號。':'真實市場快照｜資料日期如下；此HTML為離線預覽，5秒盤中更新請開啟正式程式。',
      '合成示範':'真實快照','合成資料':'公開市場快照','合成數據':'公開資料',
      '今天，先從這幾檔開始。':'開啟，就從推薦開始。','此預覽使用公開市場快照；報酬率、回撤及超額績效保留待測。':'採用真實市場快照；獨立模型的投資績效仍待歷史時點驗證。',
      '尚待正式資料驗證':'資料已檢核；投資績效待驗證','原模型 vs 十面向融合':'獨立十面向規則模型',
      '原模型與融合模型比較':'研究驗證進度','原模型年化':'年化報酬','融合年化':'超額報酬',
      '正式版可沿用原專案行情包、載入驗證結果、選擇模型及更新資料。':'正式程式開啟即顯示推薦，背景自動抓取公開行情，不需匯入任何資料。',
      '手機部署仍使用同層9檔上傳包；原GitHub專案的行情與Releases可延續。':'手機部署維持同層檔案上傳；首次使用不需歷史資料包。',
      'ALPHA RADAR PRO · V28 AUTO · 此檔為離線操作預覽，全部示範數值均為公開市場快照。':'ALPHA RADAR PRO · V28 AUTO · 此檔使用有日期的真實公開市場快照，並非即時成交。',
      '按時間順序訓練、標籤成熟後才使用；相同母池、成本與換股規則比較原模型與20%十面向融合候選。':'獨立模型使用公開行情、營收、財報與估值，依短中長線固定權重評分。缺值中性處理並降低涵蓋率。',
      '門檻：兩段與全期CAGR平均改善，每段退步不超過10百分點，全期最大回撤惡化不超過5百分點。全期包含兩段，不是第三個獨立樣本。':'目前完成資料與操作檢核；投資績效需使用當時可得歷史基本面驗證，不將今日因子倒填歷史。',
      '正式版按「執行本資料驗證」後會以載入行情計算；公開市場快照結果會明確標示，不作為真實投資依據。':'正式版自動產生資料檢核與研究報告；尚未完成的年化報酬與回撤保持待測。',
      '短線候選':'短線候選'}
    for a,b in replacements.items():template=template.replace(a,b)
    template=template.replace("parts.forEach((part,i)=>{","if(!a.open||!a.high||!a.low){Plotly.react('chart',[{type:'scatter',mode:'lines',x:a.x,y:a.close,name:'實際收盤',line:{color:'#087f76'}}],{height:360,margin:{l:40,r:20,t:20,b:35}},{responsive:true,displaylogo:false});return;}parts.forEach((part,i)=>{")
    template=template.replace('if(qty<=0)return;','if(!Number.isFinite(qty)||!Number.isFinite(price)||price<=0||risk<=0||qty<=0)return;')
    template=template.replace('${px(p.buy_low)}–${px(p.buy_high)}','${p.buy_low==null?"待K線確認":px(p.buy_low)+"–"+px(p.buy_high)}')
    raw=json.dumps(payload,ensure_ascii=False,allow_nan=False).replace('<','\\u003c')
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(upgrade(template.replace('%%PLOTLY%%',get_plotlyjs()).replace('%%DATA%%',raw)),encoding='utf-8')
    out.with_name('AlphaRadar_V29_Validation_Review.html').write_text(payload['report_html'],encoding='utf-8')
    return out


if __name__=='__main__':print(export(Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'artifacts'/'interface.html'))
