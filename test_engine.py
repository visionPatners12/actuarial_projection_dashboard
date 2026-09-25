import numpy as np
import pandas as pd
from model import *


def seeded():
    sd=empty_direct_start(); sr=empty_reass_start();
    i=sd.index[sd.branch=='Automobile'][0]
    sd.loc[i,['gwp_ytd','pap_open','pap_close','pane_open','pane_close','commission_ytd','paid_current_ytd','paid_prior_ytd','recourse_current_ytd','recourse_prior_ytd','upr_open','upr_close','case_open_current','case_close_current','case_open_prior','case_close_prior','ibnr_open_current','ibnr_close_current','ibnr_open_prior','ibnr_close_prior']]=[
        6e9,1e8,1e8,2e8,2e8,9e8,1.2e9,8e8,20e6,10e6,1.3e9,1.1e9,0,3e8,2.2e9,2.0e9,0,1e8,3.5e8,3e8]
    j=sr.index[sr.branch=='Automobile'][0]
    sr.loc[j,['ceded_premium_ytd','reass_commission_ytd','recovered_paid_current_ytd','recovered_paid_prior_ytd','ceded_upr_open','ceded_upr_close','recoverable_case_open_current','recoverable_case_close_current','recoverable_case_open_prior','recoverable_case_close_prior','recoverable_ibnr_open_current','recoverable_ibnr_close_current','recoverable_ibnr_open_prior','recoverable_ibnr_close_prior']]=[
        1.5e9,225e6,295e6,197.5e6,325e6,275e6,0,75e6,550e6,500e6,0,25e6,87.5e6,75e6]
    return sd,sr


def empty_hist(): return pd.DataFrame(),pd.DataFrame()


def test_manual_adjustment_changes_path():
    sd,sr=seeded(); hd,hr=empty_hist(); start='2026-08'; n=4
    h=build_hyp_direct(hd,start,n); rh=build_hyp_reass(hd,hr,start,n)
    base=run_projection(sd,sr,h,rh,empty_cibles_direct(start,n),empty_cibles_reass(start,n),start,n,hd,hr)[0]
    mask=(h.branch=='Automobile')&(h.metric=='Primes Emises')&(h.period=='2026-09'); h.loc[mask,'adjustment_pts']=5
    mod=run_projection(sd,sr,h,rh,empty_cibles_direct(start,n),empty_cibles_reass(start,n),start,n,hd,hr)[0]
    a=base[(base.branch=='Automobile')].sort_values('period').iloc[0].gwp_ytd
    b=mod[(mod.branch=='Automobile')].sort_values('period').iloc[0].gwp_ytd
    assert b>a


def test_direct_target_generates_uniform_adjustment_and_hits_target():
    sd,sr=seeded(); hd,hr=empty_hist(); start='2026-08'; n=4
    h=build_hyp_direct(hd,start,n); rh=build_hyp_reass(hd,hr,start,n)
    cd=empty_cibles_direct(start,n); cr=empty_cibles_reass(start,n)
    cd.loc[cd.branch=='Automobile','gwp_end']=9e9
    d,r,s,diag,apd,apr,*_=run_projection(sd,sr,h,rh,cd,cr,start,n,hd,hr)
    x=d[d.branch=='Automobile'].sort_values('period').iloc[-1]
    assert abs(x.gwp_ytd-9e9)<100
    a=apd[(apd.branch=='Automobile')&(apd.metric=='Primes Emises')]
    assert a.target_adjustment_pts.nunique()==1


def test_reass_is_rate_driven():
    sd,sr=seeded(); hd,hr=empty_hist(); start='2026-08'; n=4
    h=build_hyp_direct(hd,start,n); rh=build_hyp_reass(hd,hr,start,n)
    rh.loc[rh.metric=='Taux cession primes','base_pct']=30
    rh.loc[rh.metric=='Taux récupération sinistres','base_pct']=40
    d,r,s,diag,*_=run_projection(sd,sr,h,rh,empty_cibles_direct(start,n),empty_cibles_reass(start,n),start,n,hd,hr)
    m=pd.merge(d,r,on=['period','branch'])
    a=m[m.branch=='Automobile']
    assert np.allclose(a.ceded_premium_ytd, a.gwp_ytd*0.30,rtol=1e-10,atol=1)
    assert np.allclose(a.recovery_ratio_global_ytd,0.40,rtol=1e-9,atol=1e-9)


def test_reass_targets_adjust_rates():
    sd,sr=seeded(); hd,hr=empty_hist(); start='2026-08'; n=4
    h=build_hyp_direct(hd,start,n); rh=build_hyp_reass(hd,hr,start,n)
    cd=empty_cibles_direct(start,n); cr=empty_cibles_reass(start,n)
    # target cession 35% at end
    gross=run_projection(sd,sr,h,rh,cd,cr,start,n,hd,hr)[0]
    end=gross[gross.branch=='Automobile'].sort_values('period').iloc[-1]
    cr.loc[cr.branch=='Automobile','ceded_premium_end']=end.gwp_ytd*0.35
    cr.loc[cr.branch=='Automobile','recovered_incurred_end']=(end.incurred_current_ytd+end.incurred_prior_ytd)*0.45
    d,r,s,diag,apd,apr,*_=run_projection(sd,sr,h,rh,cd,cr,start,n,hd,hr)
    rr=r[r.branch=='Automobile'].sort_values('period').iloc[-1]
    assert abs(rr.cession_rate-0.35)<1e-9
    assert abs(rr.recovery_ratio_global_ytd-0.45)<1e-8


def test_openings_fixed_pap_pane_fixed_and_earned_monotone():
    sd,sr=seeded(); hd,hr=empty_hist(); start='2026-08'; n=4
    h=build_hyp_direct(hd,start,n); rh=build_hyp_reass(hd,hr,start,n)
    d,r,s,diag,*_=run_projection(sd,sr,h,rh,empty_cibles_direct(start,n),empty_cibles_reass(start,n),start,n,hd,hr)
    x=d[d.branch=='Automobile'].sort_values('period')
    for f in ['upr_open','case_open_current','case_open_prior','ibnr_open_current','ibnr_open_prior','pap_open','pap_close','pane_open','pane_close']:
        assert np.ptp(x[f].to_numpy(float))<1e-9, f
    assert (np.diff(x.earned_premium_ytd.to_numpy(float))>=-1e-6).all()


def test_claim_identity():
    sd,sr=seeded(); hd,hr=empty_hist(); start='2026-08'; n=4
    h=build_hyp_direct(hd,start,n); rh=build_hyp_reass(hd,hr,start,n)
    d,r,s,diag,*_=run_projection(sd,sr,h,rh,empty_cibles_direct(start,n),empty_cibles_reass(start,n),start,n,hd,hr)
    lhs=d.incurred_current_ytd
    rhs=d.paid_current_ytd-d.recourse_current_ytd+d.case_close_current+d.ibnr_close_current-d.case_open_current-d.ibnr_open_current
    assert np.max(np.abs(lhs-rhs))<1e-4


def test_multi_year_rollover():
    sd,sr=seeded(); hd,hr=empty_hist(); start='2026-11'; n=15
    h=build_hyp_direct(hd,start,n); rh=build_hyp_reass(hd,hr,start,n)
    d,r,s,diag,*_=run_projection(sd,sr,h,rh,empty_cibles_direct(start,n),empty_cibles_reass(start,n),start,n,hd,hr)
    x=d[d.branch=='Automobile'].sort_values('period').reset_index(drop=True)
    dec=x[pd.to_datetime(x.period).dt.month==12].iloc[0]
    jan=x[pd.to_datetime(x.period).dt.month==1].iloc[0]
    assert abs(jan.upr_open-dec.upr_close)<1e-6
    assert jan.case_open_current==0 and jan.ibnr_open_current==0
    assert abs(jan.case_open_prior-(dec.case_close_current+dec.case_close_prior))<1e-6


def run_all():
    tests=[v for k,v in globals().items() if k.startswith('test_') and callable(v)]
    for fn in tests:
        fn(); print('PASS',fn.__name__)
    print('ALL PASS',len(tests))

if __name__=='__main__': run_all()
