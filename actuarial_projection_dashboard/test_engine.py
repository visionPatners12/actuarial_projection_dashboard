import pandas as pd
from model import *

def smoke():
    sd=empty_direct_start(); sr=empty_reass_start(); td=empty_direct_targets(); tr=empty_reass_targets(); a=default_assumptions()
    # Non-zero realistic seed for one branch and a target.
    i=sd.index[sd.branch=='Automobile'][0]
    sd.loc[i,['gwp_ytd','commission_ytd','paid_current_ytd','upr_close','case_close_prior','ibnr_close_prior']]=[6e9,8e8,1.2e9,1.1e9,2.0e9,3e8]
    sd.loc[i,['upr_open','case_open_prior','ibnr_open_prior']]=[1.3e9,2.2e9,3.5e8]
    ti=td.index[td.branch=='Automobile'][0]
    td.loc[ti,'gwp_ytd']=8e9
    d,r,s,diag,p=run_projection(sd,sr,td,tr,a,'2026-08',4,target_policy='Cible')
    assert len(d)==8*4
    assert len(r)==8*4
    # Opening continuity test for Automobile.
    x=d[d.branch=='Automobile'].sort_values('period').reset_index(drop=True)
    assert abs(x.loc[1,'upr_open']-x.loc[0,'upr_close']) < 1e-6
    assert abs(x.loc[1,'case_open_current']-x.loc[0,'case_close_current']) < 1e-6
    assert x.loc[0,'upr_open']==sd.loc[i,'upr_close']
    print('OK',len(d),len(r),len(s),len(diag))

if __name__=='__main__': smoke()
