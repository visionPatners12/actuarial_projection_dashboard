import numpy as np
from prime_engine import *


def histories():
    return [
        np.cumsum([80,70,90,95,100,110,80,75,85,90,100,125])*1e6,
        np.cumsum([82,74,94,90,104,115,84,78,90,96,106,137])*1e6,
        np.cumsum([88,78,98,96,110,120,90,82,94,102,112,150])*1e6,
    ]


def base_result(**kw):
    args=dict(
        histories_gross=histories(), gross_landing=1.5e9, reass_landing=450e6,
        gross_departure=110e6,
        cession_config={"mode":"Linéaire","start":25,"end":30,"margin_down":3,"margin_up":4},
        rec_direct_config={"mode":"Linéaire","start":10,"end":12,"margin_down":2,"margin_up":2},
        rec_reass_local_config={"mode":"Fixe","fixed":8},
        rec_reass_ifrs_config={"mode":"Fixe","fixed":11},
        rec_open_direct_cima72=120e6, rec_open_reass_cima72=30e6, rec_open_reass_ifrs100=42e6,
    )
    args.update(kw)
    return project_branch(**args)


def test_gross_hits_landing_and_is_monotone():
    t=base_result().table
    assert abs(t['Prime brute'].iloc[-1]-1.5e9)<1e-6
    assert np.all(np.diff(t['Prime brute'])>=-1e-6)


def test_one_two_three_year_histories_supported():
    for n in (1,2,3):
        r=project_branch(histories()[-n:],1.4e9,350e6,
            cession_config={"mode":"Fixe","fixed":25},
            rec_direct_config={"mode":"Fixe","fixed":10},
            rec_reass_local_config={"mode":"Fixe","fixed":10},
            rec_reass_ifrs_config={"mode":"Fixe","fixed":10})
        assert abs(r.table['Prime brute'].iloc[-1]-1.4e9)<1e-6


def test_manual_prime_anchor_reprojects_future_and_keeps_target():
    r=base_result(gross_manual_anchors={5:800e6})
    t=r.table['Prime brute'].to_numpy()
    assert abs(t[5]-800e6)<1e-6
    assert abs(t[-1]-1.5e9)<1e-6
    assert np.all(np.diff(t)>=-1e-6)


def test_fixed_cession_links_gross_ceded_net():
    r=base_result(cession_config={"mode":"Fixe","fixed":30})
    t=r.table
    assert np.allclose(t['Prime réassurance'],t['Prime brute']*.30,atol=1e-5)
    assert np.allclose(t['Prime nette'],t['Prime brute']-t['Prime réassurance'])


def test_linear_cession_hits_end_rate():
    r=base_result(cession_config={"mode":"Linéaire","start":20,"end":30,"margin_down":0,"margin_up":0})
    t=r.table
    assert abs(t['Taux cession (%)'].iloc[0]-20)<1e-9
    assert abs(t['Taux cession (%)'].iloc[-1]-30)<1e-9


def test_linear_margin_clips_manual_override():
    manual=[np.nan]*12; manual[4]=50
    r=base_result(cession_config={"mode":"Linéaire","start":20,"end":30,"margin_down":2,"margin_up":3,"manual":manual})
    t=r.table
    baseline=np.linspace(20,30,12)[4]
    assert t['Taux cession (%)'].iloc[4] <= baseline+3+1e-9


def test_rec_variation_formula_direct_local():
    r=base_result(rec_direct_config={"mode":"Fixe","fixed":10})
    t=r.table
    assert np.allclose(t['Variation REC Direct CIMA 72%'],t['Prime brute']*.10,atol=1e-4)
    assert np.allclose(t['REC clôture Direct CIMA 72%'],120e6+t['Variation REC Direct CIMA 72%'],atol=1e-4)
    assert np.allclose(t['Prime acquise Direct Local'],t['Prime brute']-t['Variation REC Direct CIMA 72%'],atol=1e-4)


def test_rec_cima72_to_prorata_formula():
    r=base_result(rec_direct_config={"mode":"Fixe","fixed":7.2})
    t=r.table
    assert np.allclose(t['Variation REC Direct prorata'],t['Variation REC Direct CIMA 72%']/0.72,atol=1e-4)
    assert np.allclose(t['REC ouverture Direct prorata'],120e6/0.72,atol=1e-4)


def test_reass_local_and_ifrs_use_separate_rec_rates():
    r=base_result(
        rec_reass_local_config={"mode":"Fixe","fixed":8},
        rec_reass_ifrs_config={"mode":"Fixe","fixed":13},
    )
    t=r.table
    assert np.allclose(t['Variation REC Réass Local'],t['Prime réassurance']*.08,atol=1e-4)
    assert np.allclose(t['Variation REC Réass IFRS 100%'],t['Prime réassurance']*.13,atol=1e-4)


def test_openings_are_fixed_all_year():
    t=base_result().table
    assert t['REC ouverture Direct CIMA 72%'].nunique()==1
    assert t['REC ouverture Réass Local'].nunique()==1
    assert t['REC ouverture Réass IFRS 100%'].nunique()==1


def test_earned_gross_and_reass_are_monotone():
    t=base_result().table
    assert np.all(np.diff(t['Prime acquise Direct Local'])>=-1e-6)
    assert np.all(np.diff(t['Prime acquise Réass Local'])>=-1e-6)


def test_ceded_never_exceeds_gross_or_decreases():
    manual=np.array([50,45,40,35,30,25,20,15,10,8,6,5],float)
    r=base_result(cession_config={"mode":"Manuel","manual":manual})
    t=r.table
    assert np.all(t['Prime réassurance']<=t['Prime brute']+1e-6)
    assert np.all(np.diff(t['Prime réassurance'])>=-1e-6)


def test_stress_500_random_scenarios():
    x=stress_random(seed=42,scenarios=500)
    assert x.ok.all(), x[~x.ok].head().to_dict('records')
