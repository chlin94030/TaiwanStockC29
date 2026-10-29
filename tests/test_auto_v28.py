import copy,threading
import pandas as pd
from kosto.auto_market import WEIGHTS,NAMES,AutoMarket,read_snapshot,SEED,screen,audit_record
from kosto.auto_quotes import QuoteHub
from kosto.auto_report import render


def test_weight_sums_and_independent_real_seed():
    assert all(abs(sum(w.values())-1)<1e-10 and set(w)==set(NAMES) for w in WEIGHTS.values())
    p=read_snapshot(SEED);assert p and len(p['price'])>500
    data=screen(p);assert data.eligible.sum()>=3
    assert not data.name.str.contains('合成|示範').any()


def test_future_revenue_is_not_used_and_missing_is_not_zero():
    p=read_snapshot(SEED);before=screen(p);t=before.ticker.iloc[0]
    q=copy.deepcopy(p)
    for r in q['revenue']+q['otc_revenue']:
        if str(r.get('公司代號'))==t:r['出表日期']='9991231';r['營業收入-去年同月增減(%)']='999999'
    after=screen(q).set_index('ticker');assert pd.isna(after.loc[t,'growth'])
    assert after.loc[t,'coverage']<before.set_index('ticker').loc[t,'coverage']


def test_long_trend_does_not_use_short_history():
    d=screen(read_snapshot(SEED),'long')
    assert d.loc[d.history_days<120,'trend'].isna().all()
    assert d.loc[d.history_days<61,'leadership'].isna().all()


def test_offline_startup_needs_no_import_and_exports_truthful_report(tmp_path):
    m=AutoMarket(tmp_path,online=False);assert len(m.picks('mid'))>20
    m.refresh();assert not m.running
    record=audit_record(m);html=render(record)
    assert not record['data']['合成資料'] and not record['comparison']
    assert '投資績效待驗證' in html and '匯入 Claude' not in html


def test_quotes_shared_five_second_cadence_and_original_timestamp():
    completed=threading.Event()
    class Feed:
        error=''
        def fetch(self,channels):
            completed.set();return pd.DataFrame([{'ticker':'2330','price':100,'trade_at':'2026-10-28T09:00:00+08:00'}])
    hub=QuoteHub(Feed());stocks=[{'ticker':'2330','board':'TWSE'}]
    hub.get(stocks,clock=lambda:100);assert completed.wait(2)
    for _ in range(100):
        if not hub.running:break
        threading.Event().wait(.01)
    hub.get(stocks,clock=lambda:104.9);assert hub.attempts==1
    data=hub.get(stocks,enabled=False,clock=lambda:105.1)
    assert hub.attempts==1 and data['2330']['trade_at']=='2026-10-28T09:00:00+08:00'
    hub.get(stocks,clock=lambda:105.1);assert hub.attempts==2


def test_quote_failure_preserves_old_timestamp():
    class Failed:
        def fetch(self,_):raise ValueError('offline')
    hub=QuoteHub(Failed());hub.rows={'2330':{'ticker':'2330','trade_at':'old'}}
    hub.get([{'ticker':'2330','board':'TWSE'}])
    for _ in range(100):
        if not hub.running:break
        threading.Event().wait(.01)
    assert hub.rows['2330']['trade_at']=='old' and hub.error
