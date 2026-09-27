import numpy as np
import pandas as pd
from prime_engine import BRANCHES, MONTHS
from expense_engine import *


def grid(v):
    return pd.DataFrame({b:[v]*12 for b in BRANCHES})


def anchors(lines,start,end):
    a=blank_component_table(lines); z=blank_component_table(lines)
    for b in BRANCHES:
        a[b]=[start]*len(lines); z[b]=[end]*len(lines)
    return a,z


def test_linear_fg_landing_and_rate():
    fs,fe=anchors(FG_COMPONENTS,-10,-120)
    ps,pe=anchors(PF_REVENUES,1,12); cs,ce=anchors(PF_CHARGES,.2,2.4)
    p=project_expenses(grid(1000),fs,fe,blank_rate_settings(),blank_month_matrix(),ps,pe,blank_month_matrix(),blank_month_matrix(),grid(500))
    assert abs(p['fg_total']['Automobile'].iloc[-1] - (-120*len(FG_COMPONENTS)))<1e-9
    assert p['fg_rate']['Automobile'].iloc[-1] > 0
    assert np.allclose(p['result_after_fg']['Automobile'],500+p['fg_total']['Automobile'])
    assert np.allclose(p['result_after_financial']['Automobile'],p['result_after_fg']['Automobile']+p['financial_net']['Automobile'])


def test_fg_rate_modulates_total():
    fs,fe=anchors(FG_COMPONENTS,-10,-120); ps,pe=anchors(PF_REVENUES,0,0); cs,ce=anchors(PF_CHARGES,0,0)
    s=blank_rate_settings(); s['Mode']='Fixe'; s['Atterrissage (%)']=20.0
    p=project_expenses(grid(1000),fs,fe,s,blank_month_matrix(),ps,pe,blank_month_matrix(),blank_month_matrix(),grid(500))
    assert np.allclose(p['fg_total']['Automobile'],-200.0)
    assert np.allclose(p['fg_rate']['Automobile'],20.0)


def test_financial_manual_override():
    fs,fe=anchors(FG_COMPONENTS,0,0); ps,pe=anchors(PF_REVENUES,1,12); cs,ce=anchors(PF_CHARGES,.2,2.4)
    pm=blank_month_matrix(); pm.loc[5,'Automobile']=999
    p=project_expenses(grid(1000),fs,fe,blank_rate_settings(),blank_month_matrix(),ps,pe,pm,blank_month_matrix(),grid(500))
    assert abs(p['financial_products'].loc[5,'Automobile']-999)<1e-9


def test_portfolio_rate_identity():
    fs,fe=anchors(FG_COMPONENTS,-1,-12); ps,pe=anchors(PF_REVENUES,0,0); cs,ce=anchors(PF_CHARGES,0,0)
    p=project_expenses(grid(1000),fs,fe,blank_rate_settings(),blank_month_matrix(),ps,pe,blank_month_matrix(),blank_month_matrix(),grid(500))
    q=portfolio_expense_metrics(grid(1000),grid(500),p)
    assert np.allclose(q['Taux FG portefeuille (%)'], -100*q['Frais généraux']/q['Prime acquise nette'])


def test_random_stress_500():
    rng=np.random.default_rng(20260926)
    for _ in range(500):
        e=grid(float(rng.uniform(1e5,1e10)))
        fs=blank_component_table(FG_COMPONENTS); fe=blank_component_table(FG_COMPONENTS)
        ps=blank_component_table(PF_REVENUES+PF_CHARGES); pe=blank_component_table(PF_REVENUES+PF_CHARGES)
        for b in BRANCHES:
            fs[b]=rng.uniform(-1e7,0,len(FG_COMPONENTS)); fe[b]=rng.uniform(-1e9,0,len(FG_COMPONENTS))
            ps[b]=rng.uniform(0,1e7,len(PF_REVENUES+PF_CHARGES)); pe[b]=rng.uniform(0,1e9,len(PF_REVENUES+PF_CHARGES))
        s=blank_rate_settings()
        if rng.random()<.5:
            s['Mode']='Linéaire'; s['Départ (%)']=rng.uniform(0,50); s['Atterrissage (%)']=rng.uniform(0,50)
        p=project_expenses(e,fs,fe,s,blank_month_matrix(),ps,pe,blank_month_matrix(),blank_month_matrix(),grid(float(rng.uniform(-1e9,1e9))))
        for key in ['fg_total','fg_rate','financial_products','financial_charges','financial_net','result_after_fg','result_after_financial']:
            assert np.isfinite(p[key].to_numpy(float)).all()
