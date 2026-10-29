"""Persistent, chronological strategy research. No snapshot-only 'backtest'."""
from __future__ import annotations
from dataclasses import asdict,replace
from pathlib import Path
from contextlib import contextmanager
import copy,hashlib,json,sqlite3,threading,time
import numpy as np
import pandas as pd
from .auto_market import safe,now
from .config import load_config
from .desk_research import bundle_identity
from .research import Research,Variant,HKEY
from .backtest import run
from .metrics import perf,deflated_sharpe
from .ten_dimension import blend_weights

HORIZONS=('short','mid','long')
VERSION='V29-LAB-1'


def digest(value):return hashlib.sha256(json.dumps(safe(value),sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()


def candidate_set(cfg,h,limit=48):
    """Predeclared search space. No new candidate is constructed from holdout results."""
    base_cfg=cfg['horizons'][h]['model'];out=[]
    for rule,size in [('BLEND',300),('BLEND',500),('ADV',300),('MCAP',500)]:
        for mode,k,hyp,prior,residual in [('baseline',5,.5,0,'bench'),('sparse',3,0,0,'cash'),
              ('sparse',5,.3,0,'cash'),('sparse',8,.5,0,'cash'),('sparse',5,.5,.2,'cash'),('sparse',6,.7,0,'cash')]:
            config=copy.deepcopy(base_cfg)
            if mode!='baseline':config.update(mode='sparse',k=k,tmin=1.0 if h=='long' else 2.0,hyp_blend=hyp)
            for hysteresis in ([2.0,2.5] if mode!='baseline' else [cfg['horizons'][h]['hysteresis']]):
                recipe={'horizon':h,'rule':rule,'size':size,'model':config,'prior_blend':prior,
                        'hysteresis':hysteresis,'residual':residual,'family':mode}
                recipe['id']=digest(recipe)[:18];out.append(recipe)
    # Interleave pools and families; a small first batch is not one pool only.
    out.sort(key=lambda r:(r['family']!='baseline',r['hysteresis'],r['model'].get('k',5),r['rule'],r['size']))
    return out[:limit]


class Registry:
    def __init__(self,root):
        self.path=Path(root)/'artifacts'/'strategy_lab.sqlite';self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.db() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS trials(study TEXT,horizon TEXT,id TEXT,result TEXT,PRIMARY KEY(study,horizon,id));
            CREATE TABLE IF NOT EXISTS seals(study TEXT,horizon TEXT,winner TEXT,result TEXT,PRIMARY KEY(study,horizon));
            CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY,value TEXT);
            CREATE TABLE IF NOT EXISTS observations(day TEXT PRIMARY KEY,captured_at TEXT,payload TEXT);''')

    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=20);db.execute('PRAGMA journal_mode=WAL')
        try:
            yield db;db.commit()
        except BaseException:
            db.rollback();raise
        finally:db.close()

    def set(self,key,value):
        with self.db() as db:db.execute('INSERT OR REPLACE INTO state VALUES(?,?)',(key,json.dumps(safe(value),ensure_ascii=False)))

    def get(self,key,default=None):
        with self.db() as db:r=db.execute('SELECT value FROM state WHERE key=?',(key,)).fetchone()
        return json.loads(r[0]) if r else default

    def rows(self,study=None,h=None):
        sql='SELECT result FROM trials';args=[];where=[]
        if study:where.append('study=?');args.append(study)
        if h:where.append('horizon=?');args.append(h)
        if where:sql+=' WHERE '+' AND '.join(where)
        with self.db() as db:rows=db.execute(sql,args).fetchall()
        return [json.loads(r[0]) for r in rows]

    def save(self,study,h,result):
        with self.db() as db:db.execute('INSERT OR REPLACE INTO trials VALUES(?,?,?,?)',(study,h,result['recipe']['id'],json.dumps(safe(result),ensure_ascii=False)))

    def seal(self,study,h,winner,result):
        # INSERT only: once a holdout is inspected, a later trial cannot replace its winner.
        with self.db() as db:
            prior=db.execute('SELECT study,result FROM seals WHERE horizon=?',(h,)).fetchall()
            for other,payload in prior:
                old=json.loads(payload)
                if other!=study and result.get('from') and old.get('to') and result['from']<=old['to']:
                    result={**result,'deployable':False,'overlapping_holdout':True,
                            'reason':'保留期與既有研究重疊，只列事後研究追蹤，不視為全新盲測。'}
            db.execute('INSERT OR IGNORE INTO seals VALUES(?,?,?,?)',(study,h,winner,json.dumps(safe(result),ensure_ascii=False)))
            r=db.execute('SELECT winner,result FROM seals WHERE study=? AND horizon=?',(study,h)).fetchone()
        return {'winner':r[0],**json.loads(r[1])}

    def sealed(self,study,h):
        with self.db() as db:r=db.execute('SELECT winner,result FROM seals WHERE study=? AND horizon=?',(study,h)).fetchone()
        return {'winner':r[0],**json.loads(r[1])} if r else None

    def capture(self,market):
        """Collect actual observed facts for future PIT research; never backdate retrieval."""
        captured=now();day=captured[:10]
        dates={str(x.get('date',''))[:10] for x in market.payload.get('price',[])}
        if day not in dates:return False
        # Store only after the close. Preserve the first observed snapshot of a date.
        if pd.Timestamp(captured).hour<15:return False
        with self.db() as db:
            if db.execute('SELECT 1 FROM observations WHERE day=?',(day,)).fetchone():return False
        payload={'sources':market.payload.get('sources',[]),'price':market.payload.get('price',[]),
                 'features':{h:safe(market.picks(h).to_dict('records')) for h in HORIZONS}}
        with self.db() as db:db.execute('INSERT OR IGNORE INTO observations VALUES(?,?,?)',(day,captured,json.dumps(payload,ensure_ascii=False)))
        return True


def readiness(B):
    if B is None:return {'ready':False,'reason':'歷史研究資料尚未建立；首頁快照不是可用的歷史驗效資料。'}
    minimum={'U','FWD','R','OC','OK','RANKS','TRADE','CAP','BENCH','STAGE','DTOP','WSUP','MKT'}
    missing=minimum-set(B.a)
    if missing:return {'ready':False,'reason':'研究欄位不足：'+','.join(sorted(missing))}
    dates=B.sig_dates;years=(dates[-1]-dates[0]).days/365.25
    if years<3:return {'ready':False,'reason':f'歷史長度{years:.1f}年，不足本研究最低3年。'}
    days=B.days;span=max((days[-1]-days[0]).days/365.25,1/365.25)
    if len(days)/span<200 or (len(days)>1 and np.max(np.diff(days.values).astype('timedelta64[D]').astype(int))>20):
        return {'ready':False,'reason':'歷史交易日過於稀疏或有超過20日缺口，不以零報酬或停牌假設補成完整回測。'}
    return {'ready':True,'synthetic':bool(B.meta.get('synthetic')),'years':years,
            'reason':'合成資料僅測流程' if B.meta.get('synthetic') else '可進行歷史研究；正式採用仍需品質閘門'}


def _setup(B,cfg,recipe):
    settings=copy.deepcopy(cfg);h=recipe['horizon'];settings['horizons'][h]['model']=recipe['model']
    settings['horizons'][h]['hysteresis']=recipe['hysteresis'];settings['horizons'][h]['residual']=recipe['residual']
    research=Research(B,settings,log=lambda *a:None);v=research.model_variant(h)
    rule=recipe['rule'] if recipe['rule'] in B.meta['rules'] else B.meta['rules'][0]
    weights,history=research.schedule(rule,recipe['size'],h,v)
    if recipe['prior_blend']:
        weights=[None if w is None else blend_weights(w,B.factors,h,recipe['prior_blend']) for w in weights]
    return research,v,rule,weights,history


def development_metrics(nav,bench,boundary,fold_days=126):
    """Selection helper accepts ONLY development NAV. Holdout cannot influence ordering."""
    dev=nav.loc[nav.index<pd.Timestamp(boundary)];b=bench.reindex(dev.index)
    if len(dev)<250:raise ValueError('開發期樣本外不足250個交易日')
    metrics=perf(dev,b);folds=[]
    for i in range(0,len(dev)-62,fold_days):
        chunk=dev.iloc[i:min(len(dev),i+fold_days+1)]
        if len(chunk)<63:continue
        x=perf(chunk,b.reindex(chunk.index));folds.append({'from':str(chunk.index[0].date()),'to':str(chunk.index[-1].date()),**x})
    valid=[f['excess_cagr'] for f in folds if np.isfinite(f.get('excess_cagr',np.nan))]
    metrics['fold_win_rate']=float(np.mean(np.array(valid)>0)) if valid else None
    metrics['fold_count']=len(valid);return metrics,folds,dev,b


def evaluate(B,cfg,recipe):
    research,v,rule,weights,history=_setup(B,cfg,recipe);h=recipe['horizon']
    boundary=B.sig_dates[min(research.holdout,len(B.sig_dates)-1)]
    # Historical schedule is purged by label maturity in Research.train_rows.
    # Zero future scheduled weights during candidate competition.
    dev_weights=[w if i<research.holdout else None for i,w in enumerate(weights)]
    spec=research.spec(h,v);view=research.view(rule,recipe['size'])
    result=run(B,view,dev_weights,spec,start_i=research.first_oos)
    metric,folds,nav,bench=development_metrics(result.nav,result.bench,boundary)
    stress=run(B,view,dev_weights,replace(spec,buy_cost=spec.buy_cost+.0025,sell_cost=spec.sell_cost+.0025),start_i=research.first_oos)
    stress_metric=perf(stress.nav.loc[stress.nav.index<boundary],stress.bench)
    metric.update(stress_cagr=stress_metric.get('cagr'),stress_excess=stress_metric.get('excess_cagr'))
    # Original schedule supplies only model fit history, not future performance.
    history=[x for x in history if x['from']<str(boundary.date())]
    if recipe['prior_blend']:
        for entry in history:
            w=blend_weights([entry['weights'].get(f,0.) for f in B.factors],B.factors,h,recipe['prior_blend'])
            entry['weights']={f:float(x) for f,x in zip(B.factors,w) if abs(x)>1e-8}
    qualified=bool(metric.get('mdd',-1)>=-.45 and metric.get('fold_count',0)>=3 and
        (metric.get('fold_win_rate') or 0)>=.5 and (metric.get('stress_excess') or -1)>0)
    return safe({'recipe':recipe,'metric':metric,'folds':folds,'selection_eligible':qualified,
        'objective':metric.get('cagr') if qualified else None,'weights_history':history,
        'selection_weights':history[-1]['weights'] if history else {},
        'created_at':now(),'holdout_start':str(boundary.date()),'synthetic':bool(B.meta.get('synthetic')),
        'nav':{'date':[str(d.date()) for d in nav.index],'strategy':nav.tolist(),'benchmark':bench.tolist()},
        'note':'候選只依開發期樣本外評比；保留期不參與選型。'})


def choose_winner(results):
    valid=[r for r in results if r.get('selection_eligible') and r.get('objective') is not None]
    return max(valid,key=lambda r:(r['objective'],r['metric'].get('sharpe') or -99,r['recipe']['id'])) if valid else None


def holdout(B,cfg,recipe):
    research,v,rule,weights,_=_setup(B,cfg,recipe)
    result=run(B,research.view(rule,recipe['size']),weights,research.spec(recipe['horizon'],v),start_i=research.first_oos)
    boundary=B.sig_dates[min(research.holdout,len(B.sig_dates)-1)]
    # Carry capital/positions across the boundary; include previous close for first test-day return.
    at=int(result.nav.index.searchsorted(boundary));nav=result.nav.iloc[max(0,at-1):]
    metric=perf(nav,result.bench);tests=len(nav)-1
    passed=bool(tests>=120 and (metric.get('excess_cagr') or -1)>0 and metric.get('mdd',-1)>=-.45)
    quality=B.meta.get('research_provenance',{})
    deployable=passed and not B.meta.get('synthetic') and all(quality.get(k) is True for k in ('pit_verified','universe_verified','corporate_actions_verified'))
    latest=research.final_fit(rule,recipe['size'],recipe['horizon'],v).weights
    if recipe['prior_blend']:latest=blend_weights(latest,B.factors,recipe['horizon'],recipe['prior_blend'])
    return safe({'metric':metric,'passed':passed,'deployable':bool(deployable),'recipe':recipe,
        'horizon':recipe['horizon'],'from':str(nav.index[0].date()),'to':str(nav.index[-1].date()),
        'latest_weights':{f:float(w) for f,w in zip(B.factors,latest) if abs(w)>1e-8},
        'reason':'歷史門檻通過且品質證據齊全' if deployable else '僅為研究候選；保留期或資料品質證據未達正式採用要求',
        'nav':{'date':[str(d.date()) for d in nav.index],'strategy':nav.tolist(),'benchmark':result.bench.reindex(nav.index).tolist()},
        'trials_note':'保留期僅評估先前鎖定候選；失敗不依同一保留期輪流換冠軍。'})


def factor_diagnostics(B,cfg,h,rule='BLEND',size=500):
    research=Research(B,cfg,log=lambda *a:None);rule=rule if rule in B.meta['rules'] else B.meta['rules'][0]
    ic=research.ic(rule,size,h);positions=np.arange(research.first_oos,research.holdout)
    # Only matured labels ending before the holdout boundary enter this table.
    positions=positions[B.sig_pos[positions]+research.H(h)+1<B.sig_pos[research.holdout]]
    out=[]
    for j,f in enumerate(B.factors):
        vals=ic[positions,j];vals=vals[np.isfinite(vals)]
        out.append({'factor':f,'label':B.meta['factor_zh'][j],'family':B.meta['families'][j],
            'n':len(vals),'ic_mean':float(vals.mean()) if len(vals) else None,
            'ic_ir':float(vals.mean()/vals.std()) if len(vals)>1 and vals.std()>0 else None,
            'coverage':B.meta.get('coverage',{}).get(f)})
    return safe(out)


class Lab:
    def __init__(self,root):
        self.root=Path(root);self.registry=Registry(root);self.lock=threading.RLock();self.worker=None;self.stop_event=threading.Event()
        self.state=self.registry.get('progress',{'status':'等待歷史研究資料','done':0,'total':0,'message':'目前僅有快照，尚不能驗證投資績效。'})
        self.B=None;self.cfg=None;self.study=None
        self.last_auto=-1e9

    def update(self,**values):
        with self.lock:self.state={**self.state,**values,'updated_at':now()};self.registry.set('progress',self.state)

    def discover(self):
        from .bundle import Bundle
        paths=[self.root/'artifacts'/'research_bundle.npz',self.root/'artifacts'/'bundle.npz']
        for p in paths:
            if not p.is_file():continue
            stamp=(str(p),p.stat().st_mtime_ns)
            if getattr(self,'_stamp',None)==stamp:return readiness(self.B)
            try:
                B=Bundle.load(p);status=readiness(B)
                if not status['ready']:continue
                self.B=B;self.cfg=load_config();self.study=digest({'data':bundle_identity(B),'cfg':self.cfg,'protocol':VERSION})
                self._stamp=stamp;self.registry.set('study',{'id':self.study,'data_id':bundle_identity(B),'synthetic':bool(B.meta.get('synthetic')),'path':str(p)})
                return status
            except (ValueError,OSError,KeyError):continue
        return readiness(None)

    def start(self,horizons=HORIZONS,budget=16,seal=False):
        if self.worker and self.worker.is_alive():return False
        status=self.discover()
        if not status['ready']:self.update(status='資料未就緒',message=status['reason']);return False
        self.stop_event.clear()
        def work():
            try:
                total=budget*len(horizons);done=0;self.update(status='研究執行中',done=0,total=total,message='只比較開發期樣本外，保留期不參與搜索')
                for h in horizons:
                    known={r['recipe']['id'] for r in self.registry.rows(self.study,h)}
                    recipes=[r for r in candidate_set(self.cfg,h) if r['id'] not in known][:budget]
                    for recipe in recipes:
                        if self.stop_event.is_set():self.update(status='已暫停',message='結果已保存，可接續');return
                        self.update(horizon=h,candidate=recipe['id'],message=f'{h}｜{recipe["rule"]}{recipe["size"]}｜{recipe["model"].get("mode")}')
                        try:r=evaluate(self.B,self.cfg,recipe)
                        except Exception as e:r={'recipe':recipe,'error':str(e),'selection_eligible':False,'objective':None}
                        self.registry.save(self.study,h,r);done+=1;self.update(done=done)
                    if seal and not self.registry.sealed(self.study,h):
                        winner=choose_winner(self.registry.rows(self.study,h))
                        if winner:
                            trial_rows=self.registry.rows(self.study,h);ratios=[]
                            for trial in trial_rows:
                                nav=trial.get('nav',{}).get('strategy',[])
                                returns=pd.Series(nav,dtype=float).pct_change().dropna()
                                if len(returns)>30 and returns.std()>0:ratios.append(float(returns.mean()/returns.std()))
                            nav=winner['nav']['strategy'];returns=pd.Series(nav,dtype=float).pct_change().dropna()
                            dsr=deflated_sharpe(returns,len(trial_rows),float(np.std(ratios))) if len(ratios)>1 else np.nan
                            result=holdout(self.B,self.cfg,winner['recipe'])
                            result['multiple_testing']={'trials':len(trial_rows),'deflated_sharpe_probability':float(dsr) if np.isfinite(dsr) else None}
                            result['deployable']=bool(result['deployable'] and np.isfinite(dsr) and dsr>=.95)
                            if not result['deployable']:result['reason']='保留期、資料品質或多重試驗校正未全數通過，維持研究候選'
                            self.registry.seal(self.study,h,winner['recipe']['id'],result)
                self.update(status='本批研究完成',done=done,message='可擴充下一批候選；已查閱的保留期鎖定，不用它反覆選型')
            except Exception as e:self.update(status='研究中斷，可接續',message=str(e))
        self.worker=threading.Thread(target=work,daemon=True,name='strategy-lab');self.worker.start();return True

    def build(self,budget_minutes=5):
        if self.worker and self.worker.is_alive():return False
        self.stop_event.clear()
        def work():
            try:
                from .build import Builder
                from .store import Store
                from .panel import build_panel
                from .bundle import build_bundle
                cfg=load_config(overrides={'data':{'dir':str(self.root/'data')}})
                self.update(status='背景建置研究資料',message='先價量，再籌碼及基本面；各批可續傳，儀表板繼續使用。')
                for group in ('price','institutional','margin','valuation','misc'):
                    if self.stop_event.is_set():self.update(status='資料建置已暫停');return
                    Builder(cfg,group,budget_minutes=budget_minutes,log=lambda m:self.update(message=str(m))).run()
                store=Store(cfg['data']['dir']);prices=store.read('price')
                dense=(not prices.empty and prices.date.nunique()/max((prices.date.max()-prices.date.min()).days/365.25,1)>=200)
                if prices.empty or (prices.date.max()-prices.date.min()).days<365*3 or not dense:
                    self.update(status='本批資料已保存',message='歷史不足3年；可接續背景建置，尚不啟動績效搜索。');return
                B=build_bundle(build_panel(store),cfg,log=lambda m:self.update(message=str(m)))
                B.save(self.root/'artifacts'/'research_bundle.npz');self.update(status='研究資料已建立',message='可啟動候選比較；PIT及名冊證據未齊不自動採用')
            except Exception as e:self.update(status='資料建置中斷，可接續',message=str(e))
        self.worker=threading.Thread(target=work,daemon=True,name='research-data');self.worker.start();return True

    def pause(self):self.stop_event.set();self.update(message='將在目前批次／候選完成後暫停')

    def tick(self):
        if not self.registry.get('continuous',False) or (self.worker and self.worker.is_alive()) or time.monotonic()-self.last_auto<60:return
        self.last_auto=time.monotonic()
        if not self.discover()['ready']:self.build(budget_minutes=1);return
        incomplete=[h for h in HORIZONS if len(self.registry.rows(self.study,h))<len(candidate_set(self.cfg,h))]
        if incomplete:self.start(incomplete,budget=8,seal=False)
        else:self.update(status='候選已完成，等待新資料',message='不反覆使用同一保留期挑冠軍；新資料到齊後另建可識別批次。')

    def active_key(self,h):
        if not self.study:return ''
        seal=self.registry.sealed(self.study,h)
        return seal['winner'] if seal and seal.get('deployable') else ''

    def live_records(self,payload,h,frames):
        from .auto_market import screen
        from .backtest import choose
        from .desk_plan import signal_current
        from .research import factor_phrase
        if self.B is None or not self.study:return None
        seal=self.registry.sealed(self.study,h)
        if not seal or not seal.get('deployable') or not signal_current(str(self.B.sig_dates[-1].date())):return None
        recipe=seal['recipe'];settings=copy.deepcopy(self.cfg);settings['horizons'][h]['model']=recipe['model']
        settings['horizons'][h]['hysteresis']=recipe['hysteresis'];settings['horizons'][h]['residual']=recipe['residual']
        research=Research(self.B,settings,log=lambda *a:None);v=research.model_variant(h)
        rule=recipe['rule'] if recipe['rule'] in self.B.meta['rules'] else self.B.meta['rules'][0]
        view=research.view(rule,recipe['size']);w=np.array([seal['latest_weights'].get(f,0.) for f in self.B.factors])
        picks,_,scores=choose(self.B,view,len(self.B.sig_dates)-1,w,[],research.spec(h,v))
        base=screen(payload,h,frames).set_index('ticker');idx=view.members[-1];pct=pd.Series(scores).rank(pct=True)*100;out=[]
        for rank,j in enumerate(picks,1):
            t=self.B.tickers[j]
            if t not in base.index:continue
            r=base.loc[t].to_dict();k=int(np.where(idx==j)[0][0]);contrib=view.Z[-1][k]*w
            reasons=[factor_phrase(self.B,f,view.Z[-1][k,f]) for f in np.argsort(-contrib)[:3] if contrib[f]>0]
            r.update(ticker=t,rank=rank,score=float(pct[j]),reasons='、'.join(reasons),eligible=True,
                strategy_status='研究閘門通過',model_id=seal['winner'],factor_asof=str(self.B.sig_dates[-1].date()),
                coverage=float(((self.B.a['U'][-1,j]>0)*np.abs(w)).sum()/max(np.abs(w).sum(),1e-12)))
            out.append(r)
        return pd.DataFrame(out) if out else None

    def report(self):
        status=self.discover();rows=self.registry.rows(self.study) if self.study else []
        return safe({'product':'V29 STRATEGY LAB','generated_at':now(),'readiness':status,'study':self.study,
            'progress':self.state,'trial_count':len(rows),'trials':rows,
            'champions':{h:self.registry.sealed(self.study,h) if self.study else None for h in HORIZONS},
            'status':'有歷史研究結果，尚須依品質閘門判斷採用' if rows else '尚無本版投資績效驗證結果',
            'objective':'在成本、最大回撤、區段穩定性及成本壓力條件下，開發期樣本外淨年化報酬最高的候選',
            'limitations':['最高僅限本次候選集合及歷史期間，不是未來最高報酬保證。','快照與程式測試不算投資績效證據。',
                '營收代理公告日、歷史名冊及企業行動未核實前，不自動晉升正式策略。',
                '同一保留期一旦檢視即鎖定；增加試驗次數必須披露，不能只展示最佳一次。']})
