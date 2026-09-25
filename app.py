from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import gradio as gr

from model import (
    BRANCHES, DIRECT_START_COLUMNS, REASS_START_COLUMNS, HYP_COLUMNS,
    CIBLES_DIRECT_COLUMNS, CIBLES_REASS_COLUMNS, DIRECT_METRICS, REASS_METRICS,
    empty_direct_start, empty_reass_start, empty_cibles_direct, empty_cibles_reass,
    build_hyp_direct, build_hyp_reass, run_projection, _summary,
)
from formula_exporter import export_projection
from exporter import (
    DIRECT_LABELS, REASS_LABELS, CPC_LABELS, CORPORATE_BRANCHES, CPC_GROUPS,
    _direct_value, _reass_value, _gross_metrics, _reass_metrics, _sum_metrics, _cpc_values,
)

# -----------------------------------------------------------------------------
# Référentiel UI
# -----------------------------------------------------------------------------
BRANCHES_UI = [
    "Auto", "Santé", "Accident corpo", "Incendie",
    "BDM / Construction", "RC", "RD", "Transport",
]
UI_TO_INTERNAL = dict(zip(BRANCHES_UI, BRANCHES))
INTERNAL_TO_UI = dict(zip(BRANCHES, BRANCHES_UI))
MOIS = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]

DIRECT_BLOCK = [
    ("Primes émises", "gwp_ytd"),
    ("PAP ouverture", "pap_open"), ("PAP clôture", "pap_close"),
    ("PANE ouverture", "pane_open"), ("PANE clôture", "pane_close"),
    ("Commissions", "commission_ytd"),
    ("Sinistres payés exercice", "paid_current_ytd"),
    ("Sinistres payés antérieurs", "paid_prior_ytd"),
    ("Recours exercice", "recourse_current_ytd"),
    ("Recours antérieurs", "recourse_prior_ytd"),
    ("REC ouverture", "upr_open"), ("REC clôture", "upr_close"),
    ("SAP ouverture exercice", "case_open_current"), ("SAP clôture exercice", "case_close_current"),
    ("SAP ouverture antérieurs", "case_open_prior"), ("SAP clôture antérieurs", "case_close_prior"),
    ("IBNR ouverture exercice", "ibnr_open_current"), ("IBNR clôture exercice", "ibnr_close_current"),
    ("IBNR ouverture antérieurs", "ibnr_open_prior"), ("IBNR clôture antérieurs", "ibnr_close_prior"),
]
REASS_BLOCK = [
    ("Primes cédées", "ceded_premium_ytd"),
    ("Commission de réassurance", "reass_commission_ytd"),
    ("Sinistres récupérés exercice", "recovered_paid_current_ytd"),
    ("Sinistres récupérés antérieurs", "recovered_paid_prior_ytd"),
    ("REC cédée ouverture", "ceded_upr_open"), ("REC cédée clôture", "ceded_upr_close"),
    ("SAP récupérable ouverture exercice", "recoverable_case_open_current"),
    ("SAP récupérable clôture exercice", "recoverable_case_close_current"),
    ("SAP récupérable ouverture antérieurs", "recoverable_case_open_prior"),
    ("SAP récupérable clôture antérieurs", "recoverable_case_close_prior"),
    ("IBNR récupérable ouverture exercice", "recoverable_ibnr_open_current"),
    ("IBNR récupérable clôture exercice", "recoverable_ibnr_close_current"),
    ("IBNR récupérable ouverture antérieurs", "recoverable_ibnr_open_prior"),
    ("IBNR récupérable clôture antérieurs", "recoverable_ibnr_close_prior"),
]

DIRECT_VIEW = {
    "Primes émises": "gwp_ytd", "Chiffre d’affaires": "revenue",
    "Primes acquises": "earned_premium_ytd", "Commissions": "commission_ytd",
    "Sinistres payés exercice": "paid_current_ytd", "Sinistres payés antérieurs": "paid_prior_ytd",
    "Recours exercice": "recourse_current_ytd", "Recours antérieurs": "recourse_prior_ytd",
    "Charge sinistres exercice": "incurred_current_ytd", "Charge sinistres antérieurs": "incurred_prior_ytd",
    "REC clôture": "upr_close", "SAP clôture exercice": "case_close_current",
    "SAP clôture antérieurs": "case_close_prior", "IBNR clôture exercice": "ibnr_close_current",
    "IBNR clôture antérieurs": "ibnr_close_prior", "S/P exercice": "sp_exercice",
    "S/P global": "sp_global", "Taux de commission / primes": "commission_rate_written",
}
REASS_VIEW = {
    "Primes cédées": "ceded_premium_ytd", "Primes acquises cédées": "ceded_earned_premium_ytd",
    "Commission de réassurance": "reass_commission_ytd",
    "Sinistres récupérés exercice": "recovered_incurred_current_ytd",
    "Sinistres récupérés antérieurs": "recovered_incurred_prior_ytd",
    "REC cédée clôture": "ceded_upr_close",
    "SAP récupérable clôture exercice": "recoverable_case_close_current",
    "SAP récupérable clôture antérieurs": "recoverable_case_close_prior",
    "IBNR récupérable clôture exercice": "recoverable_ibnr_close_current",
    "IBNR récupérable clôture antérieurs": "recoverable_ibnr_close_prior",
    "Taux de cession des primes": "cession_rate", "Taux de récupération des sinistres": "recovery_rate",
    "Taux de commission de réassurance": "reass_commission_rate",
}
DIRECT_DRIVER = {
    "Primes émises": "Primes Emises", "Sinistres payés exercice": "Sinistres payés Per.",
    "Sinistres payés antérieurs": "Sinistres payés Ant.", "Recours exercice": "Recours Per.",
    "Recours antérieurs": "Recours Ant.", "Charge sinistres exercice": "Charge sinistres Per.",
    "Charge sinistres antérieurs": "Charge sinistres Ant.", "Commissions": "Taux commission / primes",
    "Taux de commission / primes": "Taux commission / primes", "REC clôture": "Taux REC clôture / primes",
    "IBNR clôture exercice": "Part IBNR Per. / provisions", "IBNR clôture antérieurs": "Part IBNR Ant. / provisions",
}
REASS_DRIVER = {
    "Primes cédées": "Taux cession primes", "Taux de cession des primes": "Taux cession primes",
    "Sinistres récupérés exercice": "Taux récupération sinistres",
    "Sinistres récupérés antérieurs": "Taux récupération sinistres",
    "Taux de récupération des sinistres": "Taux récupération sinistres",
    "Commission de réassurance": "Taux commission réassurance",
    "Taux de commission de réassurance": "Taux commission réassurance",
}

THEME = gr.themes.Soft(primary_hue="blue", neutral_hue="slate", radius_size="lg")
CSS = """
.gradio-container{max-width:1550px!important;margin:0 auto;background:#F7F9FC}
#entete{background:#fff;border:1px solid #E7ECF2;border-radius:20px;padding:22px 26px;margin-bottom:14px}
#entete h1{margin:0 0 6px;color:#17365D;font-size:25px}#entete p{margin:0;color:#66788A}
.carte{background:#fff!important;border:1px solid #E7ECF2!important;border-radius:16px!important;padding:6px!important;box-shadow:none!important}
.note{font-size:13px;color:#66788A}.bouton-principal button{font-weight:700!important;border-radius:11px!important}
.pd-wrap{overflow:auto;border:1px solid #E4EAF1;border-radius:14px;background:#fff}.pd-head{padding:11px 14px;background:#F3F6F9;border-bottom:1px solid #E4EAF1;color:#17365D;font-weight:700}
.pd-table{width:100%;min-width:980px;border-collapse:collapse;font-size:12px}.pd-table th{position:sticky;top:0;background:#17365D;color:#fff;padding:7px;white-space:nowrap;text-align:right}.pd-table th:first-child{text-align:left;position:sticky;left:0;z-index:3}.pd-table td{padding:6px 8px;border-right:1px solid #E8EDF3;border-bottom:1px solid #EDF1F5;text-align:right;white-space:nowrap;background:#fff}.pd-table td:first-child{position:sticky;left:0;text-align:left;font-weight:600;color:#243B53}.pd-table tr.total td{background:#DCEEF8;font-weight:700}.pd-table tr.claim td{background:#FCEBDD}.pd-table tr.reserve td{background:#FFF7D6}.pd-table tr.section td{background:#EAF2F8;font-weight:700}.pd-table tr.result td{background:#E3F2D2;font-weight:700}.pd-table tr.ratio td{font-style:italic}.neg{color:#B8322A}
footer{display:none!important}
"""

# -----------------------------------------------------------------------------
# Grilles d'entrée
# -----------------------------------------------------------------------------
def grille_mensuelle(annee: int, valeur=None) -> pd.DataFrame:
    d = {"Mois": [f"{m} {int(annee)}" for m in MOIS]}
    for b in BRANCHES_UI: d[b] = [valeur] * 12
    return pd.DataFrame(d)

def grille_bloc(kind: str) -> pd.DataFrame:
    lignes = DIRECT_BLOCK if kind == "direct" else REASS_BLOCK
    d = {"Ligne": [x[0] for x in lignes]}
    for b in BRANCHES_UI: d[b] = [None] * len(lignes)
    return pd.DataFrame(d)

def _vide(v) -> bool:
    try: return v is None or pd.isna(v) or str(v).strip() == ""
    except Exception: return v is None

def _num(v, default=0.0):
    if _vide(v): return float(default)
    try:
        x=float(str(v).replace(" ","").replace(",","."))
        return x if np.isfinite(x) else float(default)
    except Exception: return float(default)

def _grille_a_bloc(df, kind: str) -> pd.DataFrame:
    d=pd.DataFrame(df).copy(); mapping=DIRECT_BLOCK if kind=="direct" else REASS_BLOCK
    label_to_field=dict(mapping); cols=DIRECT_START_COLUMNS if kind=="direct" else REASS_START_COLUMNS
    rows=[]
    for bui,b in zip(BRANCHES_UI,BRANCHES):
        rec={"branch":b}
        for label,field in mapping:
            m=d[d["Ligne"].astype(str)==label] if "Ligne" in d.columns else pd.DataFrame()
            rec[field]=_num(m.iloc[-1].get(bui)) if not m.empty and bui in m.columns else 0.0
        rows.append(rec)
    return pd.DataFrame(rows,columns=cols)

def _bloc_non_vide(df) -> bool:
    d=pd.DataFrame(df).copy()
    if d.empty: return False
    for c in d.columns:
        if c=="Ligne": continue
        for v in d[c]:
            if not _vide(v) and abs(_num(v))>1e-12: return True
    return False

def _historique_a_long(df, annee: int) -> pd.DataFrame:
    d=pd.DataFrame(df).copy(); rows=[]
    for mi in range(1,13):
        if mi-1>=len(d): break
        r=d.iloc[mi-1]
        for bui,b in zip(BRANCHES_UI,BRANCHES):
            v=r.get(bui)
            if _vide(v): continue
            rows.append({"period":pd.Timestamp(int(annee),mi,1)+pd.offsets.MonthEnd(0),"branch":b,"gwp_ytd":_num(v)})
    return pd.DataFrame(rows)

def _ratio_long(df_ex, df_glob, annee: int) -> pd.DataFrame:
    e=pd.DataFrame(df_ex).copy(); g=pd.DataFrame(df_glob).copy(); rows=[]
    for mi in range(1,13):
        for bui,b in zip(BRANCHES_UI,BRANCHES):
            a=e.iloc[mi-1].get(bui) if mi-1<len(e) else None
            z=g.iloc[mi-1].get(bui) if mi-1<len(g) else None
            if _vide(a) and _vide(z): continue
            rows.append({"period":f"{int(annee)}-{mi:02d}","branch":b,
                         "sp_exercice":None if _vide(a) else _num(a),
                         "sp_global":None if _vide(z) else _num(z)})
    return pd.DataFrame(rows)

def _history_decembre(history, branch):
    d=pd.DataFrame(history)
    if d.empty: return 0.0
    m=d[(d["branch"]==branch)&(pd.to_datetime(d["period"]).dt.month==12)]
    return 0.0 if m.empty else _num(m.iloc[-1].get("gwp_ytd"))

def _incurred_from_block_row(r):
    cur=max(0.0,_num(r.get("paid_current_ytd"))-_num(r.get("recourse_current_ytd")))+_num(r.get("case_close_current"))+_num(r.get("ibnr_close_current"))-_num(r.get("case_open_current"))-_num(r.get("ibnr_open_current"))
    prv=max(0.0,_num(r.get("paid_prior_ytd"))-_num(r.get("recourse_prior_ytd")))+_num(r.get("case_close_prior"))+_num(r.get("ibnr_close_prior"))-_num(r.get("case_open_prior"))-_num(r.get("ibnr_open_prior"))
    return cur,prv

def _completer_depart(dep, arr, history):
    dep=pd.DataFrame(dep).copy(); arr=pd.DataFrame(arr).copy()
    if _bloc_non_vide(pd.DataFrame([{**{"Ligne":"x"}}])): pass
    # Si aucun départ saisi, reconstruire un ancrage minimal depuis décembre historique et les ouvertures du bloc d'arrivée.
    for i,b in enumerate(BRANCHES):
        if abs(_num(dep.loc[i,"gwp_ytd"]))<1e-9:
            dep.loc[i,"gwp_ytd"]=_history_decembre(history,b)
        if not arr.empty:
            # Les ouvertures de l'exercice projeté correspondent aux clôtures du 31/12 précédent.
            if abs(_num(dep.loc[i,"upr_close"]))<1e-9: dep.loc[i,"upr_close"]=_num(arr.loc[i,"upr_open"])
            if abs(_num(dep.loc[i,"case_close_prior"]))<1e-9: dep.loc[i,"case_close_prior"]=_num(arr.loc[i,"case_open_prior"])
            if abs(_num(dep.loc[i,"ibnr_close_prior"]))<1e-9: dep.loc[i,"ibnr_close_prior"]=_num(arr.loc[i,"ibnr_open_prior"])
            if abs(_num(dep.loc[i,"pap_close"]))<1e-9: dep.loc[i,"pap_close"]=_num(arr.loc[i,"pap_open"])
            if abs(_num(dep.loc[i,"pane_close"]))<1e-9: dep.loc[i,"pane_close"]=_num(arr.loc[i,"pane_open"])
    return dep

def _cibles_depuis_bloc_fin(direct_end, reass_end, annee):
    cd=empty_cibles_direct(f"{int(annee)-1}-12",12); cr=empty_cibles_reass(f"{int(annee)-1}-12",12)
    de=pd.DataFrame(direct_end); re=pd.DataFrame(reass_end)
    if not de.empty:
        for _,r in de.iterrows():
            b=r["branch"]; idx=cd.index[(cd["year"]==int(annee))&(cd["branch"]==b)]
            if len(idx):
                i=idx[0]; cur,prv=_incurred_from_block_row(r)
                vals={"gwp_end":r.get("gwp_ytd"),"incurred_current_end":cur,"incurred_prior_end":prv,
                      "paid_current_end":r.get("paid_current_ytd"),"paid_prior_end":r.get("paid_prior_ytd"),
                      "recourse_current_end":r.get("recourse_current_ytd"),"recourse_prior_end":r.get("recourse_prior_ytd"),
                      "commission_end":r.get("commission_ytd"),"upr_close_end":r.get("upr_close")}
                for k,v in vals.items():
                    if abs(_num(v))>1e-12: cd.at[i,k]=_num(v)
    if not re.empty:
        for _,r in re.iterrows():
            b=r["branch"]; idx=cr.index[(cr["year"]==int(annee))&(cr["branch"]==b)]
            if len(idx):
                i=idx[0]
                inc=max(0.0,_num(r.get("recovered_paid_current_ytd")))+max(0.0,_num(r.get("recovered_paid_prior_ytd")))
                vals={"ceded_premium_end":r.get("ceded_premium_ytd"),"recovered_incurred_end":inc,"reass_commission_end":r.get("reass_commission_ytd")}
                for k,v in vals.items():
                    if abs(_num(v))>1e-12: cr.at[i,k]=_num(v)
    return cd,cr

# -----------------------------------------------------------------------------
# IFRS
# -----------------------------------------------------------------------------
def _derive_ifrs_params(direct_local_start, direct_local_end, reass_local_start, reass_local_end,
                        direct_ifrs_start, direct_ifrs_end, reass_ifrs_start, reass_ifrs_end):
    dls=pd.DataFrame(direct_local_start); dle=pd.DataFrame(direct_local_end); rls=pd.DataFrame(reass_local_start); rle=pd.DataFrame(reass_local_end)
    dis=pd.DataFrame(direct_ifrs_start); die=pd.DataFrame(direct_ifrs_end); ris=pd.DataFrame(reass_ifrs_start); rie=pd.DataFrame(reass_ifrs_end)
    rows=[]
    for b in BRANCHES:
        def row(df):
            m=df[df["branch"]==b] if not df.empty and "branch" in df.columns else pd.DataFrame()
            return None if m.empty else m.iloc[-1]
        ld1,ld2,li1,li2=row(dls),row(dle),row(dis),row(die)
        lr1,lr2,ri1,ri2=row(rls),row(rle),row(ris),row(rie)
        coef=1.0
        for l,i in [(ld2,li2),(ld1,li1)]:
            if l is None or i is None: continue
            den=_num(l.get("ibnr_close_current"))+_num(l.get("ibnr_close_prior"))
            num=_num(i.get("ibnr_close_current"))+_num(i.get("ibnr_close_prior"))
            if den>1e-9 and num>0: coef=num/den; break
        rec_rate=0.0
        for l,i in [(lr2,ri2),(lr1,ri1)]:
            if l is None or i is None: continue
            prem=_num(l.get("ceded_premium_ytd")); op=_num(i.get("ceded_upr_open")); cl=_num(i.get("ceded_upr_close"))
            if prem>1e-9 and (abs(op)>1e-9 or abs(cl)>1e-9): rec_rate=(cl-op)/prem; break
        rows.append({"Branche":b,"Coefficient IBNR IFRS":coef,"Taux variation REC IFRS / prime cédée":rec_rate})
    return pd.DataFrame(rows)

def _apply_ifrs(direct, reass, params, ratio_targets_ifrs=None):
    d=pd.DataFrame(direct).copy(); r=pd.DataFrame(reass).copy(); p=pd.DataFrame(params).copy(); diags=[]
    if d.empty: return d,r,pd.DataFrame(diags)
    fmap={str(x["Branche"]):_num(x.get("Coefficient IBNR IFRS"),1) for _,x in p.iterrows()}
    rrmap={str(x["Branche"]):_num(x.get("Taux variation REC IFRS / prime cédée"),0) for _,x in p.iterrows()}
    rt=pd.DataFrame(ratio_targets_ifrs).copy() if ratio_targets_ifrs is not None else pd.DataFrame()
    for idx,x in d.iterrows():
        b=str(x.get("branch")); f=fmap.get(b,1.0)
        for fld in ["ibnr_open_current","ibnr_close_current","ibnr_open_prior","ibnr_close_prior"]:
            d.at[idx,fld]=max(0.0,_num(x.get(fld))*f)
        # Les cibles IFRS mensuelles, si renseignées, sont atteintes uniquement via l'IBNR.
        m=rt[(rt.get("period",pd.Series(dtype=str)).astype(str)==str(pd.Period(x.get("period"),freq="M")))&(rt.get("branch",pd.Series(dtype=str)).astype(str)==b)] if not rt.empty else pd.DataFrame()
        earned=_num(x.get("earned_premium_ytd"))
        if not m.empty and earned>1e-9:
            tr=m.iloc[-1]; spc=None if _vide(tr.get("sp_exercice")) else _num(tr.get("sp_exercice")); spg=None if _vide(tr.get("sp_global")) else _num(tr.get("sp_global"))
            paidc=max(0.0,_num(x.get("paid_current_ytd"))-_num(x.get("recourse_current_ytd")))
            paidp=max(0.0,_num(x.get("paid_prior_ytd"))-_num(x.get("recourse_prior_ytd")))
            if spc is not None:
                target=earned*spc/100.0
                req=target-paidc-_num(x.get("case_close_current"))+_num(d.at[idx,"ibnr_open_current"])+_num(x.get("case_open_current"))
                if req<0: diags.append({"branch":b,"period":str(pd.Period(x.get("period"),freq="M")),"severity":"Cible IFRS non atteignable","message":"Le S/P exercice demandé nécessiterait un IBNR IFRS négatif."})
                d.at[idx,"ibnr_close_current"]=max(0.0,req)
            cur=paidc+_num(x.get("case_close_current"))+_num(d.at[idx,"ibnr_close_current"])-_num(x.get("case_open_current"))-_num(d.at[idx,"ibnr_open_current"])
            if spg is not None:
                target_total=earned*spg/100.0; target_prior=target_total-cur
                req=target_prior-paidp-_num(x.get("case_close_prior"))+_num(d.at[idx,"ibnr_open_prior"])+_num(x.get("case_open_prior"))
                if req<0: diags.append({"branch":b,"period":str(pd.Period(x.get("period"),freq="M")),"severity":"Cible IFRS non atteignable","message":"Le S/P global demandé nécessiterait un IBNR antérieurs IFRS négatif."})
                d.at[idx,"ibnr_close_prior"]=max(0.0,req)
        paidc=max(0.0,_num(x.get("paid_current_ytd"))-_num(x.get("recourse_current_ytd")))
        paidp=max(0.0,_num(x.get("paid_prior_ytd"))-_num(x.get("recourse_prior_ytd")))
        d.at[idx,"incurred_current_ytd"]=paidc+_num(x.get("case_close_current"))+_num(d.at[idx,"ibnr_close_current"])-_num(x.get("case_open_current"))-_num(d.at[idx,"ibnr_open_current"])
        d.at[idx,"incurred_prior_ytd"]=paidp+_num(x.get("case_close_prior"))+_num(d.at[idx,"ibnr_close_prior"])-_num(x.get("case_open_prior"))-_num(d.at[idx,"ibnr_open_prior"])
        d.at[idx,"sp_exercice"]=(d.at[idx,"incurred_current_ytd"]/earned if earned else np.nan)
        d.at[idx,"sp_global"]=(d.at[idx,"incurred_current_ytd"]+d.at[idx,"incurred_prior_ytd"])/earned if earned else np.nan
    for idx,x in r.iterrows():
        b=str(x.get("branch")); rate=rrmap.get(b,0.0); local_open=_num(x.get("ceded_upr_open")); open100=local_open/0.72 if abs(local_open)>1e-12 else 0.0
        close100=max(0.0,open100+_num(x.get("ceded_premium_ytd"))*rate)
        r.at[idx,"ceded_upr_open"]=open100; r.at[idx,"ceded_upr_close"]=close100; r.at[idx,"ceded_upr_variation"]=close100-open100
        r.at[idx,"ceded_earned_premium_ytd"]=_num(x.get("ceded_premium_ytd"))+open100-close100
    # Recalcul des mouvements IFRS après modification IBNR / REC.
    for b,g in d.groupby("branch"):
        ids=list(g.sort_values("period").index); prev=None
        for ix in ids:
            yy=pd.Timestamp(d.at[ix,"period"]).year
            same=prev is not None and pd.Timestamp(d.at[prev,"period"]).year==yy
            d.at[ix,"incurred_current_increment"]=_num(d.at[ix,"incurred_current_ytd"])-(_num(d.at[prev,"incurred_current_ytd"]) if same else 0.0)
            d.at[ix,"incurred_prior_increment"]=_num(d.at[ix,"incurred_prior_ytd"])-(_num(d.at[prev,"incurred_prior_ytd"]) if same else 0.0)
            prev=ix
    for b,g in r.groupby("branch"):
        ids=list(g.sort_values("period").index); prev=None
        for ix in ids:
            yy=pd.Timestamp(r.at[ix,"period"]).year
            same=prev is not None and pd.Timestamp(r.at[prev,"period"]).year==yy
            r.at[ix,"ceded_earned_premium_increment"]=_num(r.at[ix,"ceded_earned_premium_ytd"])-(_num(r.at[prev,"ceded_earned_premium_ytd"]) if same else 0.0)
            prev=ix
    return d,r,pd.DataFrame(diags)

# -----------------------------------------------------------------------------
# Affichages type pd
# -----------------------------------------------------------------------------
def _fmt_money(v):
    try:
        x=float(v); cls=' class="neg"' if x<0 else ''; return f'<span{cls}>{x:,.0f}</span>'.replace(',', ' ')
    except Exception: return "—"

def _fmt_pct(v):
    try:
        x=float(v); cls=' class="neg"' if x<0 else ''; return f'<span{cls}>{x*100:.1f}%</span>'
    except Exception: return "—"

def _table_html(df,title,kind,row_numbers):
    d=pd.DataFrame(df); h=[f'<div class="pd-wrap"><div class="pd-head">{title}</div><table class="pd-table"><thead><tr>']
    for c in d.columns: h.append(f'<th>{c}</th>')
    h.append('</tr></thead><tbody>')
    for i,(_,r) in enumerate(d.iterrows()):
        rr=row_numbers[i] if i<len(row_numbers) else 0; cls=''
        if kind=='direct':
            if rr in {12,16,18,22,38,43,49,61,62,68,69}: cls='total'
            elif rr in {14,15,47,48}: cls='claim'
            elif rr in {36,37,41,42,45,46}: cls='reserve'
            elif rr in {51,57,64,71,75,82,93}: cls='section'
        elif kind=='reass':
            if rr in {12,16,18,22,38,42,46,58,59,65,66}: cls='total'
            elif rr in {14,15}: cls='claim'
            elif rr in {36,37,40,41,44,45}: cls='reserve'
        else:
            if rr in {43,69,114,146,148}: cls='result'
            elif rr in {46,47,48,49,50,72,73,117,118,119,120,121}: cls='ratio'
            elif rr in {7,11,14,15,19,41,55,59,62,63,67,78,82,85,86,90}: cls='total'
        h.append(f'<tr class="{cls}">')
        for j,c in enumerate(d.columns):
            v=r[c]; h.append(f'<td>{v if j==0 else (_fmt_pct(v) if kind=="cpc" and rr in {46,47,48,49,50,72,73,117,118,119,120,121} else _fmt_money(v))}</td>')
        h.append('</tr>')
    h.append('</tbody></table></div>'); return ''.join(h)

def _period_slice(df, index):
    d=pd.DataFrame(df).copy()
    if d.empty: return None,{}
    d['period']=pd.to_datetime(d['period']); ps=sorted(d['period'].drop_duplicates()); idx=max(0,min(len(ps)-1,int(index)-1)); p=ps[idx]
    return p,{r['branch']:r for _,r in d[d['period']==p].iterrows()}

def _local_preview(df,index,kind):
    p,rows=_period_slice(df,index)
    if p is None: return '<div class="pd-wrap"><div class="pd-head">Aucune projection</div></div>'
    labels=DIRECT_LABELS if kind=='direct' else REASS_LABELS; fn=_direct_value if kind=='direct' else _reass_value
    chosen=([7,8,9,10,11,12,14,15,16,18,20,21,22,36,37,38,41,42,45,46,47,48,49,58,59,60,61,62,65,66,67,68,69] if kind=='direct' else [7,8,9,10,11,12,14,15,16,18,20,21,22,36,37,38,40,41,42,44,45,46,55,56,57,58,59,62,63,64,65,66])
    out=[]
    for rr in chosen:
        vals=[fn(rows.get(b),rr) for b in BRANCHES]; corp=sum(vals[BRANCHES.index(b)] for b in CORPORATE_BRANCHES); glob=sum(vals)
        out.append([labels.get(rr,str(rr))]+vals+[corp,glob])
    return _table_html(pd.DataFrame(out,columns=['Ligne']+BRANCHES_UI+['Corporate','Global']),f"{('Direct' if kind=='direct' else 'Réassurance')} · {MOIS[p.month-1]} {p.year}",kind,chosen)

def _cpc_preview(direct,reass,index):
    p,drows=_period_slice(direct,index); _,rrows=_period_slice(reass,index)
    if p is None: return '<div class="pd-wrap"><div class="pd-head">Aucune projection</div></div>'
    rows=[5,6,7,9,10,11,12,13,14,15,17,19,43,46,47,48,50,53,54,55,57,58,59,60,61,62,63,65,67,69,72,73,76,77,78,80,81,82,83,84,85,86,88,90,114,117,118,119,121]
    groups=[('CONSOLIDATION',BRANCHES)]+list(CPC_GROUPS.items()); vals={}
    for n,m in groups: vals[n]=_cpc_values(_sum_metrics(drows,m,_gross_metrics),_sum_metrics(rrows,m,_reass_metrics))
    frame=pd.DataFrame([[CPC_LABELS.get(rr,str(rr))]+[vals[n].get(rr,0) for n,_ in groups] for rr in rows],columns=['Ligne']+[n for n,_ in groups])
    return _table_html(frame,f"CPC SAZ · {MOIS[p.month-1]} {p.year}",'cpc',rows)

# -----------------------------------------------------------------------------
# Hypothèses / pilotage
# -----------------------------------------------------------------------------
def _build_hypotheses(history, annee_projection):
    start=f"{int(annee_projection)-1}-12"; hd=build_hyp_direct(history,start,12); hr=build_hyp_reass(history,pd.DataFrame(),start,12)
    return hd,hr

def _ajustement_grid(hyp, metric, annee):
    h=pd.DataFrame(hyp).copy(); d=grille_mensuelle(annee,0.0)
    if h.empty or not metric: return d
    for mi in range(1,13):
        per=f"{int(annee)}-{mi:02d}"
        for bui,b in zip(BRANCHES_UI,BRANCHES):
            m=h[(h['period'].astype(str)==per)&(h['branch']==b)&(h['metric']==metric)]
            if not m.empty: d.at[mi-1,bui]=_num(m.iloc[-1].get('adjustment_pts'))
    return d

def _appliquer_grille_ajustement(hyp, metric, grid, annee):
    h=pd.DataFrame(hyp).copy(); g=pd.DataFrame(grid)
    if h.empty or not metric: return h
    for mi in range(1,13):
        per=f"{int(annee)}-{mi:02d}"
        for bui,b in zip(BRANCHES_UI,BRANCHES):
            val=_num(g.iloc[mi-1].get(bui)) if mi-1<len(g) else 0.0
            mask=(h['period'].astype(str)==per)&(h['branch']==b)&(h['metric']==metric)
            h.loc[mask,'adjustment_pts']=val
    return h

def _courbe(direct,reass,direct_ifrs,reass_ifrs,history,applied_d,applied_r,referentiel,flux,ligne,branche_ui,annee):
    fig=go.Figure(); b=UI_TO_INTERNAL.get(branche_ui,BRANCHES[0]); df=pd.DataFrame(direct_ifrs if referentiel=='IFRS' and flux=='Direct' else reass_ifrs if referentiel=='IFRS' else direct if flux=='Direct' else reass).copy()
    view=DIRECT_VIEW if flux=='Direct' else REASS_VIEW; field=view.get(ligne)
    if not df.empty and field in df.columns:
        m=df[df['branch']==b].copy(); m['period']=pd.to_datetime(m['period']); m=m.sort_values('period')
        y=m[field].astype(float)
        if field in {'sp_exercice','sp_global','commission_rate_written','cession_rate','recovery_rate','reass_commission_rate'}: y=y*100
        fig.add_trace(go.Scatter(x=MOIS[:len(m)],y=y,mode='lines+markers',name=f'{annee} projeté'))
    if flux=='Direct' and ligne=='Primes émises':
        hist=pd.DataFrame(history)
        if not hist.empty:
            hm=hist[hist['branch']==b].copy(); hm['period']=pd.to_datetime(hm['period']); hm=hm.sort_values('period')
            fig.add_trace(go.Scatter(x=MOIS[:len(hm)],y=hm['gwp_ytd'],mode='lines+markers',name=f'{int(annee)-1} historique',line=dict(dash='dot')))
    driver=(DIRECT_DRIVER if flux=='Direct' else REASS_DRIVER).get(ligne)
    app=pd.DataFrame(applied_d if flux=='Direct' else applied_r)
    if driver and not app.empty:
        a=app[(app['branch']==b)&(app['metric']==driver)].copy()
        if not a.empty:
            fig.add_trace(go.Bar(x=MOIS[:len(a)],y=a['applied_pct'],name='% appliqué',opacity=.22,yaxis='y2'))
            fig.update_layout(yaxis2=dict(overlaying='y',side='right',title='%'))
    fig.update_layout(template='plotly_white',height=440,hovermode='x unified',legend=dict(orientation='h',y=1.08),margin=dict(l=25,r=25,t=45,b=25),title=f'{ligne} · {branche_ui} · {referentiel}')
    return fig

# -----------------------------------------------------------------------------
# Calcul central
# -----------------------------------------------------------------------------
def _calculer(historique, annee_historique, annee_projection,
              dl_dep,dl_fin,rl_dep,rl_fin,di_dep,di_fin,ri_dep,ri_fin,
              sp_loc_ex,sp_loc_glob,sp_ifrs_ex,sp_ifrs_glob,hyp_d,hyp_r):
    hist=_historique_a_long(historique,int(annee_historique)); an=int(annee_projection); start=f'{an-1}-12'
    # Au moins un ancrage Direct Local ou IFRS doit être saisi.
    if not any(_bloc_non_vide(x) for x in [dl_dep,dl_fin,di_dep,di_fin]):
        raise ValueError("Renseignez au minimum un bloc Direct (départ ou arrivée, Local ou IFRS).")
    dl_dep_i=_grille_a_bloc(dl_dep,'direct'); dl_fin_i=_grille_a_bloc(dl_fin,'direct')
    rl_dep_i=_grille_a_bloc(rl_dep,'reass'); rl_fin_i=_grille_a_bloc(rl_fin,'reass')
    di_dep_i=_grille_a_bloc(di_dep,'direct'); di_fin_i=_grille_a_bloc(di_fin,'direct')
    ri_dep_i=_grille_a_bloc(ri_dep,'reass'); ri_fin_i=_grille_a_bloc(ri_fin,'reass')
    # Si seul l'IFRS est renseigné, il initialise le Local ; les écarts IFRS restent ensuite limités à IBNR/REC.
    if not _bloc_non_vide(dl_dep) and _bloc_non_vide(di_dep): dl_dep_i=di_dep_i.copy()
    if not _bloc_non_vide(dl_fin) and _bloc_non_vide(di_fin): dl_fin_i=di_fin_i.copy()
    dl_dep_i=_completer_depart(dl_dep_i,dl_fin_i,hist)
    if pd.DataFrame(hyp_d).empty or pd.DataFrame(hyp_r).empty: hyp_d,hyp_r=_build_hypotheses(hist,an)
    cd,cr=_cibles_depuis_bloc_fin(dl_fin_i if _bloc_non_vide(dl_fin) or _bloc_non_vide(di_fin) else pd.DataFrame(), rl_fin_i if _bloc_non_vide(rl_fin) or _bloc_non_vide(ri_fin) else pd.DataFrame(),an)
    ratios_local=_ratio_long(sp_loc_ex,sp_loc_glob,an)
    d,r,s,diag,apd,apr,hd,hr,cd,cr=run_projection(dl_dep_i,rl_dep_i,pd.DataFrame(hyp_d),pd.DataFrame(hyp_r),cd,cr,start,12,hist,pd.DataFrame(),ratio_targets_local=ratios_local)
    params=_derive_ifrs_params(dl_dep_i,dl_fin_i,rl_dep_i,rl_fin_i,di_dep_i,di_fin_i,ri_dep_i,ri_fin_i)
    ratios_ifrs=_ratio_long(sp_ifrs_ex,sp_ifrs_glob,an)
    di,ri,diag_i=_apply_ifrs(d,r,params,ratios_ifrs)
    si=_summary(di,ri)
    all_diag=pd.concat([pd.DataFrame(diag),pd.DataFrame(diag_i)],ignore_index=True) if len(diag_i) else pd.DataFrame(diag)
    out=Path(tempfile.gettempdir())/'projection_technique_v4.xlsx'
    export_projection(out,{"cibles_direct":cd,"cibles_reass":cr},d,r,s,all_diag,apd,apr,ifrs_params=params)
    return d,r,di,ri,s,si,all_diag,apd,apr,hd,hr,params,str(out),hist

def _recalculer(*args):
    try:
        vals=_calculer(*args)
        d,r,di,ri,s,si,diag,apd,apr,hd,hr,params,out,hist=vals
        msg=f"Projection recalculée sur 12 mois. {len(diag)} contrôle(s) à examiner."
        return msg,d,r,di,ri,s,si,diag,apd,apr,hd,hr,params,out,hist,_local_preview(d,1,'direct'),_local_preview(r,1,'reass'),_cpc_preview(d,r,1),s,si
    except Exception as e:
        vide=pd.DataFrame(); html='<div class="pd-wrap"><div class="pd-head">Aucune projection</div></div>'
        return f"Erreur : {e}",vide,vide,vide,vide,vide,vide,pd.DataFrame([{"Contrôle":str(e)}]),vide,vide,pd.DataFrame(),pd.DataFrame(),pd.DataFrame(),None,pd.DataFrame(),html,html,html,vide,vide

def _changer_bloc(d,r,di,ri,index,referentiel):
    if referentiel=='IFRS': return _local_preview(di,index,'direct'),_local_preview(ri,index,'reass'),_cpc_preview(di,ri,index)
    return _local_preview(d,index,'direct'),_local_preview(r,index,'reass'),_cpc_preview(d,r,index)

def _charger_pilotage(flux,ligne,hyp_d,hyp_r,annee):
    metric=(DIRECT_DRIVER if flux=='Direct' else REASS_DRIVER).get(ligne)
    note=(f"Pilotage actif : {metric}. Saisissez des ajustements en points de pourcentage." if metric else "Cette ligne est calculée. Visualisez-la ici ; son pilotage se fait via ses lignes sources ou les cibles CPC.")
    return _ajustement_grid(hyp_d if flux=='Direct' else hyp_r,metric,int(annee)),note

def _appliquer_grille(flux,ligne,grid,hyp_d,hyp_r,annee):
    metric=(DIRECT_DRIVER if flux=='Direct' else REASS_DRIVER).get(ligne)
    if not metric: return hyp_d,hyp_r,"Ligne calculée : aucun ajustement direct appliqué."
    if flux=='Direct': hyp_d=_appliquer_grille_ajustement(hyp_d,metric,grid,int(annee))
    else: hyp_r=_appliquer_grille_ajustement(hyp_r,metric,grid,int(annee))
    return hyp_d,hyp_r,"Ajustements enregistrés. Recalculez le modèle."

def _appliquer_point(flux,ligne,branche_ui,mois,delta,hyp_d,hyp_r,annee):
    metric=(DIRECT_DRIVER if flux=='Direct' else REASS_DRIVER).get(ligne)
    if not metric: return hyp_d,hyp_r,_ajustement_grid(hyp_d if flux=='Direct' else hyp_r,None,int(annee)),"Cette ligne est calculée et ne possède pas de point de pilotage direct."
    h=pd.DataFrame(hyp_d if flux=='Direct' else hyp_r).copy(); b=UI_TO_INTERNAL[branche_ui]; mi=MOIS.index(mois)+1; per=f"{int(annee)}-{mi:02d}"
    mask=(h['period'].astype(str)==per)&(h['branch']==b)&(h['metric']==metric); h.loc[mask,'adjustment_pts']=_num(delta)
    if flux=='Direct': hyp_d=h
    else: hyp_r=h
    return hyp_d,hyp_r,_ajustement_grid(h,metric,int(annee)),f"{mois} · {branche_ui} : ajustement fixé à {_num(delta):.2f} point(s)."

def _lignes_flux(flux):
    choices=list(DIRECT_VIEW if flux=='Direct' else REASS_VIEW)
    return gr.update(choices=choices,value=choices[0])

def _initialiser(historique,annee_historique,annee_projection):
    hist=_historique_a_long(historique,int(annee_historique)); hd,hr=_build_hypotheses(hist,int(annee_projection))
    return hd,hr,"Historique analysé. La tendance mensuelle des primes a été transformée en hypothèses de progression."

def _maj_annees(annee_hist,annee_proj):
    return (grille_mensuelle(int(annee_hist)),grille_mensuelle(int(annee_proj)),grille_mensuelle(int(annee_proj)),grille_mensuelle(int(annee_proj)),grille_mensuelle(int(annee_proj)))

# -----------------------------------------------------------------------------
# Application
# -----------------------------------------------------------------------------
def build_app():
    with gr.Blocks(title="Projection technique assurance") as demo:
        gr.HTML('<div id="entete"><h1>Projection technique assurance</h1><p>Historique → ancrages → cibles CPC → pilotage des courbes → Direct / Réassurance / CPC en Local et IFRS.</p></div>')

        # États de calcul
        hyp_d_state=gr.State(pd.DataFrame()); hyp_r_state=gr.State(pd.DataFrame())
        d_state=gr.State(pd.DataFrame()); r_state=gr.State(pd.DataFrame()); di_state=gr.State(pd.DataFrame()); ri_state=gr.State(pd.DataFrame())
        s_state=gr.State(pd.DataFrame()); si_state=gr.State(pd.DataFrame()); apd_state=gr.State(pd.DataFrame()); apr_state=gr.State(pd.DataFrame()); hist_state=gr.State(pd.DataFrame())

        with gr.Tab("1 · Historique"):
            gr.Markdown("### Historique des primes\nCollez directement depuis Excel. **Mois en lignes, branches en colonnes**. L'ordre des branches est fixe dans toute l'application.")
            with gr.Row():
                annee_hist=gr.Number(value=2026,precision=0,label="Année historique",minimum=2000,maximum=2100)
                annee_proj=gr.Number(value=2027,precision=0,label="Année à projeter",minimum=2000,maximum=2100)
                maj_annees=gr.Button("Actualiser les années")
            historique=gr.Dataframe(value=grille_mensuelle(2026),type="pandas",interactive=True,label="Primes émises historiques — copier/coller depuis Excel",elem_classes="carte")
            init_btn=gr.Button("Analyser l'historique et préparer les tendances",variant="primary",elem_classes="bouton-principal")
            init_status=gr.Markdown(elem_classes="note")

        with gr.Tab("2 · Blocs de départ / arrivée"):
            gr.Markdown("### Ancrages du modèle\nLe **départ correspond au 31/12 de l'année précédente** et l'**arrivée au 31/12 de l'année projetée**. Vous pouvez coller un bloc depuis Excel. Au minimum un bloc Direct, Local ou IFRS, doit être renseigné.")
            with gr.Tabs():
                with gr.Tab("Direct Local"):
                    with gr.Row():
                        dl_dep=gr.Dataframe(value=grille_bloc('direct'),type="pandas",interactive=True,label="Bloc de départ — Direct Local")
                        dl_fin=gr.Dataframe(value=grille_bloc('direct'),type="pandas",interactive=True,label="Bloc d'arrivée — Direct Local")
                with gr.Tab("Réassurance Local"):
                    with gr.Row():
                        rl_dep=gr.Dataframe(value=grille_bloc('reass'),type="pandas",interactive=True,label="Bloc de départ — Réassurance Local")
                        rl_fin=gr.Dataframe(value=grille_bloc('reass'),type="pandas",interactive=True,label="Bloc d'arrivée — Réassurance Local")
                with gr.Tab("Direct IFRS"):
                    gr.Markdown("Seules les différences d'IBNR sont utilisées pour le passage IFRS ; les autres lignes servent de contrôle et de repère.",elem_classes="note")
                    with gr.Row():
                        di_dep=gr.Dataframe(value=grille_bloc('direct'),type="pandas",interactive=True,label="Bloc de départ — Direct IFRS")
                        di_fin=gr.Dataframe(value=grille_bloc('direct'),type="pandas",interactive=True,label="Bloc d'arrivée — Direct IFRS")
                with gr.Tab("Réassurance IFRS"):
                    gr.Markdown("Seules les différences de REC de réassurance sont utilisées pour le passage IFRS ; les autres lignes servent de contrôle.",elem_classes="note")
                    with gr.Row():
                        ri_dep=gr.Dataframe(value=grille_bloc('reass'),type="pandas",interactive=True,label="Bloc de départ — Réassurance IFRS")
                        ri_fin=gr.Dataframe(value=grille_bloc('reass'),type="pandas",interactive=True,label="Bloc d'arrivée — Réassurance IFRS")

        with gr.Tab("3 · Cibles CPC"):
            gr.Markdown("### Ratios mensuels à atteindre\nSaisissez les ratios en **%** (ex. `55` pour 55 %). Une cellule vide laisse le moteur suivre sa tendance. Les cibles Local modifient la charge/provisions Local ; les cibles IFRS sont atteintes par l'ajustement IBNR IFRS.")
            with gr.Tabs():
                with gr.Tab("Local"):
                    sp_loc_ex=gr.Dataframe(value=grille_mensuelle(2027),type="pandas",interactive=True,label="S/P exercice — Local (%)")
                    sp_loc_glob=gr.Dataframe(value=grille_mensuelle(2027),type="pandas",interactive=True,label="S/P global — Local (%)")
                with gr.Tab("IFRS"):
                    sp_ifrs_ex=gr.Dataframe(value=grille_mensuelle(2027),type="pandas",interactive=True,label="S/P exercice — IFRS (%)")
                    sp_ifrs_glob=gr.Dataframe(value=grille_mensuelle(2027),type="pandas",interactive=True,label="S/P global — IFRS (%)")

        with gr.Tab("4 · Pilotage des courbes"):
            gr.Markdown("### Pilotage ligne par ligne\nChoisissez une ligne, une branche et un mois. Un ajustement de **+1 point** ajoute un point au pourcentage de ce mois. Si un bloc d'arrivée est renseigné, les autres mois sont automatiquement recalibrés pour conserver l'atterrissage.")
            with gr.Row():
                referentiel=gr.Radio(["Local","IFRS"],value="Local",label="Référentiel")
                flux=gr.Radio(["Direct","Réassurance"],value="Direct",label="Flux")
                ligne=gr.Dropdown(choices=list(DIRECT_VIEW),value="Primes émises",label="Ligne")
                branche=gr.Dropdown(choices=BRANCHES_UI,value=BRANCHES_UI[0],label="Branche")
            courbe=gr.Plot(label="Évolution")
            with gr.Row():
                mois_point=gr.Dropdown(choices=MOIS,value="Février",label="Mois à ajuster")
                ajustement_point=gr.Slider(-50,50,value=0,step=.1,label="Ajustement du point (points de %)")
                point_btn=gr.Button("Appliquer le point")
            pilot_note=gr.Markdown(elem_classes="note")
            ajust_grid=gr.Dataframe(value=grille_mensuelle(2027,0.0),type="pandas",interactive=True,label="Ajustements manuels (+/- points) — mois en lignes, branches en colonnes")
            appliquer_grid=gr.Button("Appliquer la grille d'ajustements")
            pilot_status=gr.Markdown(elem_classes="note")

        with gr.Tab("5 · Résultats"):
            with gr.Row():
                resultat_ref=gr.Radio(["Local","IFRS"],value="Local",label="Référentiel affiché")
                bloc=gr.Slider(1,12,value=1,step=1,label="Mois / bloc")
                afficher=gr.Button("Afficher")
            with gr.Tabs():
                with gr.Tab("Direct"): direct_html=gr.HTML('<div class="pd-wrap"><div class="pd-head">Calculez le modèle.</div></div>')
                with gr.Tab("Réassurance"): reass_html=gr.HTML('<div class="pd-wrap"><div class="pd-head">Calculez le modèle.</div></div>')
                with gr.Tab("CPC SAZ"): cpc_html=gr.HTML('<div class="pd-wrap"><div class="pd-head">Calculez le modèle.</div></div>')
            with gr.Row():
                synth_local=gr.Dataframe(interactive=False,label="Synthèse Local")
                synth_ifrs=gr.Dataframe(interactive=False,label="Synthèse IFRS")

        with gr.Tab("6 · Contrôles et export"):
            calculer=gr.Button("Recalculer tout le modèle",variant="primary",elem_classes="bouton-principal")
            statut=gr.Markdown(elem_classes="note")
            diagnostics=gr.Dataframe(interactive=False,label="Contrôles")
            params_ifrs=gr.Dataframe(interactive=False,label="Paramètres IFRS déduits des blocs")
            export=gr.File(label="Classeur Excel final — Direct / Réassurance / CPC")

        # ---- événements ----
        maj_annees.click(_maj_annees,inputs=[annee_hist,annee_proj],outputs=[historique,sp_loc_ex,sp_loc_glob,sp_ifrs_ex,sp_ifrs_glob])
        init_btn.click(_initialiser,inputs=[historique,annee_hist,annee_proj],outputs=[hyp_d_state,hyp_r_state,init_status])
        flux.change(_lignes_flux,inputs=[flux],outputs=[ligne])
        ligne.change(_charger_pilotage,inputs=[flux,ligne,hyp_d_state,hyp_r_state,annee_proj],outputs=[ajust_grid,pilot_note])
        flux.change(_charger_pilotage,inputs=[flux,ligne,hyp_d_state,hyp_r_state,annee_proj],outputs=[ajust_grid,pilot_note])
        point_event=point_btn.click(_appliquer_point,inputs=[flux,ligne,branche,mois_point,ajustement_point,hyp_d_state,hyp_r_state,annee_proj],outputs=[hyp_d_state,hyp_r_state,ajust_grid,pilot_status])

        calc_inputs=[historique,annee_hist,annee_proj,dl_dep,dl_fin,rl_dep,rl_fin,di_dep,di_fin,ri_dep,ri_fin,sp_loc_ex,sp_loc_glob,sp_ifrs_ex,sp_ifrs_glob,hyp_d_state,hyp_r_state]
        calc_outputs=[statut,d_state,r_state,di_state,ri_state,s_state,si_state,diagnostics,apd_state,apr_state,hyp_d_state,hyp_r_state,params_ifrs,export,hist_state,direct_html,reass_html,cpc_html,synth_local,synth_ifrs]
        calculer.click(_recalculer,inputs=calc_inputs,outputs=calc_outputs).then(_courbe,inputs=[d_state,r_state,di_state,ri_state,hist_state,apd_state,apr_state,referentiel,flux,ligne,branche,annee_proj],outputs=[courbe])
        afficher.click(_changer_bloc,inputs=[d_state,r_state,di_state,ri_state,bloc,resultat_ref],outputs=[direct_html,reass_html,cpc_html])
        for comp in [referentiel,flux,ligne,branche]:
            comp.change(_courbe,inputs=[d_state,r_state,di_state,ri_state,hist_state,apd_state,apr_state,referentiel,flux,ligne,branche,annee_proj],outputs=[courbe])
        point_event.then(_recalculer,inputs=calc_inputs,outputs=calc_outputs).then(_courbe,inputs=[d_state,r_state,di_state,ri_state,hist_state,apd_state,apr_state,referentiel,flux,ligne,branche,annee_proj],outputs=[courbe])
        # Pour la grille complète, l'enregistrement puis le recalcul sont chaînés pour éviter toute course entre états.
        grid_event=appliquer_grid.click(_appliquer_grille,inputs=[flux,ligne,ajust_grid,hyp_d_state,hyp_r_state,annee_proj],outputs=[hyp_d_state,hyp_r_state,pilot_status])
        grid_event.then(_recalculer,inputs=calc_inputs,outputs=calc_outputs).then(_courbe,inputs=[d_state,r_state,di_state,ri_state,hist_state,apd_state,apr_state,referentiel,flux,ligne,branche,annee_proj],outputs=[courbe])

    return demo

if __name__ == "__main__":
    app=build_app(); port=int(os.environ.get("PORT","7860")); app.launch(server_name="0.0.0.0",server_port=port,show_error=True,theme=THEME,css=CSS)
