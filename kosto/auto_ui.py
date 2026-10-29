"""V28 independent app: open to real recommendations; all acquisition is automatic."""
from __future__ import annotations
import json,os
from pathlib import Path
import numpy as np
import pandas as pd
import streamlit as st
from .auto_market import AutoMarket,WEIGHTS,NAMES,audit_record,safe
from .auto_quotes import QuoteHub
from .auto_report import render as report_html
from .desk_style import css,esc,title
from .desk_quotes import phase,taipei,quote_check
from .desk_plan import HZ,PROFILES,build_plan,decision,signal_current,allocation

ROOT=Path(os.getenv('ALPHA_DESK_PROJECT_ROOT',Path(__file__).resolve().parent.parent))


@st.cache_resource(show_spinner=False)
def service(root,online=True):return AutoMarket(root,online)


@st.cache_resource(show_spinner=False)
def quote_hub():return QuoteHub()


def price(x):
    try:return f'{float(x):,.2f}' if np.isfinite(float(x)) else '待確認'
    except (TypeError,ValueError):return '待確認'


def plan_for(market,row,h,schedule=True):
    f=market.history(row['ticker'],row['board'],schedule=schedule)
    if f.empty or len(f)<60:return None
    valid=f[['open','high','low','close']].dropna()
    if len(valid)<60 or str(valid.index[-1].date())!=str(row['date']):return None
    return build_plan(f,h)


def card(row,h,p,q=None):
    synthetic=False
    state=decision(p,q,mode='live' if phase()=='盤中' else 'close',data_ready=signal_current(row['date']) and row['eligible'],synthetic=synthetic)
    if p is None:state_label='價格待K線確認'
    else:state_label=state.label
    if not signal_current(row['date']):state_label='快照觀察・等待更新'
    if row.get('strategy_status')!='研究閘門通過' and state.can_enter:state_label='價位符合・研究候選'
    shown=q.get('price') if q and quote_check(q)[0] else row['price']
    levels=[('參考價',price(shown)),('買進參考區',price(p.buy_low)+'–'+price(p.buy_high) if p else '背景補齊中'),('防守參考',price(p.alert) if p else '待確認')]
    html='<div class="focus-pick"><div class="focus-pick-top"><span class="focus-rank">優先觀察 '+f'{int(row["rank"]):02d}'+'</span><span class="focus-status">'+esc(state_label)+'</span></div>'
    html+='<div class="focus-name"><b>'+esc(row['name'])+'</b><span>'+esc(row['ticker'])+'</span></div><div class="focus-sector">'+esc(row['group'])+' · '+HZ[h]+'</div>'
    html+='<div class="focus-reason-label">為什麼入選</div><ul class="focus-reasons">'+''.join('<li>'+esc(x)+'</li>' for x in row['reasons'].split('、')[:2])+'</ul>'
    html+='<div class="focus-levels">'+''.join('<div><span>'+esc(k)+'</span><b>'+esc(v)+'</b></div>' for k,v in levels)+'</div>'
    html+='<div class="focus-risk"><b>留意</b> '+esc(row['risk'])+'</div><div class="focus-score">相對分數 '+f'{row["score"]:.1f} / 100 · 因子涵蓋 {row["coverage"]:.0%} · 非勝率</div></div>'
    st.markdown(html,unsafe_allow_html=True)
    st.caption(str(row.get('strategy_status','初選觀察・未驗效'))+'｜行情 '+str(row['date'])+(' · 成交 '+str(q.get('time','')) if q else ' · 最近收盤'))


def detail(market,row,h):
    if st.button('← 返回推薦清單'):
        st.session_state.pop('auto_detail',None);st.rerun()
    st.markdown(title(row['name']+' '+row['ticker'],row['group']),unsafe_allow_html=True)
    st.write('入選助力：'+row['reasons']);st.caption('留意：'+row['risk'])
    p=plan_for(market,row,h)
    if p:st.info(f'買區 {price(p.buy_low)}～{price(p.buy_high)}｜防守 {price(p.alert)}｜2R參考 {price(p.take1)}')
    else:st.info('歷史K線正在背景補齊。先閱讀公司與入選原因；技術價位完成前維持觀察。')
    f=market.history(row['ticker'],row['board'])
    if f.empty:
        hist=[r for r in market.payload.get('history',[]) if r['ticker']==row['ticker']]
        if hist:
            f=pd.DataFrame(hist);f['date']=pd.to_datetime(f.date);f=f.set_index('date').sort_index();f['close']=pd.to_numeric(f.close,errors='coerce')
    if not f.empty:
        from . import ta
        import plotly.graph_objects as go
        period=st.segmented_control('圖表週期',['D','W','M'],format_func=lambda x:{'D':'日','W':'週','M':'月'}[x],default='D') or 'D'
        actual={'open','high','low','volume'}.issubset(f.columns)
        if actual:
            f=ta.resample(f,period);ind=ta.indicators(f)
            options=['volume','kd','macd','rsi','boll'];panels=st.multiselect('顯示指標',options,default=['volume','kd','macd'],format_func=lambda k:{'volume':'成交量','kd':'KD','macd':'MACD','rsi':'RSI','boll':'布林通道'}[k])
            ma=st.multiselect('均線',[5,20,60,120,240],default=[20,60],format_func=lambda n:str(n)+{'D':'日','W':'週','M':'月'}[period])
            from .charts import kline
            fig=kline(ind,mas=ma,boll='boll' in panels,panels=[x for x in panels if x!='boll'],bars=252,dark=False,ma_unit=period)
        else:
            f=f.resample({'D':'D','W':'W-FRI','M':'ME'}[period]).last().dropna(subset=['close'])
            fig=go.Figure(go.Scatter(x=f.index,y=f.close,mode='lines',name='實際收盤',line_color='#087f76'))
            st.caption('目前僅有實際收盤序列，完整開高低量尚在補齊，因此先顯示折線。')
        st.plotly_chart(fig,width='stretch',config={'displaylogo':False})
    st.markdown('### 基本面與模型依據')
    a,b,c,d=st.columns(4);a.metric('月營收年增',f"{row.get('revenue_yoy'):+.1f}%" if pd.notna(row.get('revenue_yoy')) else '未取得')
    b.metric('月營收月增',f"{row.get('revenue_mom'):+.1f}%" if pd.notna(row.get('revenue_mom')) else '未取得')
    c.metric('基本每股盈餘',price(row.get('eps')));d.metric('本益比',price(row.get('pe')))
    st.caption('營收期別 '+str(row.get('revenue_date',''))+'｜財報 '+str(row.get('quality_period','')))
    with st.expander('十面向觀測與缺失明細'):
        st.dataframe(pd.DataFrame([{'面向':name,'觀測值':str(row.get(k)) if pd.notna(row.get(k)) else '待補資料','資料狀態':'有觀測' if pd.notna(row.get(k)) else '缺少，未當成0'} for k,name in NAMES.items()]),hide_index=True,width='stretch')
    with st.expander('法人、資券及資料日期',expanded=False):
        st.dataframe(pd.DataFrame([{'法人':name,'買賣超（張）':row.get(k)} for k,name in [('foreign','外資'),('trust','投信'),('dealer','自營商')]]).style.format({'買賣超（張）':'{:+,.0f}'},na_rep='未取得'),hide_index=True,width='stretch')
        known=[row.get(k) for k in ('foreign','trust','dealer')]
        if all(pd.notna(x) for x in known):st.write('三法人同步買超' if all(x>0 for x in known) else '三法人同步賣超' if all(x<0 for x in known) else '三法人方向分歧')
        st.caption('法人資料 '+str(row.get('inst_date','未取得'))+'；盤後日資料')
        st.write('融資餘額 '+price(row.get('mbal'))+'張｜融券 '+price(row.get('sbal'))+'張')
        st.caption('大戶／主力分點：尚未接入；不以法人或成交量替代大戶進出。')


def funding(market,h,rows):
    cap=st.number_input('投資資金（元）',min_value=10000,value=1_000_000,step=10000)
    name=st.selectbox('配置範例',list(PROFILES),index=list(PROFILES).index('純個股均衡'))
    w=PROFILES[name];st.caption('／'.join(k+' '+f'{v:.0%}' for k,v in w.items())+'。0050可以為0%。')
    chosen={};plans={};prices={};groups={}
    for hz in HZ:
        data=market.picks(hz);data=data.loc[data.eligible].head(10);chosen[hz]=[]
        for r in data.to_dict('records'):
            p=plan_for(market,r,hz,schedule=False)
            if p and signal_current(r['date']):
                t=r['ticker'];chosen[hz].append(t);plans[t]=p if t not in plans or p.alert>plans[t].alert else plans[t];prices[t]=plans[t].entry;groups[t]=r['group']
    target,ledger=allocation(cap,w,chosen,plans,prices,groups=groups)
    st.write(f'個股含費用 {ledger["stocks_including_fees"]:,.0f}元｜0050 {ledger["etf"]:,.0f}元｜現金 {ledger["cash"]:,.0f}元')
    if not target.empty:st.dataframe(target[['ticker','group','shares','amount','buy_low','buy_high','alert']],hide_index=True,width='stretch')
    else:st.caption('買區尚未完成或資料未夠新時，資金保留為現金，不會套用猜測價位。')
    st.caption('此為目標試算，須自行扣除既有持股；單股10%、同族群25%、每檔至防守風險0.5%。')


def dashboard(market):
    st.markdown('<div class="lab-hero"><span>01 / INVESTMENT DESK</span><h1>選股決策中心</h1><p>完整資訊、清楚順序：先看總表與策略證據，再查個股、價格和部位。</p></div>',unsafe_allow_html=True)
    with st.container(key='focus_controls'):
        a,b=st.columns(2)
        h=a.segmented_control('操作週期',list(HZ),format_func=HZ.get,default='mid',key='auto_h') or 'mid'
        auto=b.toggle('盤中每5秒刷新',value=True,key='auto_quotes_enabled')
    display=st.segmented_control('閱讀方式',['總表＋重點','完整總表','重點卡片'],default='總表＋重點',key='desk_display') or '總表＋重點'
    rows=market.picks(h);selected=st.session_state.get('auto_detail')
    if selected:
        match=rows.loc[rows.ticker.eq(selected)] if not rows.empty else rows
        if not match.empty:detail(market,match.iloc[0].to_dict(),h);return
    @st.fragment(run_every='5s' if auto else None)
    def board():
        market.refresh();data=market.picks(h);data=data.loc[data.eligible].head(10) if not data.empty else data
        from .lab_ui import laboratory
        lab=laboratory(str(ROOT));market.lab=lab
        lab.tick()
        if not market.payload.get('synthetic'):
            try:lab.registry.capture(market)
            except (OSError,ValueError):pass
        mode=phase();hub=quote_hub();qs=hub.get(data.to_dict('records'),enabled=auto and mode=='盤中')
        if not data.empty and mode=='盤中' and market.global_snapshot:
            from .global_markets import linked_score
            data['execution_score']=data.apply(lambda r:linked_score(r.score,r.group,market.global_snapshot),axis=1)
            data=data.sort_values('execution_score',ascending=False)
        if data.empty:
            st.info('正在自動取得市場資料。取得後會自動顯示推薦，無需匯入或下載檔案。');return
        st.caption(mode+' · '+market.status+' · 已初篩 '+str(len(market.picks(h)))+'檔 · 畫面 '+taipei().strftime('%H:%M:%S'))
        if mode=='盤中':st.caption('排程每5秒 · 最近收到報價 '+(hub.last_received[11:19] if hub.last_received else '等待來源回應')+' · '+('更新中' if hub.running else '使用實際成交時間判斷'))
        if hub.error and mode=='盤中':st.caption(hub.error)
        a,b,c,d=st.columns(4)
        a.metric('本週期候選',len(data));b.metric('平均因子涵蓋',f'{data.coverage.mean():.0%}')
        c.metric('模型狀態','已過研究閘門' if data.strategy_status.eq('研究閘門通過').all() else '初選觀察・未驗效')
        d.metric('研究進度',lab.state.get('status','等待研究'))
        if display!='重點卡片':
            full=[]
            for row in data.to_dict('records'):
                p=plan_for(market,row,h,schedule=False);q=qs.get(row['ticker'])
                full.append({'股票':row['ticker']+' '+row['name'],'族群':row['group'],'模型':row.get('strategy_status'),
                    '分數':row['score'],'涵蓋率':row['coverage'],'參考價':q.get('price') if q and quote_check(q)[0] else row['price'],
                    '買區':price(p.buy_low)+'～'+price(p.buy_high) if p else '待確認','防守':price(p.alert) if p else '待確認',
                    '入選助力':row['reasons'],'留意':row['risk']})
            st.dataframe(pd.DataFrame(full).style.format({'分數':'{:.1f}','涵蓋率':'{:.0%}','參考價':'{:,.2f}'},na_rep='待確認'),hide_index=True,width='stretch',height=390)
        for col,row in zip(st.columns(min(3,len(data))),data.head(3 if display!='完整總表' else 0).to_dict('records')):
            with col:
                with st.container(border=True):
                    p=plan_for(market,row,h);card(row,h,p,qs.get(row['ticker']))
                    if st.button('查看 '+row['name']+' 的圖表與判斷',key='auto_pick_'+row['ticker'],width='stretch'):
                        st.session_state['auto_detail']=row['ticker'];st.rerun()
        st.markdown('<div class="focus-guide"><div><span>01</span><b>讀原因</b><p>確認推薦助力、拖累因素及資料日期。</p></div><div><span>02</span><b>等確認</b><p>實際K線與有效成交齊全，才評估買區內的第一筆。</p></div><div><span>03</span><b>控部位</b><p>分批與分散配置，0050可選；資料未齊先保留資金。</p></div></div>',unsafe_allow_html=True)
        with st.expander('其他候選與個股查詢'):
            query=st.text_input('代號或公司名',key='auto_search',placeholder='例如2330、台積電')
            allrows=market.picks(h)
            match=allrows.loc[allrows.ticker.astype(str).str.contains(query,regex=False)|allrows['name'].str.contains(query,regex=False)] if query else data
            fields=['ticker','name','group','score','coverage','date','reasons']
            st.dataframe(match[fields].rename(columns={'ticker':'代號','name':'公司','group':'族群','score':'分數','coverage':'涵蓋率','date':'資料日','reasons':'入選依據'}),hide_index=True,width='stretch')
            if query and not match.empty:
                chosen=st.selectbox('開啟標的',match.ticker.tolist(),key='auto_search_match')
                if st.button('開啟個股分析'):
                    st.session_state['auto_detail']=chosen;st.rerun()
        with st.expander('配置我的資金（0050選用）'):
            if st.toggle('開啟配置試算',key='auto_funding'):funding(market,h,data)
        with st.expander('自動資料狀態'):
            st.caption('隨附真實快照 → 背景更新整批資料 → 漸進補齊K線。無需手動匯入。')
            st.dataframe(pd.DataFrame(market.payload.get('sources',[])),hide_index=True,width='stretch')
            if market.error:st.caption(market.error)
            if market.global_snapshot:
                from .global_markets import display_rows
                st.caption('海外情境：'+market.global_snapshot.note+'；最多12%用於盤中執行排序。')
                st.dataframe(display_rows(market.global_snapshot),hide_index=True,width='stretch')
            st.caption('各股缺少的財報、集保大戶與主力分點會明示缺少，不填入假數字。')
    board()


def research(market):
    from .lab_ui import workspace
    workspace(market,ROOT)
    return
    record=audit_record(market,st.session_state.get('auto_h','mid'))
    st.markdown('<div class="focus-conclusion"><span>目前研究結論</span><h2>'+esc(record['conclusion'])+'</h2><p>'+esc(record['note'])+'</p></div>',unsafe_allow_html=True)
    st.download_button('下載完整研究報告',report_html(record),'AlphaRadar_Research_Report.html','text/html',type='primary')
    st.download_button('下載研究數據 JSON',json.dumps(safe(record),ensure_ascii=False,indent=2),'AlphaRadar_Research_Data.json','application/json')
    with st.expander('十面向因子與短中長線權重',expanded=True):
        table=pd.DataFrame({'面向':list(NAMES.values()),**{HZ[h]:list(w.values()) for h,w in WEIGHTS.items()}})
        st.dataframe(table.style.format({HZ[h]:'{:.0%}' for h in HZ}),hide_index=True,width='stretch')
        st.caption('財報品質採最新可用淨利率並依同業比較；缺值中性處理，長期趨勢須等足夠歷史資料。')
    with st.expander('測試驗證狀態'):
        checks=[('資料取得','自動整批公開資料與真實啟動快照'),('選股資料檢核','日期、流動性、缺值、因子涵蓋率'),('盤中更新','每5秒排程、共享快取、真實成交時間、失敗保留前次資料'),('完整投資績效','待使用歷史時點因子驗證，沒有套用舊模型的績效')]
        st.dataframe(pd.DataFrame(checks,columns=['項目','狀態']),hide_index=True,width='stretch')
        for note in record['limitations']:st.write('・'+note)
    with st.expander('資料品質與來源'):
        st.json(record['quality'])


def main():
    st.set_page_config(page_title='Alpha Radar PRO｜自動選股',page_icon='▥',layout='wide',initial_sidebar_state='collapsed')
    st.markdown(css(False),unsafe_allow_html=True)
    market=service(str(ROOT),os.getenv('ALPHA_RADAR_OFFLINE_QA')!='1')
    st.markdown('<div class="desk-top"><div><div class="desk-wordmark">ALPHA RADAR <span>PRO</span></div><div class="desk-product">投資決策 · 策略研究 · 持續驗效</div></div><div class="desk-meta">V29 STRATEGY LAB<br>'+esc(phase())+'</div></div>',unsafe_allow_html=True)
    page=st.radio('主要區塊',['選股儀表板','模型測試驗證'],horizontal=True,label_visibility='collapsed',key='desk_section')
    if page=='選股儀表板':dashboard(market)
    else:research(market)
    st.markdown('<div class="desk-footer">ALPHA RADAR PRO · 依實際可得資料產生投資觀察，分數不是勝率。每5秒為刷新排程，成交時間與上游回應另行顯示；系統不自動下單。</div>',unsafe_allow_html=True)
