"""Independent cold-start screening: real packaged snapshot, background refresh, no import step."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import gzip,json,threading,time,hashlib,copy
import numpy as np
import pandas as pd
import requests
from .chain import label
from .desk_plan import build_plan,decision,signal_current

API='https://openapi.twse.com.tw/v1/'
ENDPOINTS={'price':API+'exchangeReport/STOCK_DAY_ALL','history':API+'exchangeReport/STOCK_DAY_AVG_ALL',
    'value':API+'exchangeReport/BWIBBU_ALL','revenue':API+'opendata/t187ap05_L','quality':API+'opendata/t187ap14_L',
    'otc_value':'https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis',
    'otc_revenue':'https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O'}
NAMES={'growth':'營收成長','quality':'獲利品質','value':'估值','leadership':'相對強勢','trend':'趨勢結構',
       'institutions':'法人買盤','financing':'融資擁擠度','risk':'價格風險','liquidity':'流動性','behavior':'收盤強度'}
WEIGHTS={
 'short':dict(zip(NAMES,[.08,.04,.05,.20,.14,.16,.05,.10,.08,.10])),
 'mid':dict(zip(NAMES,[.20,.10,.10,.16,.12,.12,.04,.08,.04,.04])),
 'long':dict(zip(NAMES,[.28,.16,.15,.12,.10,.07,.03,.05,.02,.02]))}
MIN_COVERAGE=.50
SEED=Path(__file__).with_name('data')/'startup_market.json.gz'


def now():return datetime.now(ZoneInfo('Asia/Taipei')).isoformat(timespec='seconds')


def number(x):
    try:
        v=float(str(x).replace(',','').replace('%',''))
        return v if np.isfinite(v) else np.nan
    except (ValueError,TypeError):return np.nan


def date(x):
    s=str(x).strip().replace('/','').replace('-','')
    try:
        if len(s)==7:s=str(int(s[:3])+1911)+s[3:]
        return str(pd.Timestamp(s).date()) if len(s)==8 else None
    except (ValueError,TypeError):return None


def safe(value):
    if isinstance(value,dict):return {str(k):safe(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [safe(x) for x in value]
    if isinstance(value,(np.integer,)):return int(value)
    if isinstance(value,(np.bool_,)):return bool(value)
    if isinstance(value,(float,np.floating)):return float(value) if np.isfinite(value) else None
    if isinstance(value,(pd.Timestamp,datetime)):return value.isoformat()
    return value


def write_snapshot(path,payload):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    raw=json.dumps(safe(payload),ensure_ascii=False,allow_nan=False).encode()
    tmp=path.with_suffix('.tmp');tmp.write_bytes(gzip.compress(raw));tmp.replace(path)


def read_snapshot(path):
    try:
        value=json.loads(gzip.decompress(Path(path).read_bytes()))
        if not isinstance(value,dict) or not isinstance(value.get('price'),list):return None
        if len(value['price'])<50:return None
        return value
    except (OSError,ValueError,EOFError):return None


def _json(url):
    # Some public gateways leave a connection open after a complete JSON body.
    # Stop at a complete JSON document rather than waiting for a misleading length.
    with requests.get(url,timeout=(4,20),headers={'User-Agent':'Mozilla/5.0'},stream=True) as r:
        r.raise_for_status();body=bytearray();value=None
        while len(body)<20_000_000:
            chunk=r.raw.read1(65536,decode_content=True)
            if not chunk:break
            body.extend(chunk)
            if body.rstrip().endswith((b']',b'}')):
                try:value=json.loads(body.decode('utf-8-sig'));break
                except (ValueError,UnicodeDecodeError):pass
        if value is None:value=json.loads(body.decode('utf-8-sig'))
    if not isinstance(value,list) or not value:raise ValueError('empty official response')
    return value


def fetch_snapshot(previous=None,progress=lambda x:None):
    previous=previous or {};raw={};errors=[];sources=[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        tasks={pool.submit(_json,url):key for key,url in ENDPOINTS.items()}
        for f in as_completed(tasks):
            key=tasks[f]
            try:raw[key]=f.result();sources.append({'dataset':key,'url':ENDPOINTS[key],'retrieved_at':now(),'rows':len(raw[key])})
            except Exception as e:errors.append(key+': '+type(e).__name__)
    prices=[]
    for r in raw.get('price',[]):
        prices.append({'ticker':str(r.get('Code','')),'name':r.get('Name',''),'board':'TWSE','date':date(r.get('Date')),
            'open':number(r.get('OpeningPrice')),'high':number(r.get('HighestPrice')),'low':number(r.get('LowestPrice')),
            'close':number(r.get('ClosingPrice')),'volume':number(r.get('TradeVolume')),
            'amount':number(r.get('TradeValue')),'change':number(r.get('Change'))})
    # Official parsers preserve board-specific units. Never invent an OTC row.
    from .sources.official import Official,Http
    def board_data(board,method,d):
        p=Official(Http(pause=.2,retries=1,timeout=8));return getattr(p,board+'_'+method)(pd.Timestamp(d))
    d=max((p['date'] for p in prices if p['date']),default=str(pd.Timestamp.now(tz='Asia/Taipei').date()))
    extra={}
    with ThreadPoolExecutor(max_workers=2) as pool:
        specs=[('tpex','price'),('twse','inst'),('twse','margin'),('tpex','inst'),('tpex','margin')]
        if not prices:specs.insert(0,('twse','price'))
        if 'value' not in raw:specs.append(('twse','valuation'))
        tasks={pool.submit(board_data,b,m,d):(b,m) for b,m in specs}
        for f in as_completed(tasks):
            b,m=tasks[f]
            try:
                rows=f.result().to_dict('records')
                if m=='price':prices+=rows
                elif m=='valuation':raw['value']=[{'Code':x['ticker'],'Date':str(pd.Timestamp(x['date']).date()).replace('-',''),'PEratio':x.get('pe'),'PBratio':x.get('pb'),'DividendYield':x.get('dy')} for x in rows]
                else:extra.setdefault(m,[]).extend(rows)
                if rows:sources.append({'dataset':b+'_'+m,'date':d,'retrieved_at':now(),'rows':len(rows)})
            except Exception as e:errors.append(b+'_'+m+': '+type(e).__name__)
    if len(prices)<50:raise ValueError('整批行情尚未取得；保留上次有效快照')
    prices=safe(prices)
    for p in prices:p['date']=str(p['date'])[:10]
    # Retain previous board only when it was unavailable, with its original date.
    boards={p['board'] for p in prices}
    prices += [p for p in previous.get('price',[]) if p.get('board') not in boards]
    history=raw.get('history') or previous.get('history',[])
    if history and 'Code' in history[0]:history=[{'ticker':str(r['Code']),'date':date(r['Date']),'close':number(r.get('ClosingPrice'))} for r in history]
    result={'schema':1,'generated_at':now(),'price':prices,'history':history,
        'value':raw.get('value') or previous.get('value',[]),'revenue':raw.get('revenue') or previous.get('revenue',[]),
        'quality':raw.get('quality') or previous.get('quality',[]),
        'otc_value':raw.get('otc_value') or previous.get('otc_value',[]),'otc_revenue':raw.get('otc_revenue') or previous.get('otc_revenue',[]),
        'inst':safe(extra.get('inst') or previous.get('inst',[])),'margin':safe(extra.get('margin') or previous.get('margin',[])),
        'sources':sources+[s for s in previous.get('sources',[]) if s['dataset'] not in {x['dataset'] for x in sources}],
        'errors':errors,'ohlc':previous.get('ohlc',{})}
    progress('已取得整批行情與可用因子');return safe(result)


def _valid_date(observed,limit):return observed is not None and str(observed)[:10]<=limit


def screen(payload,horizon='mid',frames=None):
    """Cross-sectional ranks; missing factors remain neutral and reduce coverage."""
    frames=frames or {};values={str(r['Code']):r for r in payload.get('value',[])}
    # A live decision may use a newly observed report with the previous close.
    # Keep the decision/observation date distinct from the price's trading date.
    observation_day=min(str(payload.get('generated_at') or now())[:10],now()[:10])
    values.update({str(r.get('SecuritiesCompanyCode')):{'PEratio':r.get('PriceEarningRatio'),'PBratio':r.get('PriceBookRatio'),'Date':r.get('Date')} for r in payload.get('otc_value',[])})
    rev={str(r.get('公司代號')):r for r in payload.get('revenue',[])+payload.get('otc_revenue',[])}
    quality={str(r.get('公司代號')):r for r in payload.get('quality',[])}
    inst={str(r['ticker']):r for r in payload.get('inst',[])};margin={str(r['ticker']):r for r in payload.get('margin',[])}
    history=pd.DataFrame(payload.get('history',[]));hist={}
    if not history.empty:
        history['close']=pd.to_numeric(history.close,errors='coerce');history=history.dropna(subset=['date','close'])
        hist={str(t):g.sort_values('date').drop_duplicates('date').set_index('date').close for t,g in history.groupby('ticker')}
    rows=[]
    for p in payload.get('price',[]):
        t=str(p.get('ticker',''));close=number(p.get('close'));amount=number(p.get('amount'));volume=number(p.get('volume'));day=str(p.get('date',''))[:10]
        if not (len(t)==4 and t.isdigit() and not t.startswith('00') and close>=10 and amount>=20_000_000 and volume>0):continue
        rr=rev.get(t,{})
        if rr and not _valid_date(date(rr.get('出表日期')),observation_day):rr={}
        val=values.get(t,{})
        if val and not _valid_date(date(val.get('Date')),day):val={}
        cs=hist.get(t,pd.Series(dtype=float))
        if not cs.empty:cs=cs.loc[cs.index<=day]
        f=frames.get(t)
        if f is not None and not f.empty:
            series=f.loc[f.index<=pd.Timestamp(day),'close'].dropna();cs=pd.Series(series.values,index=series.index.strftime('%Y-%m-%d'))
        cs=cs[cs>0];ret=cs.pct_change().dropna();look={'short':5,'mid':20,'long':60}[horizon];ma={'short':20,'mid':60,'long':120}[horizon]
        ir=inst.get(t,{})
        if not _valid_date(ir.get('date'),day) or (ir and (pd.Timestamp(day)-pd.Timestamp(ir['date'])).days>4):ir={}
        mg=margin.get(t,{})
        if not _valid_date(mg.get('date'),day) or (mg and (pd.Timestamp(day)-pd.Timestamp(mg['date'])).days>4):mg={}
        pe=number(val.get('PEratio'));pb=number(val.get('PBratio'));high=number(p.get('high'));low=number(p.get('low'));chg=number(p.get('change'))
        qr=quality.get(t,{})
        if qr and not _valid_date(date(qr.get('出表日期')),observation_day):qr={}
        revenue=number(qr.get('營業收入'));profit=number(qr.get('稅後淨利'))
        factors={'growth':number(rr.get('營業收入-去年同月增減(%)')),'quality':profit/revenue if revenue>0 else np.nan,
            'value':1/pe if pe>0 else np.nan,'leadership':cs.iloc[-1]/cs.iloc[-look-1]-1 if len(cs)>look else np.nan,
            'trend':cs.iloc[-1]/cs.tail(ma).mean()-1 if len(cs)>=ma else np.nan,
            'institutions':(number(ir.get('foreign'))+number(ir.get('trust')))/volume if ir else np.nan,
            'financing':-number(mg.get('mbal'))/number(mg.get('mlimit')) if number(mg.get('mlimit'))>0 else np.nan,
            'risk':-ret.tail(20).std() if len(ret)>=15 else np.nan,'liquidity':np.log1p(amount),
            'behavior':(close-low)/(high-low) if high>low else np.nan}
        chain=label(t,rr.get('產業別',''));rows.append({**p,'price':close,'change_pct':chg/(close-chg) if close-chg>0 else np.nan,
            'group':chain['group'],'segment':chain['segment'],'sector':rr.get('產業別') or chain['chain'] or chain['group'],
            'revenue_date':str(rr.get('資料年月','')),'revenue_yoy':factors['growth'],'pe':pe,'pb':pb,
            'revenue_mom':number(rr.get('營業收入-上月比較增減(%)')),'eps':number(qr.get('基本每股盈餘(元)')),
            'quality_period':str(qr.get('年度',''))+'年第'+str(qr.get('季別',''))+'季',
            'foreign':number(ir.get('foreign'))/1000,'trust':number(ir.get('trust'))/1000,'dealer':number(ir.get('dealer'))/1000,
            'inst_date':str(ir.get('date',''))[:10],'mbal':number(mg.get('mbal')),'sbal':number(mg.get('sbal')),
            'history_days':len(cs),**factors})
    data=pd.DataFrame(rows)
    if data.empty:return data
    scores=pd.DataFrame(index=data.index);weights=WEIGHTS[horizon]
    for k in NAMES:
        scores[k]=data[k].rank(pct=True)*100
        # Sector-normalise valuation where enough peers exist.
        if k in ('value','quality'):
            for _,idx in data.groupby('sector').groups.items():
                if data.loc[idx,k].notna().sum()>=8:scores.loc[idx,k]=data.loc[idx,k].rank(pct=True)*100
    data['coverage']=sum(scores[k].notna().astype(float)*w for k,w in weights.items())
    data['score']=sum(scores[k].fillna(50)*w for k,w in weights.items())
    data['eligible']=data.coverage>=MIN_COVERAGE;data['strategy_status']='初選觀察・未驗效';data['observed_asof']=observation_day
    reasons=[];risks=[]
    for idx,r in data.iterrows():
        contribution={k:(scores.at[idx,k]-50)*w for k,w in weights.items() if pd.notna(scores.at[idx,k])}
        positives=[k for k in sorted(contribution,key=contribution.get,reverse=True) if contribution[k]>0][:2]
        negatives=[k for k in sorted(contribution,key=contribution.get) if contribution[k]<0][:2]
        explain={'growth':f'最新月營收年增 {r.revenue_yoy:+.1f}%' if pd.notna(r.revenue_yoy) else '',
            'quality':'最新財報淨利率相對同業較佳',
            'value':f'本益比 {r.pe:.1f}倍，估值排名較有利','leadership':f'近{look}交易日走勢相對靠前',
            'trend':f'相對{ma}日均線結構較強','institutions':'外資與投信合計買盤相對較強',
            'financing':'融資使用率相對較低','risk':'近20日價格波動相對較小','liquidity':'成交金額較充足','behavior':'收盤位於當日區間較高處'}
        reasons.append('、'.join(explain[k] for k in positives) or '綜合條件相對靠前')
        risks.append('、'.join(NAMES[k]+'相對較弱' for k in negatives) or '跳空及消息風險')
    data['reasons']=reasons;data['risk']=risks
    data=data.sort_values(['eligible','score','amount','ticker'],ascending=[False,False,False,True]).drop_duplicates('ticker').reset_index(drop=True)
    data['rank']=np.arange(1,len(data)+1);return data


class AutoMarket:
    def __init__(self,root,online=True):
        self.root=Path(root);self.path=self.root/'artifacts'/'auto_market.json.gz';self.lock=threading.RLock();self.online=online
        self.payload=read_snapshot(self.path) or read_snapshot(SEED) or {'price':[],'history':[],'sources':[]}
        self.status='啟動快照已就緒' if self.payload['price'] else '自動取得整批市場資料'
        self.error='';self.running=False;self.last_attempt=0.;self.version=0;self.frames={};self.history_jobs=set();self.history_attempt={};self.cache={}
        self.pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='market-history')
        self.lab=None
        self.global_snapshot=None;self.global_attempt=-1e9
        for t,rows in self.payload.get('ohlc',{}).items():
            try:
                f=pd.DataFrame(rows);f['date']=pd.to_datetime(f.date);self.frames[t]=f.set_index('date').sort_index()
            except (ValueError,KeyError):pass
        if online:self.refresh()

    def refresh(self,force=False):
        if not self.online:return
        with self.lock:
            if self.running or (not force and time.monotonic()-self.last_attempt<900):return
            self.running=True;self.last_attempt=time.monotonic();self.status='背景更新中，先顯示最近有效推薦'
        def run():
            try:
                data=fetch_snapshot(self.payload)
                if max(str(r.get('date','')) for r in data['price'])<max((str(r.get('date','')) for r in self.payload['price']),default=''):
                    raise ValueError('來源回傳較舊行情，保留前次快照')
                write_snapshot(self.path,data)
                with self.lock:self.payload=data;self.version+=1;self.cache.clear();self.status='市場資料自動更新完成';self.error=''
            except Exception as e:
                with self.lock:self.error=str(e);self.status='更新暫未完成，沿用最近有效快照'
            finally:self.running=False
        threading.Thread(target=run,daemon=True,name='auto-market-refresh').start()
        if time.monotonic()-self.global_attempt>900:
            self.global_attempt=time.monotonic()
            def overseas():
                from .global_markets import fetch_global
                self.global_snapshot=fetch_global()
            threading.Thread(target=overseas,daemon=True,name='global-context').start()

    def picks(self,h):
        with self.lock:
            active=self.lab.active_key(h) if self.lab else ''
            key=(self.version,h,active)
            if key not in self.cache:
                formal=self.lab.live_records(self.payload,h,self.frames) if active else None
                self.cache[key]=formal if formal is not None else screen(self.payload,h,self.frames)
            return self.cache[key].copy(deep=True)

    def history(self,ticker,board='TWSE',schedule=True):
        path=self.root/'artifacts'/'history'/f'{ticker}.json'
        with self.lock:
            if ticker not in self.frames and path.exists():
                try:
                    f=pd.DataFrame(json.loads(path.read_text()));f['date']=pd.to_datetime(f.date);self.frames[ticker]=f.set_index('date').sort_index()
                except (ValueError,OSError,KeyError):pass
            frame=self.frames.get(ticker,pd.DataFrame()).copy()
            latest=max((str(p['date'])[:10] for p in self.payload['price'] if p['ticker']==ticker),default='')
            fresh=not frame.empty and str(frame.index[-1].date())>=latest and len(frame)>=240
            if schedule and self.online and not fresh and board=='TWSE' and ticker not in self.history_jobs and time.monotonic()-self.history_attempt.get(ticker,-1e9)>900:
                self.history_jobs.add(ticker);self.history_attempt[ticker]=time.monotonic();self.pool.submit(self._history_job,ticker)
        return frame

    def _history_job(self,ticker):
        from .sources.official import roc_to_date
        path=self.root/'artifacts'/'history'/f'{ticker}.json'
        old=self.frames.get(ticker,pd.DataFrame())
        pieces=safe(old.reset_index().to_dict('records')) if not old.empty else []
        for p in pieces:p['date']=str(p['date'])[:10]
        end=pd.Timestamp.now(tz='Asia/Taipei').tz_localize(None)
        months=2 if len(pieces)>=240 else 14
        for month in pd.date_range(end=end.replace(day=1),periods=months,freq='MS')[::-1]:
            try:
                r=requests.get('https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY',params={'response':'json','date':month.strftime('%Y%m%d'),'stockNo':ticker},timeout=(3,8));r.raise_for_status();j=r.json()
                if str(j.get('stat',''))!='OK':
                    time.sleep(1);continue
                for x in j.get('data',[]):
                    d=roc_to_date(x[0]);c=number(x[6])
                    if pd.isna(d) or not c>0:continue
                    pieces.append({'date':str(d.date()),'open':number(x[3]),'high':number(x[4]),'low':number(x[5]),'close':c,'volume':number(x[1])/1000})
                if pieces:
                    f=pd.DataFrame(pieces).drop_duplicates('date',keep='last').sort_values('date');f['date']=pd.to_datetime(f.date)
                    with self.lock:self.frames[ticker]=f.set_index('date');self.version+=1;self.cache.clear()
                time.sleep(.8)
            except (requests.RequestException,ValueError,KeyError,IndexError):time.sleep(1)
        if pieces:
            path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(safe(pieces),ensure_ascii=False));tmp.replace(path)
        with self.lock:self.history_jobs.discard(ticker)


def audit_record(market,h='mid'):
    data=market.picks(h);coverage=float(data.coverage.mean()) if not data.empty else 0
    dates=sorted({str(r.get('date','')) for r in market.payload.get('price',[])})
    return {'title':'Alpha Radar 獨立模型研究報告','version':'V28 AUTO','generated_at':now(),
        'data':{'來源':'證交所／櫃買公開資料，自動取得','訊號起日':dates[0] if dates else '—','訊號迄日':dates[-1] if dates else '—',
                '股票數':len(data),'合成資料':False,'資料識別':hashlib.sha256(json.dumps(market.payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()},
        'state':'pending','conclusion':'資料檢核已完成；投資績效待驗證','note':f'目前{len(data)}檔通過價格與流動性初篩；{h}平均因子涵蓋{coverage:.0%}。缺值以中性處理並降低涵蓋率。',
        'models':[{'週期':{'short':'短線','mid':'中線','long':'長線'}[k],'模型':'獨立十面向選股','母池':'上市／上櫃實際取得的普通股','資金批數':{'short':1,'mid':4,'long':12}[k],'權重':v} for k,v in WEIGHTS.items()],
        'comparison':[],'protocol':'先檢查資料日期、因子可得性、流動性與缺值；完整績效驗證須使用當時可得的歷史因子，不能將今日營收／估值倒填歷史。',
        'costs':{'fee':.001425,'fee_discount':.6,'tax':.003,'slippage':.001},'validation_meta':{},'dimensions':list(NAMES.values()),
        'limitations':['本版為獨立規則模型，並非早期研究擬合模型的績效延伸。','各股缺失的財報或價格因子保持中性，依實際涵蓋率顯示；不宣稱每檔具備全部觀測。',
            '歷史K線背景補齊前，長週期趨勢及技術買區維持待確認；不以短資料冒充長期趨勢。',
            '5秒是報價刷新排程，不保證上游每5秒產生新成交或準時回應。','完整歷史基本面、股利、名冊與交易成本驗證未完成，不提供虛構勝率或年化報酬。'],
        'quality':{'sources':market.payload.get('sources',[]),'errors':market.payload.get('errors',[]),'coverage':coverage}}
