"""Research claims must match both the input data and the current recipe."""
from types import SimpleNamespace
import copy
import numpy as np
import pandas as pd
from kosto.desk_research import bundle_identity,recipe_identity,validation_state,render_report


def sample(synthetic=False):
    return SimpleNamespace(meta={'tickers':['2330'],'factors':['f_roe'],'sig_dates':['2026-01-01'],'days':['2026-01-01'],'rules':['ADV'],'synthetic':synthetic},a={'U':np.array([[[3]]],dtype=np.uint16)})


def result(B,cfg):
    return {'data_id':bundle_identity(B),'recipe_id':recipe_identity(cfg),'results':[{'horizon':h,'accepted':True} for h in ('short','mid','long')]}


def test_changed_market_data_cannot_reuse_validation():
    a,b=sample(),sample();b.a['U'][0,0,0]=4
    cfg={};r=result(a,cfg)
    assert validation_state(b,cfg,r)[0]=='unmatched'


def test_changed_strategy_cannot_reuse_validation():
    B=sample();r=result(B,{'costs':{'slippage':.001}})
    assert validation_state(B,{'costs':{'slippage':.002}},r)[0]=='unmatched'


def test_synthetic_passes_never_become_investment_evidence():
    B=sample(True);r=result(B,{})
    assert validation_state(B,{},r)[0]=='demo'
    assert validation_state(B,{},None)[0]=='pending'


def test_all_horizons_required_for_complete_conclusion():
    B=sample();r=result(B,{})
    assert validation_state(B,{},r)[0]=='passed'
    r['results'].pop()
    assert validation_state(B,{},r)[0]=='incomplete'


def test_derived_sector_codes_do_not_invalidate_same_bundle():
    B=sample();a=bundle_identity(B)
    B.meta.pop('_validation_data_id');B.a['SECTOR']=np.array([0])
    assert bundle_identity(B)==a
