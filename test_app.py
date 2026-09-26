import numpy as np
import pandas as pd
import app
from prime_engine import stress_random


def _hist(scale):
    inc=np.array([8,7,9,10,8,11,9,8,10,9,11,12],float)*scale
    d={"Mois":app.MONTHS}
    for j,b in enumerate(app.BRANCHES): d[b]=np.cumsum(inc*(1+j*.04))
    return pd.DataFrame(d)


def _anchors():
    a=app.blank_anchors()
    for i,b in enumerate(app.BRANCHES):
        a.loc[i,"Départ Direct (facultatif)"]=100*(1+i*.05)
        a.loc[i,"Atterrissage Direct"]=1200*(1+i*.05)
        a.loc[i,"Atterrissage Réassurance"]=300*(1+i*.05)
        a.loc[i,"REC ouverture Direct CIMA 72%"] = 80*(1+i*.03)
        a.loc[i,"REC ouverture Réass Local CIMA"] = 20*(1+i*.03)
        a.loc[i,"REC ouverture Réass IFRS 100%"] = 28*(1+i*.03)
    return a


def test_template_import_blank():
    out=app.load_template(app.TEMPLATE_PATH)
    assert len(out)==10
    assert out[0].shape==(12,9)
    assert out[3].shape==(8,8)
    assert out[4].shape==(8,len(app.COMMISSION_ANCHOR_COLS))


def test_ui_projection_outputs_all_branches_and_months():
    h3,h2,h1=_hist(8),_hist(9),_hist(10)
    outs=app.run_projection(
        h3,h2,h1,_anchors(),app.blank_month_matrix(),
        app.default_rate_settings('cession'),app.blank_month_matrix(),app.blank_month_matrix(),
        app.default_rate_settings('rec'),app.blank_month_matrix(),app.blank_month_matrix(),
        app.default_rate_settings('rec'),app.blank_month_matrix(),app.blank_month_matrix(),
        app.default_rate_settings('rec'),app.blank_month_matrix(),app.blank_month_matrix(),
        'Local','Automobile'
    )
    assert len(outs)==38
    for idx in range(3,16):
        df=outs[idx]
        assert list(df.columns)==['Mois']+app.BRANCHES
        assert len(df)==12


def test_ifrs_direct_rec_is_cima72_divided_by_072():
    h3,h2,h1=_hist(8),_hist(9),_hist(10)
    anchors=_anchors()
    rd=app.default_rate_settings('rec'); rd['Mode']='Fixe'; rd['Atterrissage (%)']=7.2
    common=[h3,h2,h1,anchors,app.blank_month_matrix(),
        app.default_rate_settings('cession'),app.blank_month_matrix(),app.blank_month_matrix(),
        rd,app.blank_month_matrix(),app.blank_month_matrix(),
        app.default_rate_settings('rec'),app.blank_month_matrix(),app.blank_month_matrix(),
        app.default_rate_settings('rec'),app.blank_month_matrix(),app.blank_month_matrix()]
    loc=app.run_projection(*common,'Local','Automobile')
    ifr=app.run_projection(*common,'IFRS','Automobile')
    local_var=loc[8]['Automobile'].to_numpy(float)
    ifrs_var=ifr[8]['Automobile'].to_numpy(float)
    assert np.allclose(ifrs_var, local_var/0.72)


def test_point_override_reaches_month_and_preserves_landing():
    m=app.blank_month_matrix()
    m=app.apply_point_override(m,'Automobile','Juin',650.0)
    assert m.loc[5,'Automobile']==650.0
    assert np.isnan(m.loc[4,'Automobile'])


def test_stress_5000():
    r=stress_random(seed=20260926, scenarios=5000)
    assert r.ok.all(), r[~r.ok].head().to_dict('records')


def test_compact_branch_editor_only_applies_changed_cells():
    h3,h2,h1=_hist(8),_hist(9),_hist(10)
    common=[
        h3,h2,h1,_anchors(),app.blank_month_matrix(),
        app.default_rate_settings('cession'),app.blank_month_matrix(),app.blank_month_matrix(),
        app.default_rate_settings('rec'),app.blank_month_matrix(),app.blank_month_matrix(),
        app.default_rate_settings('rec'),app.blank_month_matrix(),app.blank_month_matrix(),
        app.default_rate_settings('rec'),app.blank_month_matrix(),app.blank_month_matrix(),
    ]
    outs=app.run_projection(*common,'Local','Automobile')
    reference=outs[36].copy()
    edited=reference.copy()
    edited.loc[5,'Prime brute']=float(reference.loc[5,'Prime brute'])+25.0
    g,c,rd,rl,ri=app.apply_branch_table(
        edited,reference,'Automobile','Local',
        app.blank_month_matrix(),app.blank_month_matrix(),app.blank_month_matrix(),
        app.blank_month_matrix(),app.blank_month_matrix(),
    )
    assert np.isfinite(g.loc[5,'Automobile'])
    assert np.isnan(g.loc[4,'Automobile'])
    assert np.isnan(c['Automobile']).all()
    assert np.isnan(rd['Automobile']).all()
    assert np.isnan(rl['Automobile']).all()
    assert np.isnan(ri['Automobile']).all()


def test_compact_branch_editor_routes_reass_rec_to_selected_view():
    ref=pd.DataFrame({
        'Mois':app.MONTHS,
        'Prime brute':[100.0]*12,
        'Taux cession (%)':[20.0]*12,
        'Taux REC Direct (%)':[10.0]*12,
        'Taux REC Réass (%)':[8.0]*12,
    })
    edited=ref.copy(); edited.loc[2,'Taux REC Réass (%)']=12.0
    blank=lambda: app.blank_month_matrix()
    _,_,_,rl,ri=app.apply_branch_table(edited,ref,'Automobile','IFRS',blank(),blank(),blank(),blank(),blank())
    assert np.isnan(rl.loc[2,'Automobile'])
    assert ri.loc[2,'Automobile']==12.0
