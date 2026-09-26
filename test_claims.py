import numpy as np
import pandas as pd

from claims_engine import (
    blank_sp_settings, blank_month_matrix, blank_portfolio_manual,
    build_portfolio_target, optimize_sp_matrix, calculate_claims_and_result,
    portfolio_metrics,
)
from prime_engine import BRANCHES, MONTHS


def earned_df(value=100.0):
    d={"Mois":MONTHS}
    for j,b in enumerate(BRANCHES): d[b]=[value*(j+1)]*12
    return pd.DataFrame(d)


def test_linear_path_without_portfolio():
    e=earned_df()
    s=blank_sp_settings(50,70)
    manual=blank_month_matrix()
    out,lo,hi,ach,diags=optimize_sp_matrix(e,s,manual,[],[np.nan]*12,50,70)
    assert abs(out.loc[0,"Automobile"]-50)<1e-9
    assert abs(out.loc[11,"Automobile"]-70)<1e-9


def test_manual_override_is_hard():
    e=earned_df()
    s=blank_sp_settings(50,70)
    manual=blank_month_matrix()
    manual.loc[5,"Automobile"]=91.0
    out,lo,hi,ach,diags=optimize_sp_matrix(e,s,manual,[],[np.nan]*12,50,70)
    assert out.loc[5,"Automobile"]==91.0
    assert lo.loc[5,"Automobile"]==91.0 and hi.loc[5,"Automobile"]==91.0


def test_portfolio_target_exact_when_feasible():
    e=earned_df()
    s=blank_sp_settings(50,70)
    s["Marge baisse (pts)"]=30.0; s["Marge hausse (pts)"]=30.0
    target=[65.0]*12
    out,lo,hi,ach,diags=optimize_sp_matrix(e,s,blank_month_matrix(),[],target,50,70)
    assert np.allclose(ach,65.0,atol=1e-6)


def test_locked_branch_does_not_move():
    e=earned_df()
    s=blank_sp_settings(50,50)
    s["Marge baisse (pts)"]=40.0; s["Marge hausse (pts)"]=40.0
    out,lo,hi,ach,diags=optimize_sp_matrix(e,s,blank_month_matrix(),["Automobile"],[80.0]*12,50,50)
    assert np.allclose(out["Automobile"],50.0)
    assert np.allclose(ach,80.0,atol=1e-6)


def test_impossible_target_hits_boundary_and_reports():
    e=earned_df()
    s=blank_sp_settings(50,50)
    s["Marge baisse (pts)"]=1.0; s["Marge hausse (pts)"]=1.0
    out,lo,hi,ach,diags=optimize_sp_matrix(e,s,blank_month_matrix(),[],[90.0]*12,50,50)
    assert np.all(ach <= 51.000001)
    assert len(diags)>=1


def test_charge_decomposition_identity():
    e=earned_df(1000)
    c=pd.DataFrame({b:[10.0]*12 for b in BRANCHES})
    sx=pd.DataFrame({b:[60.0]*12 for b in BRANCHES})
    sg=pd.DataFrame({b:[50.0]*12 for b in BRANCHES})
    ce,ca,cg,rt=calculate_claims_and_result(e,c,sx,sg)
    for b in BRANCHES:
        assert np.allclose(ce[b]+ca[b],cg[b])
        assert np.allclose(rt[b],e[b]-cg[b]-c[b])


def test_boni_prior_when_global_below_exercise():
    e=earned_df(1000)
    z=pd.DataFrame({b:[0.0]*12 for b in BRANCHES})
    sx=pd.DataFrame({b:[70.0]*12 for b in BRANCHES})
    sg=pd.DataFrame({b:[50.0]*12 for b in BRANCHES})
    ce,ca,cg,rt=calculate_claims_and_result(e,z,sx,sg)
    assert (ca[BRANCHES].to_numpy() < 0).all()


def test_portfolio_metrics_matches_weighted_ratio():
    e=earned_df(1000)
    z=pd.DataFrame({b:[0.0]*12 for b in BRANCHES})
    sx=pd.DataFrame({b:[60.0]*12 for b in BRANCHES})
    sg=pd.DataFrame({b:[45.0]*12 for b in BRANCHES})
    ce,ca,cg,rt=calculate_claims_and_result(e,z,sx,sg)
    p=portfolio_metrics(e,ce,cg,z,rt)
    assert np.allclose(p["S/P exercice portefeuille (%)"],60.0)
    assert np.allclose(p["S/P global portefeuille (%)"],45.0)
    assert np.allclose(p["Marge technique avant FG (%)"],55.0)


def test_portfolio_target_manual_curve():
    m=blank_portfolio_manual(); m.loc[2,"S/P exercice cible (%)"]=77.0
    t=build_portfolio_target("Linéaire",50,60,m,"S/P exercice cible (%)")
    assert t[0]==50 and t[-1]==60 and t[2]==77


def test_random_stress_1000():
    rng=np.random.default_rng(1234)
    for _ in range(1000):
        e=earned_df(float(rng.uniform(1e5,1e8)))
        s=blank_sp_settings(float(rng.uniform(20,80)),float(rng.uniform(20,100)))
        s["Marge baisse (pts)"]=float(rng.uniform(0,30)); s["Marge hausse (pts)"]=float(rng.uniform(0,30))
        base_target=float(rng.uniform(10,120))
        out,lo,hi,ach,diags=optimize_sp_matrix(e,s,blank_month_matrix(),[],[base_target]*12,50,70)
        assert np.isfinite(out.to_numpy()).all()
        assert (out.to_numpy() >= lo.to_numpy()-1e-7).all()
        assert (out.to_numpy() <= hi.to_numpy()+1e-7).all()

def test_app_sp_result_local_and_ifrs_logic():
    from app import run_sp_projection
    def grid(v):
        d={"Mois":MONTHS}
        for b in BRANCHES: d[b]=[v]*12
        return pd.DataFrame(d)
    ex=blank_sp_settings(60,60); gl=blank_sp_settings(50,50)
    ex["Marge baisse (pts)"]=0; ex["Marge hausse (pts)"]=0
    gl["Marge baisse (pts)"]=0; gl["Marge hausse (pts)"]=0
    args=[grid(1000),grid(100),grid(20),grid(10),"Local","Automobile","Décembre",ex,gl,blank_month_matrix(),blank_month_matrix(),[],"Libre",None,None,None,None,blank_portfolio_manual()]
    out=run_sp_projection(*args)
    # Local result per branch = 1000 - 500 - (100-20)=420
    branch_result=out[2]
    assert abs(branch_result["Résultat technique avant FG"].iloc[-1]-420)<1e-9
    args[4]="IFRS"
    out=run_sp_projection(*args)
    # IFRS commission net = 100 + DAC 10 - 20 = 90 => result 410
    branch_result=out[2]
    assert abs(branch_result["Résultat technique avant FG"].iloc[-1]-410)<1e-9
