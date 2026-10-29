"""Walk-forward comparison of the source recipe and V27 ten-dimension blend."""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
from .backtest import run
from .desk_models import POOL_DEFAULT
from .research import Research
from .ten_dimension import blend_weights,BLEND
from .desk_research import bundle_identity,recipe_identity

def _metric(segment,key):
    value=segment.get(key)
    return None if value is None or not np.isfinite(value) else float(value)

def validate(bundle,cfg,progress=lambda m:None):
    data_id=bundle_identity(bundle)
    research=Research(bundle,cfg,log=lambda *a:None);rows=[]
    for h in ('short','mid','long'):
        rule,size=POOL_DEFAULT[h]
        override=(cfg.get('desk') or {}).get('pools',{}).get(h,{})
        rule=override.get('rule',rule);size=int(override.get('size',size))
        if rule not in bundle.meta['rules']:rule=bundle.meta['rules'][0]
        v=research.model_variant(h);weights,_=research.schedule(rule,size,h,v)
        enhanced=[None if w is None else blend_weights(w,bundle.factors,h) for w in weights]
        spec=research.spec(h,v);view=research.view(rule,size)
        source=research.segments(run(bundle,view,weights,spec,start_i=research.first_oos))
        v27=research.segments(run(bundle,view,enhanced,spec,start_i=research.first_oos))
        windows={}
        for name in ('dev','holdout','oos'):
            a,b=source[name],v27[name]
            windows[name]={"source_cagr":_metric(a,'cagr'),"v27_cagr":_metric(b,'cagr'),
                "delta_cagr":None if _metric(a,'cagr') is None or _metric(b,'cagr') is None else _metric(b,'cagr')-_metric(a,'cagr'),
                "source_mdd":_metric(a,'mdd'),"v27_mdd":_metric(b,'mdd'),
                "source_ir":_metric(a,'info_ratio'),"v27_ir":_metric(b,'info_ratio'),
                "bench_cagr":_metric(b,'bench_cagr'),"years":_metric(b,'years')}
        deltas=[x['delta_cagr'] for x in windows.values() if x['delta_cagr'] is not None]
        mdd_oos=windows['oos'];mdd_ok=(mdd_oos['source_mdd'] is not None and mdd_oos['v27_mdd'] is not None and mdd_oos['v27_mdd']>=mdd_oos['source_mdd']-.05)
        accepted=bool(len(deltas)==3 and np.mean(deltas)>0 and min(deltas)>=-.10 and mdd_ok)
        rows.append({"horizon":h,"pool":f'{rule}{size}',"prior_blend":BLEND,"accepted":accepted,"windows":windows})
        progress(f'{h}: '+('通過候選驗收' if accepted else '候選未通過'))
    sd=bundle.sig_dates
    return {"protocol":"固定20%十面向先驗；開發期樣本外、保留期及全期CAGR平均須改善，任一窗口退步不超過10百分點，全期回撤惡化不超過5百分點；全期包含前兩段，非獨立第三組樣本。",
        "automatic_promotion":False,"results":rows,"data_id":data_id,"recipe_id":recipe_identity(cfg),
        "synthetic":bool(bundle.meta.get('synthetic')),
        "generated_at":datetime.now(ZoneInfo('Asia/Taipei')).isoformat(timespec='seconds'),
        "dates":{"first_oos":str(sd[min(research.first_oos,len(sd)-1)].date()),
                 "holdout_start":str(sd[min(research.holdout,len(sd)-1)].date()),"last_signal":str(sd[-1].date())}}

def save(bundle,cfg,path='artifacts/v27_validation.json',progress=lambda m:None):
    result=validate(bundle,cfg,progress);p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    from .desk_models import DeskEngine
    from .desk_research import make_record,render_report
    record=make_record(bundle,DeskEngine(bundle,cfg),result,'本次研究資料')
    p.with_name('AlphaRadar_Research_Report.html').write_text(render_report(record),encoding='utf-8')
    return p
