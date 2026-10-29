"""Full research workspace under one primary navigation entry."""
from __future__ import annotations
import json
import pandas as pd
import streamlit as st
from .strategy_lab import Lab,HORIZONS,factor_diagnostics
from .auto_market import NAMES,WEIGHTS,audit_record,safe
from .auto_report import render as snapshot_report
from .desk_plan import HZ
from .desk_style import title,esc
from .lab_report import render


@st.cache_resource(show_spinner=False)
def laboratory(root):return Lab(root)


def workspace(market,root):
    lab=laboratory(str(root));ready=lab.discover()
    st.markdown('<div class="focus-eyebrow">02 / RESEARCH & VALIDATION</div>'+title('策略驗效與優化中心','讓因子與權重接受同條件比較：淨報酬、回撤、穩定性、成本壓力都要看。'),unsafe_allow_html=True)
    section=st.segmented_control('研究工作區',['驗效總覽','因子研究','策略競賽','研究報告'],default='驗效總覽',key='lab_section') or '驗效總覽'
    continuous=st.toggle('持續研究：背景補資料並分批搜尋',value=lab.registry.get('continuous',False),key='lab_continuous')
    if continuous!=lab.registry.get('continuous',False):
        lab.registry.set('continuous',continuous)
        if not continuous:lab.pause()
    lab.tick()
    status=lab.report();rows=status['trials']
    if section=='驗效總覽':
        a,b,c,d=st.columns(4)
        a.metric('本版歷史試驗',len(rows));b.metric('正式可採用週期',sum(bool(x and x.get('deployable')) for x in status['champions'].values()))
        c.metric('研究資料','已就緒' if ready['ready'] else '待補齊');d.metric('驗效狀態','研究中' if lab.worker and lab.worker.is_alive() else '尚待證據' if not rows else '有結果待審核')
        if not rows:st.warning('目前沒有本版投資績效驗證結果。快照、固定權重及程式測試不能證明報酬。')
        overview=[]
        for h in HORIZONS:
            seal=status['champions'].get(h);m=(seal or {}).get('metric',{})
            overview.append({'週期':HZ[h],'已試驗':sum(r['recipe']['horizon']==h for r in rows),
                '保留期年化':m.get('cagr'),'同期0050':m.get('bench_cagr'),'超額':m.get('excess_cagr'),
                '最大回撤':m.get('mdd'),'結論':'可採用' if seal and seal.get('deployable') else '研究候選' if seal else '尚未驗效'})
        view=pd.DataFrame(overview)
        for k in ['保留期年化','同期0050','超額','最大回撤']:view[k]=view[k].map(lambda v:f'{v:+.1%}' if pd.notna(v) else '待測')
        st.dataframe(view,hide_index=True,width='stretch')
        st.info('追求的是「指定風險與成本條件下，樣本外淨報酬最高的候選」。完整試驗紀錄保留；不承諾未來最高報酬。')
        _progress(lab)
        with st.expander('研究資料背景建置與品質閘門',expanded=not ready['ready']):
            st.write(ready['reason'])
            st.caption('程式自動建立價量、法人、資券、估值及營收歷史；各批可續傳，首頁繼續使用。財報實際公告日與歷史名冊未核實，不能自動升為正式策略。')
            a,b=st.columns(2)
            if a.button('開始／接續背景建置',key='lab_build',width='stretch'):lab.build();st.rerun()
            if b.button('暫停研究工作',key='lab_pause',width='stretch'):lab.pause();st.rerun()
            st.caption('每資料群組最多5分鐘一批；可在批次完成後暫停。初期多年資料建置需要時間，不阻擋選股介面。')
    elif section=='因子研究':
        h=st.segmented_control('研究週期',list(HZ),format_func=HZ.get,default='mid',key='lab_factor_h') or 'mid'
        if ready['ready']:
            if st.button('計算開發期因子診斷',type='primary'):
                with st.spinner('只使用保留期之前、標籤已成熟的樣本…'):
                    st.session_state['lab_factor_result']={'study':lab.study,'horizon':h,'rows':factor_diagnostics(lab.B,lab.cfg,h)}
            results=st.session_state.get('lab_factor_result')
            if results and results['study']==lab.study and results['horizon']==h:
                st.dataframe(pd.DataFrame(results['rows']).rename(columns={'label':'因子','family':'族群','ic_mean':'平均IC','ic_ir':'ICIR','coverage':'涵蓋率','n':'有效樣本'}),hide_index=True,width='stretch')
                st.caption('IC/ICIR是研究診斷，不是勝率；實際權重仍須經組合回測、成本及穩定性比較。')
        else:st.info('完整因子研究等待歷史資料。目前可以檢查快照各面向的缺漏，不能據此推估歷史IC。')
        data=market.picks(h);audit=[]
        for k,name in NAMES.items():
            valid=int(data[k].notna().sum()) if k in data else 0
            audit.append({'快照面向':name,'固定先驗權重':WEIGHTS[h][k],'有觀測檔數':valid,'實際涵蓋':valid/max(len(data),1),'是否最佳權重':'尚未經驗效證實'})
        st.dataframe(pd.DataFrame(audit).style.format({'固定先驗權重':'{:.0%}','實際涵蓋':'{:.0%}'}),hide_index=True,width='stretch')
        st.caption('研究引擎恢復使用完整因子庫：成長、估值、技術、籌碼與市場行為；不能只把十個面向當成十個固定因子。')
    elif section=='策略競賽':
        a,b=st.columns([2,1]);hs=a.multiselect('研究週期',list(HZ),default=list(HZ),format_func=HZ.get)
        budget=b.selectbox('本批每週期候選',[4,8,16,32,48],index=2)
        st.caption('候選涵蓋不同母池、精簡因子數、動能／成長融合、續抱緩衝、現金或0050餘款；選型只看開發期樣本外。')
        seal=st.checkbox('本批完成後鎖定開發期冠軍，檢查保留期一次',value=False)
        a,b=st.columns(2)
        if a.button('開始／接續策略競賽',type='primary',width='stretch'):
            lab.start(horizons=hs or HORIZONS,budget=budget,seal=seal);st.rerun()
        if b.button('暫停（結果保留）',width='stretch'):lab.pause();st.rerun()
        if not ready['ready']:st.info(ready['reason'])
        _progress(lab)
        board=[]
        for r in rows:
            m=r.get('metric',{});p=r['recipe']
            board.append({'週期':HZ[p['horizon']],'候選':p['id'],'母池':p['rule']+str(p['size']),
                '因子數':p['model'].get('k'),'開發期淨年化':m.get('cagr'),'同期0050':m.get('bench_cagr'),
                '超額':m.get('excess_cagr'),'最大回撤':m.get('mdd'),'區段勝率':m.get('fold_win_rate'),
                '成本壓力超額':m.get('stress_excess'),'可列冠軍':'是' if r.get('selection_eligible') else '否',
                '狀態':r.get('error') or '已完成'})
        if board:
            frame=pd.DataFrame(board).sort_values('開發期淨年化',ascending=False,na_position='last')
            st.dataframe(frame.style.format({k:'{:+.1%}' for k in ['開發期淨年化','同期0050','超額','最大回撤','區段勝率','成本壓力超額']},na_rep='—'),hide_index=True,width='stretch')
            choice=st.selectbox('檢視試驗完整記錄',[r['recipe']['id'] for r in rows])
            result=next(r for r in rows if r['recipe']['id']==choice);_curve(result.get('nav'))
            with st.expander('逐段成效、模型配方與歷次權重'):
                st.json({k:v for k,v in result.items() if k!='nav'})
        else:st.caption('尚無已完成試驗，不填入示範報酬。')
    else:
        st.write(status['status']);st.caption(status['objective'])
        st.download_button('下載驗效與優化研究報告',render(status,audit_record(market)),'AlphaRadar_V29_Validation_Report.html','text/html',type='primary')
        st.download_button('下載完整試驗紀錄 JSON',json.dumps(safe(status),ensure_ascii=False,indent=2),'AlphaRadar_V29_Trials.json','application/json')
        for note in status['limitations']:st.write('・'+note)
        with st.expander('原快照資料檢核（與投資績效分開）'):
            st.download_button('下載資料檢核報告',snapshot_report(audit_record(market)),'AlphaRadar_Data_Audit.html','text/html')


@st.fragment(run_every='3s')
def _progress(lab):
    lab.tick()
    state=lab.state;total=max(1,state.get('total',0));done=state.get('done',0)
    st.progress(min(1.,done/total),text=state.get('status','等待研究')+f' · {done}/{state.get("total",0)}')
    st.caption(state.get('message',''))


def _curve(data):
    if not data:return
    import plotly.graph_objects as go
    fig=go.Figure()
    for key,name,color in [('strategy','策略','#0b8e85'),('benchmark','0050','#dca54b')]:
        values=data.get(key,[])
        if values and values[0]:fig.add_trace(go.Scatter(x=data['date'],y=[x/values[0] for x in values],name=name,line_color=color))
    fig.update_layout(height=330,margin=dict(l=10,r=20,t=15,b=15),paper_bgcolor='white',plot_bgcolor='white',legend=dict(orientation='h'))
    st.plotly_chart(fig,width='stretch')
