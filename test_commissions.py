import numpy as np
from prime_engine import project_branch


def hist(target=1_000_000_000.0):
    weights=np.array([6,7,8,8,9,9,8,8,9,9,9,10],float)
    return np.cumsum(weights/weights.sum()*target)


def base(**kw):
    args=dict(
        histories_gross=[hist(900e6),hist(950e6),hist(1e9)],
        gross_landing=1.2e9,
        reass_landing=360e6,
        gross_departure=90e6,
        cession_config={"mode":"Fixe","fixed":30.0},
        rec_direct_config={"mode":"Fixe","fixed":0.0},
        rec_reass_local_config={"mode":"Fixe","fixed":0.0},
        rec_reass_ifrs_config={"mode":"Fixe","fixed":0.0},
        direct_commission_config={"mode":"Fixe","fixed":14.0},
        reass_commission_config={"mode":"Fixe","fixed":50.0},
        direct_dac_config={"mode":"Fixe","fixed":0.0},
        reass_dac_config={"mode":"Fixe","fixed":0.0},
    )
    args.update(kw)
    return project_branch(**args).table


def test_fixed_commission_formulas():
    t=base()
    assert np.allclose(t["Commission Direct"],t["Prime brute"]*.14)
    assert np.allclose(t["Commission Réassurance"],t["Commission Direct"]*.50)
    expected_effective=np.divide(t["Commission Réassurance"],t["Prime réassurance"],out=np.zeros(len(t)),where=np.abs(t["Prime réassurance"])>1e-12)*100
    assert np.allclose(t["Taux commission Réassurance effectif (%)"],expected_effective)
    expected=(t["Commission Direct"]-t["Commission Réassurance"])/t["Prime acquise nette Local"]*100
    assert np.allclose(t["Taux commission CPC Local (%)"],expected)


def test_linear_commission_start_and_end():
    t=base(
        direct_commission_config={"mode":"Linéaire","start":10.0,"end":16.0,"margin_down":2,"margin_up":2},
        reass_commission_config={"mode":"Linéaire","start":40.0,"end":55.0,"margin_down":2,"margin_up":2},
    )
    assert abs(t["Taux commission Direct (%)"].iloc[0]-10)<1e-9
    assert abs(t["Taux commission Direct (%)"].iloc[-1]-16)<1e-9
    assert abs(t["Taux récupération commission Réassurance (%)"].iloc[0]-40)<1e-9
    assert abs(t["Taux récupération commission Réassurance (%)"].iloc[-1]-55)<1e-9
    assert np.allclose(t["Commission Réassurance"],t["Commission Direct"]*t["Taux récupération commission Réassurance (%)"]/100)


def test_monthly_commission_override_with_margin():
    manual=[np.nan]*12; manual[5]=30.0
    t=base(direct_commission_config={"mode":"Linéaire","start":10.0,"end":12.0,"manual":manual,"margin_down":1.0,"margin_up":1.0})
    baseline=np.linspace(10,12,12)[5]
    assert abs(t["Taux commission Direct (%)"].iloc[5]-(baseline+1.0))<1e-9


def test_monthly_reass_commission_recovery_override():
    manual=[np.nan]*12; manual[4]=62.0
    t=base(reass_commission_config={"mode":"Linéaire","start":40.0,"end":50.0,"manual":manual,"margin_down":3.0,"margin_up":3.0})
    baseline=np.linspace(40,50,12)[4]
    expected=min(baseline+3.0,62.0)
    assert abs(t["Taux récupération commission Réassurance (%)"].iloc[4]-expected)<1e-9
    assert abs(t["Commission Réassurance"].iloc[4]-t["Commission Direct"].iloc[4]*expected/100)<1e-6


def test_direct_dac_uses_rec_prorata_and_fixed_opening():
    t=base(
        rec_open_direct_cima72=72e6,
        rec_direct_config={"mode":"Fixe","fixed":7.2},
        direct_dac_config={"mode":"Fixe","fixed":17.0},
        dac_open_direct_ifrs=17e6,
    )
    assert np.allclose(t["DAC ouverture Direct IFRS"],17e6)
    assert np.allclose(t["DAC clôture Direct IFRS"],t["REC clôture Direct prorata"]*.17)
    assert np.allclose(t["Variation DAC Direct IFRS"],t["DAC ouverture Direct IFRS"]-t["DAC clôture Direct IFRS"])


def test_reass_dac_uses_rec_100_percent():
    t=base(
        rec_open_reass_ifrs100=30e6,
        rec_reass_ifrs_config={"mode":"Fixe","fixed":4.0},
        reass_dac_config={"mode":"Fixe","fixed":17.0},
        dac_open_reass_ifrs=5.1e6,
    )
    assert np.allclose(t["DAC clôture Réassurance IFRS"],t["REC clôture Réass IFRS 100%"]*.17)
    assert np.allclose(t["Variation DAC Réassurance IFRS"],t["DAC ouverture Réassurance IFRS"]-t["DAC clôture Réassurance IFRS"])


def test_cpc_ifrs_commission_identity_matches_pd_structure():
    t=base(
        rec_open_direct_cima72=72e6,
        rec_direct_config={"mode":"Fixe","fixed":7.2},
        rec_open_reass_ifrs100=30e6,
        rec_reass_ifrs_config={"mode":"Fixe","fixed":5.0},
        direct_dac_config={"mode":"Fixe","fixed":17.0},
        reass_dac_config={"mode":"Fixe","fixed":17.0},
        dac_open_direct_ifrs=17e6,
        dac_open_reass_ifrs=5.1e6,
    )
    expected_amount=t["Commission Direct"]+t["Variation DAC Direct IFRS"]-t["Commission Réassurance"]
    expected_rate=expected_amount/t["Prime acquise nette IFRS"]*100
    assert np.allclose(t["Commission nette CPC IFRS"],expected_amount)
    assert np.allclose(t["Taux commission CPC IFRS (%)"],expected_rate)


def test_pd_january_auto_commission_and_direct_dac_formula():
    gross=2066685645.8635378
    ceded=79809368.39985986
    cession=100*ceded/gross
    cima_open=1561398332.154345
    cima_var=609612398.842279
    rec_rate=100*cima_var/gross
    reass100_open=35468606.46335736
    reass100_close=36057534.27272988
    reass_rec_rate=100*(reass100_close-reass100_open)/ceded
    t=project_branch(
        histories_gross=[np.linspace(gross/12,gross,12)], gross_landing=gross, reass_landing=ceded,
        gross_departure=gross,
        cession_config={"mode":"Fixe","fixed":cession},
        rec_direct_config={"mode":"Fixe","fixed":rec_rate},
        rec_reass_local_config={"mode":"Fixe","fixed":0.0},
        rec_reass_ifrs_config={"mode":"Fixe","fixed":reass_rec_rate},
        rec_open_direct_cima72=cima_open,
        rec_open_reass_ifrs100=reass100_open,
        direct_commission_config={"mode":"Fixe","fixed":14.0},
        reass_commission_config={"mode":"Fixe","fixed":4.689217061534405},
        direct_dac_config={"mode":"Fixe","fixed":17.0},
        reass_dac_config={"mode":"Fixe","fixed":17.0},
        dac_open_direct_ifrs=368663495.09199816,
        dac_open_reass_ifrs=6029663.098770758,
    ).table
    assert abs(t["Commission Direct"].iloc[0]-289335990.42089534)<1
    assert abs(t["Commission Réassurance"].iloc[0]-13567592.627976177)<1
    assert abs(t["REC clôture Direct prorata"].iloc[0]-3015292681.9397554)<2
    assert abs(t["DAC clôture Direct IFRS"].iloc[0]-512599755.9297585)<2
    assert abs(t["DAC clôture Réassurance IFRS"].iloc[0]-6129780.82636408)<2
    # Exact January Auto CPC IFRS net commission rate from pd.xlsx.
    assert abs(t["Taux commission CPC IFRS (%)"].iloc[0]-11.556302235663972)<1e-9

def test_reass_commission_moves_with_direct_not_directly_with_ceded_premium():
    low=base(
        direct_commission_config={"mode":"Fixe","fixed":10.0},
        reass_commission_config={"mode":"Fixe","fixed":40.0},
    )
    high=base(
        direct_commission_config={"mode":"Fixe","fixed":20.0},
        reass_commission_config={"mode":"Fixe","fixed":40.0},
    )
    # Same premium/reinsurance trajectory; doubling Direct commission doubles Reass commission.
    assert np.allclose(low["Prime réassurance"],high["Prime réassurance"])
    assert np.allclose(high["Commission Direct"],low["Commission Direct"]*2.0)
    assert np.allclose(high["Commission Réassurance"],low["Commission Réassurance"]*2.0)
    assert np.allclose(high["Commission Réassurance"],high["Commission Direct"]*.40)
