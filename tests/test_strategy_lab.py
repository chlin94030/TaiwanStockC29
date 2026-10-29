import copy
import numpy as np
import pandas as pd
from kosto.config import load_config
from kosto.strategy_lab import Registry,Lab,candidate_set,development_metrics,choose_winner,evaluate,readiness
from tests.test_engine import world


def test_predeclared_candidates_unique_and_repeatable():
    cfg=load_config();a=candidate_set(cfg,'mid');b=candidate_set(cfg,'mid')
    assert a==b and len({r['id'] for r in a})==len(a)
    assert {'cash','bench'}<={r['residual'] for r in a}
    assert len({r['rule'] for r in a})>=3


def test_selection_is_invariant_to_holdout_returns():
    days=pd.bdate_range('2020-01-01',periods=800);nav=pd.Series(np.exp(np.arange(800)*.0005),index=days);bench=nav**.5
    a=development_metrics(nav,bench,days[600])[0]
    mutated=nav.copy();mutated.iloc[600:]*=np.linspace(.01,100,200)
    b=development_metrics(mutated,bench,days[600])[0]
    assert a==b


def test_holdout_winner_is_immutable(tmp_path):
    registry=Registry(tmp_path)
    a=registry.seal('same','short','first',{'passed':False});b=registry.seal('same','short','lucky',{'passed':True})
    assert a==b and b['winner']=='first' and not b['passed']


def test_overlapping_holdout_cannot_be_promoted_as_new_blind_test(tmp_path):
    registry=Registry(tmp_path)
    registry.seal('first','mid','a',{'from':'2025-01-01','to':'2025-12-31','deployable':False})
    result=registry.seal('next','mid','b',{'from':'2025-02-01','to':'2026-01-31','deployable':True})
    assert result['overlapping_holdout'] and not result['deployable']


def test_synthetic_research_report_is_labelled():
    from kosto.lab_report import render
    report={'generated_at':'2026-10-29','status':'測試','readiness':{'synthetic':True},'champions':{},'trial_count':0,'trials':[],'objective':'測試','limitations':[]}
    assert '合成資料' in render(report)


def test_best_return_only_among_risk_qualified_trials():
    def r(k,score,qualified):return {'recipe':{'id':k},'objective':score,'selection_eligible':qualified,'metric':{'sharpe':1}}
    assert choose_winner([r('bad',9,False),r('good',.3,True),r('lower',.2,True)])['recipe']['id']=='good'
    assert choose_winner([r('bad',9,False)]) is None


def test_no_bundle_cannot_generate_fake_performance(tmp_path):
    lab=Lab(tmp_path);assert not lab.start(budget=4)
    report=lab.report();assert not report['readiness']['ready'] and report['trial_count']==0
    assert all(x is None for x in report['champions'].values())


def test_research_runs_with_purged_development_only(world):
    cfg=copy.deepcopy(world.cfg);cfg['research']['holdout_months']=6
    recipe=candidate_set(cfg,'mid',1)[0];recipe['size']=60;recipe['rule']='ADV'
    result=evaluate(world.B,cfg,recipe)
    assert result['synthetic'] and result['metric']['fold_count']>=3
    assert result['nav']['date'][-1]<result['holdout_start']
    assert all(x['from']<result['holdout_start'] for x in result['weights_history'])
    assert 'holdout_cagr' not in result['metric']
