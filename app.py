from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import gradio as gr
from openpyxl import load_workbook

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
    "Automobile", "Santé", "Accident corporel", "Incendie",
    "BDM - Construction", "RC - RC Déc", "RD", "Transport",
]
UI_TO_INTERNAL = dict(zip(BRANCHES_UI, BRANCHES))
INTERNAL_TO_UI = dict(zip(BRANCHES, BRANCHES_UI))
MOIS = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]

# Les libellés ci-dessous reprennent exactement les lignes de pd.xlsx.
# La colonne "Section" permet de distinguer les libellés répétés comme
# "Ouverture", "Clôture Per." et "Clôture Ant.".
DIRECT_BLOCK = [
    ("Production", "Primes Emises", "gwp_ytd"),
    ("PAP / PANE", "PAP Ouverture", "pap_open"),
    ("PAP / PANE", "PAP Clôture", "pap_close"),
    ("PAP / PANE", "PANE Ouverture", "pane_open"),
    ("PAP / PANE", "PANE Clôture", "pane_close"),
    ("Sinistres", "Sinistres payés Per.", "paid_current_ytd"),
    ("Sinistres", "Sinistres payés Ant.", "paid_prior_ytd"),
    ("Commissions", "Commisions", "commission_ytd"),
    ("REC CIMA 72%", "REC Ouverture", "upr_open"),
    ("REC CIMA 72%", "REC Clôture", "upr_close"),
    ("IBNR CIMA", "IBNR Ouverture", "ibnr_open_prior"),
    ("IBNR CIMA", "IBNR Clôture", "ibnr_close_current"),
    ("Recours", "Recours Per.", "recourse_current_ytd"),
    ("Recours", "Recours Per.Anté", "recourse_prior_ytd"),
    ("SAP hors chargement", "Ouverture", "case_open_prior"),
    ("SAP hors chargement", "Clôture Per.", "case_close_current"),
    ("SAP hors chargement", "Clôture Ant.", "case_close_prior"),
]

REASS_BLOCK = [
    ("Production", "Primes Emises", "ceded_premium_ytd"),
    ("PAP / PANE", "PAP Ouverture", None),
    ("PAP / PANE", "PAP Clôture", None),
    ("PAP / PANE", "PANE Ouverture", None),
    ("PAP / PANE", "PANE Clôture", None),
    ("Sinistres", "Sinistres payés Per.", "recovered_paid_current_ytd"),
    ("Sinistres", "Sinistres payés Ant.", "recovered_paid_prior_ytd"),
    ("Commissions", "Commisions", "reass_commission_ytd"),
    ("REC CIMA 72%", "REC Ouverture", "ceded_upr_open"),
    ("REC CIMA 72%", "REC Clôture", "ceded_upr_close"),
    ("REC 100%", "REC Ouverture 100%", None),
    ("REC 100%", "REC Clôture 100%", None),
    ("DAC", "DAC Ouv", None),
    ("DAC", "DAC Clo", None),
    ("IBNR CIMA", "IBNR Ouverture", "recoverable_ibnr_open_prior"),
    ("IBNR CIMA", "IBNR Clôture", "recoverable_ibnr_close_current"),
    ("IBNR BE", "IBNR BE Per.", None),
    ("IBNR BE", "IBNR BE Ant.", None),
    ("SAP hors chargement", "Ouverture", "recoverable_case_open_prior"),
    ("SAP hors chargement", "Clôture Per.", "recoverable_case_close_current"),
    ("SAP hors chargement", "Clôture Ant.", "recoverable_case_close_prior"),
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
    "Taux REC Réassurance / primes cédées": "rec_cession_rate",
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
    "REC cédée clôture": "Taux REC réassurance / primes cédées",
    "Taux REC Réassurance / primes cédées": "Taux REC réassurance / primes cédées",
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
    d = {"Section": [x[0] for x in lignes], "Ligne": [x[1] for x in lignes]}
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
    d=pd.DataFrame(df).copy()
    lignes = DIRECT_BLOCK if kind == "direct" else REASS_BLOCK
    cols = DIRECT_START_COLUMNS if kind == "direct" else REASS_START_COLUMNS
    rows=[]
    for bui,b in zip(BRANCHES_UI,BRANCHES):
        rec={c:0.0 for c in cols if c!="branch"}; rec["branch"]=b
        for section,label,field in lignes:
            if field is None:
                continue
            if "Ligne" not in d.columns:
                m=pd.DataFrame()
            else:
                mask=d["Ligne"].astype(str).str.strip()==label.strip()
                if "Section" in d.columns:
                    mask &= d["Section"].astype(str).str.strip()==section.strip()
                m=d[mask]
            rec[field]=_num(m.iloc[-1].get(bui)) if not m.empty and bui in m.columns else 0.0
        if kind == "direct":
            # Dans pd.xlsx, les ouvertures de l'exercice courant sont nulles.
            rec["case_open_current"]=0.0
            rec["ibnr_open_current"]=0.0
            rec["ibnr_close_prior"]=0.0
        else:
            rec["recoverable_case_open_current"]=0.0
            rec["recoverable_ibnr_open_current"]=0.0
            rec["recoverable_ibnr_close_prior"]=0.0
        rows.append(rec)
    return pd.DataFrame(rows,columns=cols)

def _bloc_non_vide(df) -> bool:
    d=pd.DataFrame(df).copy()
    if d.empty: return False
    for c in d.columns:
        if c in ("Section","Ligne"): continue
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

def _historiques_a_long(hist_n3, hist_n2, hist_n1, annee_n1: int) -> pd.DataFrame:
    frames=[]
    for df,year in [(hist_n3,int(annee_n1)-2),(hist_n2,int(annee_n1)-1),(hist_n1,int(annee_n1))]:
        x=_historique_a_long(df,year)
        if not x.empty: frames.append(x)
    return pd.concat(frames,ignore_index=True) if frames else pd.DataFrame(columns=["period","branch","gwp_ytd"])

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

# Coefficients IBNR IFRS / Local observés dans pd.xlsx.
# Ils servent de point de départ automatique. Les cibles S/P IFRS, lorsqu'elles
# sont renseignées, recalibrent ensuite l'IBNR de clôture nécessaire.
IBNR_IFRS_FACTORS = {
    "Automobile": 0.60,
    "Santé": 0.40,
    "Accident corporel": 1.00,
    "Incendie": 1.00,
    "BDM - Construction": 1.00,
    "RC - RC Déc": 0.70,
    "RD": 1.00,
    "Transport": 0.30,
}

def grille_coefficients_ifrs():
    return pd.DataFrame({
        "Branche": BRANCHES_UI,
        "Coefficient IBNR IFRS / Local": [IBNR_IFRS_FACTORS[b] for b in BRANCHES],
        "Méthode": ["Coefficient pd.xlsx + recalage S/P IFRS"] * len(BRANCHES),
    })

def _ifrs_params_auto():
    return pd.DataFrame([
        {"Branche": b, "ibnr_factor": IBNR_IFRS_FACTORS.get(b, 1.0)} for b in BRANCHES
    ])

def _hyp_reass_from_grids(base_hyp, annee, cession, recovery, rec_upr, commission):
    h=pd.DataFrame(base_hyp).copy()
    grids={
        "Taux cession primes":pd.DataFrame(cession),
        "Taux récupération sinistres":pd.DataFrame(recovery),
        "Taux REC réassurance / primes cédées":pd.DataFrame(rec_upr),
        "Taux commission réassurance":pd.DataFrame(commission),
    }
    for metric,g in grids.items():
        for mi in range(1,13):
            per=f"{int(annee)}-{mi:02d}"
            for bui,b in zip(BRANCHES_UI,BRANCHES):
                if mi-1>=len(g) or bui not in g.columns: continue
                v=g.iloc[mi-1].get(bui)
                if _vide(v): continue
                mask=(h['period'].astype(str)==per)&(h['branch']==b)&(h['metric']==metric)
                h.loc[mask,'base_pct']=_num(v); h.loc[mask,'adjustment_pts']=0.0; h.loc[mask,'source']='Saisie utilisateur'
    return h

def _reass_start_from_direct(direct_start, hyp_reass, annee):
    sr=empty_reass_start(BRANCHES); ds=pd.DataFrame(direct_start); h=pd.DataFrame(hyp_reass)
    per=f"{int(annee)}-01"
    for i,b in enumerate(BRANCHES):
        dr=ds[ds['branch']==b].iloc[-1] if not ds[ds['branch']==b].empty else pd.Series(dtype=float)
        def rate(metric,default):
            m=h[(h['period'].astype(str)==per)&(h['branch']==b)&(h['metric']==metric)]
            if m.empty: return default
            return max(0.0,min(1.0,(_num(m.iloc[-1].get('base_pct'))+_num(m.iloc[-1].get('adjustment_pts')))/100.0))
        cess=rate('Taux cession primes',.25); rec=rate('Taux récupération sinistres',.25); uprr=rate('Taux REC réassurance / primes cédées',.25); comm=rate('Taux commission réassurance',.15)
        ceded=max(0.0,_num(dr.get('gwp_ytd'))*cess)
        sr.loc[i,'ceded_premium_ytd']=ceded; sr.loc[i,'reass_commission_ytd']=ceded*comm
        sr.loc[i,'ceded_upr_open']=ceded*uprr; sr.loc[i,'ceded_upr_close']=ceded*uprr
        case=max(0.0,_num(dr.get('case_close_current'))+_num(dr.get('case_close_prior')))
        ibnr=max(0.0,_num(dr.get('ibnr_close_current'))+_num(dr.get('ibnr_close_prior')))
        sr.loc[i,'recoverable_case_open_prior']=case*rec; sr.loc[i,'recoverable_case_close_prior']=case*rec
        sr.loc[i,'recoverable_ibnr_open_prior']=ibnr*rec; sr.loc[i,'recoverable_ibnr_close_prior']=ibnr*rec
    return sr

# -----------------------------------------------------------------------------
# IFRS
# -----------------------------------------------------------------------------
def _apply_ifrs(direct, reass, ratio_targets_ifrs=None):
    """Construit l'IFRS automatiquement depuis le Local.

    - IBNR: Local × coefficient IFRS/Local par branche ; si une cible S/P IFRS
      est renseignée, la clôture IBNR est recalée au minimum nécessaire.
    - DAC Direct: calculé automatiquement à partir de la REC 100 % (REC/72 %)
      et du taux de commission local.
    - REC Réassurance IFRS: REC locale portée à 100 % (REC/72 %).
    - DAC Réassurance: REC 100 % × taux de commission de réassurance.
    """
    d=pd.DataFrame(direct).copy(); r=pd.DataFrame(reass).copy(); diags=[]
    if d.empty: return d,r,pd.DataFrame(diags)
    rt=pd.DataFrame(ratio_targets_ifrs).copy() if ratio_targets_ifrs is not None else pd.DataFrame()

    for b,g in d.groupby('branch'):
        factor=float(IBNR_IFRS_FACTORS.get(b,1.0))
        ids=list(g.sort_values('period').index)
        for idx in ids:
            x=d.loc[idx]
            # Ouvertures et clôtures IFRS estimées depuis le Local.
            open_cur=max(0.0,_num(x.get('ibnr_open_current'))*factor)
            open_pr=max(0.0,_num(x.get('ibnr_open_prior'))*factor)
            d.at[idx,'ibnr_open_current']=open_cur; d.at[idx,'ibnr_open_prior']=open_pr
            d.at[idx,'ibnr_close_current']=max(0.0,_num(x.get('ibnr_close_current'))*factor)
            d.at[idx,'ibnr_close_prior']=max(0.0,_num(x.get('ibnr_close_prior'))*factor)

            earned=_num(x.get('earned_premium_ytd'))
            period=str(pd.Period(x.get('period'),freq='M'))
            m=rt[(rt.get('period',pd.Series(dtype=str)).astype(str)==period)&(rt.get('branch',pd.Series(dtype=str)).astype(str)==b)] if not rt.empty else pd.DataFrame()
            if not m.empty and earned>1e-9:
                tr=m.iloc[-1]
                spc=None if _vide(tr.get('sp_exercice')) else _num(tr.get('sp_exercice'))
                spg=None if _vide(tr.get('sp_global')) else _num(tr.get('sp_global'))
                paidc=max(0.0,_num(x.get('paid_current_ytd'))-_num(x.get('recourse_current_ytd')))
                paidp=max(0.0,_num(x.get('paid_prior_ytd'))-_num(x.get('recourse_prior_ytd')))
                if spc is not None:
                    req=earned*spc/100.0-paidc-_num(x.get('case_close_current'))+open_cur+_num(x.get('case_open_current'))
                    if req<0:
                        diags.append({'branch':b,'period':period,'severity':'Cible IFRS non atteignable','message':'Le S/P exercice demanderait un IBNR IFRS négatif.'})
                    d.at[idx,'ibnr_close_current']=max(0.0,req)
                cur=paidc+_num(x.get('case_close_current'))+_num(d.at[idx,'ibnr_close_current'])-_num(x.get('case_open_current'))-open_cur
                if spg is not None:
                    req=(earned*spg/100.0-cur)-paidp-_num(x.get('case_close_prior'))+open_pr+_num(x.get('case_open_prior'))
                    if req<0:
                        diags.append({'branch':b,'period':period,'severity':'Cible IFRS non atteignable','message':'Le S/P global demanderait un IBNR antérieurs IFRS négatif.'})
                    d.at[idx,'ibnr_close_prior']=max(0.0,req)

            paidc=max(0.0,_num(x.get('paid_current_ytd'))-_num(x.get('recourse_current_ytd')))
            paidp=max(0.0,_num(x.get('paid_prior_ytd'))-_num(x.get('recourse_prior_ytd')))
            d.at[idx,'incurred_current_ytd']=paidc+_num(x.get('case_close_current'))+_num(d.at[idx,'ibnr_close_current'])-_num(x.get('case_open_current'))-_num(d.at[idx,'ibnr_open_current'])
            d.at[idx,'incurred_prior_ytd']=paidp+_num(x.get('case_close_prior'))+_num(d.at[idx,'ibnr_close_prior'])-_num(x.get('case_open_prior'))-_num(d.at[idx,'ibnr_open_prior'])
            d.at[idx,'sp_exercice']=_num(d.at[idx,'incurred_current_ytd'])/earned if earned else np.nan
            d.at[idx,'sp_global']=(_num(d.at[idx,'incurred_current_ytd'])+_num(d.at[idx,'incurred_prior_ytd']))/earned if earned else np.nan
            d.at[idx,'ibnr_ifrs_factor']=factor

            # DAC calculé depuis le Local : REC 100 % × taux de commission local.
            commission_rate=_num(x.get('commission_ytd'))/_num(x.get('gwp_ytd')) if abs(_num(x.get('gwp_ytd')))>1e-9 else 0.0
            rec100_open=max(0.0,_num(x.get('upr_open'))/0.72)
            rec100_close=max(0.0,_num(x.get('upr_close'))/0.72)
            d.at[idx,'dac_rate']=commission_rate
            d.at[idx,'dac_open']=rec100_open*commission_rate
            d.at[idx,'dac_close']=rec100_close*commission_rate
            d.at[idx,'dac_variation']=d.at[idx,'dac_open']-d.at[idx,'dac_close']

    # Réassurance IFRS calculée directement depuis Reass Local.
    for b,g in r.groupby('branch'):
        ids=list(g.sort_values('period').index)
        open100=None
        for idx in ids:
            x=r.loc[idx]
            if open100 is None:
                open100=max(0.0,_num(x.get('ceded_upr_open'))/0.72)
            close100=max(0.0,_num(x.get('ceded_upr_close'))/0.72)
            r.at[idx,'ceded_upr_open']=open100
            r.at[idx,'ceded_upr_close']=close100
            r.at[idx,'ceded_upr_variation']=close100-open100
            r.at[idx,'ceded_earned_premium_ytd']=_num(x.get('ceded_premium_ytd'))+open100-close100
            r.at[idx,'rec_cession_rate']=close100/_num(x.get('ceded_premium_ytd')) if abs(_num(x.get('ceded_premium_ytd')))>1e-9 else 0.0
            cr=_num(x.get('reass_commission_rate'))
            r.at[idx,'dac_open']=open100*cr
            r.at[idx,'dac_close']=close100*cr
            r.at[idx,'dac_variation']=r.at[idx,'dac_open']-r.at[idx,'dac_close']

    # Recalcul des incréments modifiés.
    for frame,fields in [(d,['incurred_current_ytd','incurred_prior_ytd','dac_variation']),(r,['ceded_earned_premium_ytd','dac_variation'])]:
        for b,g in frame.groupby('branch'):
            prev=None
            for ix in list(g.sort_values('period').index):
                same=prev is not None and pd.Timestamp(frame.at[prev,'period']).year==pd.Timestamp(frame.at[ix,'period']).year
                for fld in fields:
                    key=fld.replace('_ytd','')+'_increment' if fld.endswith('_ytd') else 'dac_increment'
                    frame.at[ix,key]=_num(frame.at[ix,fld])-(_num(frame.at[prev,fld]) if same else 0.0)
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
        if field in {'sp_exercice','sp_global','commission_rate_written','cession_rate','recovery_rate','rec_cession_rate','reass_commission_rate'}: y=y*100
        fig.add_trace(go.Scatter(x=MOIS[:len(m)],y=y,mode='lines+markers',name=f'{annee} projeté'))
    if flux=='Direct' and ligne=='Primes émises':
        hist=pd.DataFrame(history)
        if not hist.empty:
            hm=hist[hist['branch']==b].copy(); hm['period']=pd.to_datetime(hm['period']); hm=hm.sort_values('period')
            for yr,gy in hm.groupby(hm['period'].dt.year):
                gy=gy.sort_values('period')
                fig.add_trace(go.Scatter(x=[MOIS[m-1] for m in gy['period'].dt.month],y=gy['gwp_ytd'],mode='lines+markers',name=f'{int(yr)} historique',line=dict(dash='dot')))
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
def _calculer(hist_n3, hist_n2, hist_n1, annee_historique, annee_projection,
              dl_dep, dl_fin, rl_dep, rl_fin,
              taux_cession, taux_recup, taux_rec_reass, taux_comm_reass,
              sp_loc_ex, sp_loc_glob, sp_ifrs_ex, sp_ifrs_glob, hyp_d, hyp_r):
    hist=_historiques_a_long(hist_n3,hist_n2,hist_n1,int(annee_historique)); an=int(annee_projection); start=f'{an-1}-12'
    if not any(_bloc_non_vide(x) for x in [dl_dep,dl_fin]):
        raise ValueError("Renseignez au minimum un bloc Direct Local : départ ou arrivée.")
    dl_dep_i=_grille_a_bloc(dl_dep,'direct'); dl_fin_i=_grille_a_bloc(dl_fin,'direct')
    rl_dep_i=_grille_a_bloc(rl_dep,'reass'); rl_fin_i=_grille_a_bloc(rl_fin,'reass')
    dl_dep_i=_completer_depart(dl_dep_i,dl_fin_i,hist)
    if pd.DataFrame(hyp_d).empty:
        hyp_d=build_hyp_direct(hist,start,12)
    base_hr=pd.DataFrame(hyp_r).copy() if not pd.DataFrame(hyp_r).empty else build_hyp_reass(hist,pd.DataFrame(),start,12)
    hyp_r=_hyp_reass_from_grids(base_hr,an,taux_cession,taux_recup,taux_rec_reass,taux_comm_reass)
    sr=rl_dep_i if _bloc_non_vide(rl_dep) else _reass_start_from_direct(dl_dep_i,hyp_r,an)
    cd,cr=_cibles_depuis_bloc_fin(
        dl_fin_i if _bloc_non_vide(dl_fin) else pd.DataFrame(),
        rl_fin_i if _bloc_non_vide(rl_fin) else pd.DataFrame(),an)
    ratios_local=_ratio_long(sp_loc_ex,sp_loc_glob,an)
    d,r,s,diag,apd,apr,hd,hr,cd,cr=run_projection(dl_dep_i,sr,pd.DataFrame(hyp_d),pd.DataFrame(hyp_r),cd,cr,start,12,hist,pd.DataFrame(),ratio_targets_local=ratios_local)
    params=_ifrs_params_auto()
    ratios_ifrs=_ratio_long(sp_ifrs_ex,sp_ifrs_glob,an)
    di,ri,diag_i=_apply_ifrs(d,r,ratios_ifrs)
    si=_summary(di,ri)
    all_diag=pd.concat([pd.DataFrame(diag),pd.DataFrame(diag_i)],ignore_index=True) if len(diag_i) else pd.DataFrame(diag)
    out=Path(tempfile.gettempdir())/'projection_technique_v4_5.xlsx'
    export_projection(out,{"cibles_direct":cd,"cibles_reass":cr},d,r,s,all_diag,apd,apr,ifrs_params=params,ratio_targets_ifrs=ratios_ifrs)
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

def _initialiser(hist_n3,hist_n2,hist_n1,annee_historique,annee_projection):
    hist=_historiques_a_long(hist_n3,hist_n2,hist_n1,int(annee_historique)); hd,hr=_build_hypotheses(hist,int(annee_projection))
    return hd,hr,"Historique N-3 à N-1 analysé. Les tendances mensuelles ont été transformées en hypothèses de progression."

def _maj_annees(annee_hist,annee_proj):
    ah=int(annee_hist); ap=int(annee_proj)
    return (grille_mensuelle(ah-2),grille_mensuelle(ah-1),grille_mensuelle(ah),
            grille_mensuelle(ap,25.0),grille_mensuelle(ap,25.0),grille_mensuelle(ap,25.0),grille_mensuelle(ap,15.0),
            grille_mensuelle(ap),grille_mensuelle(ap),grille_mensuelle(ap),grille_mensuelle(ap))

# -----------------------------------------------------------------------------
# Application
# -----------------------------------------------------------------------------
FICHIER_HYPOTHESES = Path(__file__).with_name("hypotheses_forecast_assurance_a_remplir.xlsx")


def _chercher_ligne(ws, texte: str) -> Optional[int]:
    cible=str(texte).strip()
    for row in range(1, int(ws.max_row or 500)+1):
        if str(ws.cell(row,1).value or "").strip()==cible:
            return row
    return None

def _lire_grille_excel(ws, titre: str, annee: int, rows: int=12) -> pd.DataFrame:
    rr=_chercher_ligne(ws,titre)
    if rr is None:
        return grille_mensuelle(annee)
    # Le titre est suivi de l'en-tête, puis des 12 mois.
    start=rr+2
    data={"Mois":[f"{m} {int(annee)}" for m in MOIS]}
    for j,b in enumerate(BRANCHES_UI, start=2):
        data[b]=[ws.cell(start+i,j).value for i in range(rows)]
    return pd.DataFrame(data)

def _lire_bloc_excel(ws, titre: str, kind: str) -> pd.DataFrame:
    rr=_chercher_ligne(ws,titre)
    if rr is None:
        return grille_bloc(kind)
    defs=DIRECT_BLOCK if kind=="direct" else REASS_BLOCK
    start=rr+2
    rows=[]
    for i,(section,label,_) in enumerate(defs):
        row={"Section":section,"Ligne":label}
        # Le classeur de saisie place Section/Ligne en A/B, puis les 8 branches en C:J.
        for j,b in enumerate(BRANCHES_UI,start=3):
            row[b]=ws.cell(start+i,j).value
        rows.append(row)
    return pd.DataFrame(rows)

def _lire_annee_projection(ws, default=2027):
    for row in range(1,min(int(ws.max_row or 500),20)+1):
        if str(ws.cell(row,1).value or "").strip()=="Année projetée N":
            try: return int(ws.cell(row,2).value)
            except Exception: return int(default)
    return int(default)

def _charger_fichier_hypotheses(fichier):
    if not fichier:
        raise gr.Error("Sélectionnez d'abord un fichier d'hypothèses .xlsx.")
    path=str(getattr(fichier,"name",fichier))
    try:
        xls=load_workbook(path,data_only=True,read_only=True)
        for nom in ["Historique","Ancrages modèle","Hyp Réassurance","Cibles CPC"]:
            if nom not in xls.sheetnames:
                raise ValueError(f"Feuille manquante : {nom}")
        wh=xls["Historique"]
        an_proj=_lire_annee_projection(wh,2027)
        an_hist=an_proj-1
        h3=_lire_grille_excel(wh,"PRIMES ÉMISES CUMULÉES — N-3",an_hist-2)
        h2=_lire_grille_excel(wh,"PRIMES ÉMISES CUMULÉES — N-2",an_hist-1)
        h1=_lire_grille_excel(wh,"PRIMES ÉMISES CUMULÉES — N-1",an_hist)

        wa=xls["Ancrages modèle"]
        dd=_lire_bloc_excel(wa,"DIRECT LOCAL — BLOC DE DÉPART","direct")
        df=_lire_bloc_excel(wa,"DIRECT LOCAL — BLOC D'ARRIVÉE","direct")
        rd=_lire_bloc_excel(wa,"REASS LOCAL — BLOC DE DÉPART (OPTIONNEL)","reass")
        rf=_lire_bloc_excel(wa,"REASS LOCAL — BLOC D'ARRIVÉE (OPTIONNEL)","reass")

        wr=xls["Hyp Réassurance"]
        tc=_lire_grille_excel(wr,"Taux de cession des primes",an_proj)
        tr=_lire_grille_excel(wr,"Taux de récupération des sinistres",an_proj)
        tu=_lire_grille_excel(wr,"Taux REC Réassurance / primes cédées",an_proj)
        tm=_lire_grille_excel(wr,"Taux de commission de réassurance (optionnel)",an_proj)

        wc=xls["Cibles CPC"]
        sle=_lire_grille_excel(wc,"LOCAL — S/P exercice",an_proj)
        slg=_lire_grille_excel(wc,"LOCAL — S/P global",an_proj)
        sie=_lire_grille_excel(wc,"IFRS — S/P exercice",an_proj)
        sig=_lire_grille_excel(wc,"IFRS — S/P global",an_proj)

        hist=_historiques_a_long(h3,h2,h1,an_hist)
        hd,hr=_build_hypotheses(hist,an_proj)
        return (an_hist,an_proj,h3,h2,h1,dd,df,rd,rf,tc,tr,tu,tm,sle,slg,sie,sig,hd,hr,
                "Fichier chargé. Les historiques, ancrages, hypothèses de réassurance et cibles CPC ont été réinjectés dans l'application.")
    except Exception as e:
        raise gr.Error(f"Impossible de charger le fichier : {e}")

def build_app():
    with gr.Blocks(title="Projection technique assurance") as demo:
        gr.HTML('<div id="entete"><h1>Projection technique assurance</h1><p>Historique N-3 à N-1 → ancrages Direct / Réassurance → hypothèses Réassurance → cibles CPC → projection Local → passage IFRS automatique.</p></div>')

        hyp_d_state=gr.State(pd.DataFrame()); hyp_r_state=gr.State(pd.DataFrame())
        d_state=gr.State(pd.DataFrame()); r_state=gr.State(pd.DataFrame()); di_state=gr.State(pd.DataFrame()); ri_state=gr.State(pd.DataFrame())
        s_state=gr.State(pd.DataFrame()); si_state=gr.State(pd.DataFrame()); apd_state=gr.State(pd.DataFrame()); apr_state=gr.State(pd.DataFrame()); hist_state=gr.State(pd.DataFrame())

        with gr.Tab("1 · Historique"):
            gr.Markdown("### Données du modèle")
            with gr.Row():
                with gr.Column(scale=1):
                    gr.DownloadButton(
                        "Télécharger le fichier d’hypothèses",
                        value=str(FICHIER_HYPOTHESES),
                        variant="primary",
                        elem_classes="bouton-principal",
                    )
                with gr.Column(scale=2):
                    fichier_import=gr.File(
                        label="Importer le fichier d’hypothèses complété",
                        file_types=[".xlsx"],
                        type="filepath",
                    )
                    charger_fichier=gr.Button("Charger les données du fichier",variant="secondary")
                    import_status=gr.Markdown(elem_classes="note")
            gr.Markdown(
                "### Historique des primes\n"
                "Les trois années servent à analyser la tendance mensuelle. **Mois en lignes, branches en colonnes** dans l’ordre : "
                "**Automobile, Santé, Accident corporel, Incendie, BDM - Construction, RC - RC Déc, RD, Transport**."
            )
            with gr.Row():
                annee_hist=gr.Number(value=2026,precision=0,label="Année N-1",minimum=2000,maximum=2100)
                annee_proj=gr.Number(value=2027,precision=0,label="Année projetée N",minimum=2000,maximum=2100)
                maj_annees=gr.Button("Actualiser les années")
            with gr.Tabs():
                with gr.Tab("N-3"):
                    hist_n3=gr.Dataframe(value=grille_mensuelle(2024),type="pandas",interactive=True,label="Primes émises cumulées — N-3",elem_classes="carte")
                with gr.Tab("N-2"):
                    hist_n2=gr.Dataframe(value=grille_mensuelle(2025),type="pandas",interactive=True,label="Primes émises cumulées — N-2",elem_classes="carte")
                with gr.Tab("N-1"):
                    hist_n1=gr.Dataframe(value=grille_mensuelle(2026),type="pandas",interactive=True,label="Primes émises cumulées — N-1",elem_classes="carte")
            init_btn=gr.Button("Analyser l'historique",variant="primary",elem_classes="bouton-principal")
            init_status=gr.Markdown(elem_classes="note")

        with gr.Tab("2 · Ancrages du modèle"):
            gr.Markdown("### Direct Local\nLes lignes reprennent celles de `Direct Local` dans `pd`. Renseignez **au minimum le bloc de départ ou le bloc d'arrivée**.")
            with gr.Row():
                dl_dep=gr.Dataframe(value=grille_bloc('direct'),type="pandas",interactive=True,label="Bloc de départ — Direct Local")
                dl_fin=gr.Dataframe(value=grille_bloc('direct'),type="pandas",interactive=True,label="Bloc d'arrivée — Direct Local")
            gr.Markdown("### Reass Local — facultatif\nLes lignes reprennent celles de `Reass Local` dans `pd`. Si ces blocs restent vides, la Réassurance est reconstruite depuis les taux mensuels.")
            with gr.Row():
                rl_dep=gr.Dataframe(value=grille_bloc('reass'),type="pandas",interactive=True,label="Bloc de départ — Reass Local (optionnel)")
                rl_fin=gr.Dataframe(value=grille_bloc('reass'),type="pandas",interactive=True,label="Bloc d'arrivée — Reass Local (optionnel)")
            gr.Markdown("### Passage IFRS automatique\nL’IFRS est calculé à partir du Local. L’IBNR utilise un coefficient IFRS/Local par branche, puis les **cibles S/P IFRS** peuvent recalibrer automatiquement la clôture.")
            coef_ifrs=gr.Dataframe(value=grille_coefficients_ifrs(),type="pandas",interactive=False,label="Coefficients IBNR IFRS / Local utilisés",elem_classes="carte")

        with gr.Tab("3 · Hypothèses Réassurance"):
            gr.Markdown("### Réassurance pilotée par taux\nLa **REC Réassurance est indépendante de la REC Direct** : elle est calculée sur les **primes cédées**.")
            taux_cession=gr.Dataframe(value=grille_mensuelle(2027,25.0),type="pandas",interactive=True,label="Taux de cession des primes (%)")
            taux_recup=gr.Dataframe(value=grille_mensuelle(2027,25.0),type="pandas",interactive=True,label="Taux de récupération des sinistres (%)")
            taux_rec_reass=gr.Dataframe(value=grille_mensuelle(2027,25.0),type="pandas",interactive=True,label="Taux REC Réassurance / primes cédées (%)")
            taux_comm_reass=gr.Dataframe(value=grille_mensuelle(2027,15.0),type="pandas",interactive=True,label="Taux de commission de réassurance (%) — optionnel")

        with gr.Tab("4 · Cibles CPC"):
            gr.Markdown("### Ratios mensuels à atteindre\nSaisissez les ratios en **%**. Une cellule vide laisse le moteur suivre la trajectoire issue des hypothèses.")
            with gr.Tabs():
                with gr.Tab("Local"):
                    sp_loc_ex=gr.Dataframe(value=grille_mensuelle(2027),type="pandas",interactive=True,label="S/P exercice — Local (%)")
                    sp_loc_glob=gr.Dataframe(value=grille_mensuelle(2027),type="pandas",interactive=True,label="S/P global — Local (%)")
                with gr.Tab("IFRS"):
                    sp_ifrs_ex=gr.Dataframe(value=grille_mensuelle(2027),type="pandas",interactive=True,label="S/P exercice — IFRS (%)")
                    sp_ifrs_glob=gr.Dataframe(value=grille_mensuelle(2027),type="pandas",interactive=True,label="S/P global — IFRS (%)")

        with gr.Tab("5 · Pilotage interactif"):
            gr.Markdown("### Ajuster une trajectoire\nChaque point modifié agit sur le pourcentage du mois choisi ; le modèle est ensuite recalculé.")
            with gr.Row():
                referentiel=gr.Radio(["Local","IFRS"],value="Local",label="Référentiel")
                flux=gr.Radio(["Direct","Réassurance"],value="Direct",label="Flux")
                ligne=gr.Dropdown(choices=list(DIRECT_VIEW),value="Primes émises",label="Ligne")
                branche=gr.Dropdown(choices=BRANCHES_UI,value=BRANCHES_UI[0],label="Branche")
            courbe=gr.Plot(label="Évolution")
            with gr.Row():
                mois_point=gr.Dropdown(choices=MOIS,value="Février",label="Mois à ajuster")
                ajustement_point=gr.Slider(-50,50,value=0,step=.1,label="Ajustement (points de %)")
                point_btn=gr.Button("Appliquer et recalculer")
            pilot_note=gr.Markdown(elem_classes="note")
            ajust_grid=gr.Dataframe(value=grille_mensuelle(2027,0.0),type="pandas",interactive=True,label="Ajustements manuels (+/- points)")
            appliquer_grid=gr.Button("Appliquer la grille et recalculer")
            pilot_status=gr.Markdown(elem_classes="note")

        with gr.Tab("6 · Résultats"):
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

        with gr.Tab("7 · Contrôles et export"):
            calculer=gr.Button("Recalculer tout le modèle",variant="primary",elem_classes="bouton-principal")
            statut=gr.Markdown(elem_classes="note")
            diagnostics=gr.Dataframe(interactive=False,label="Contrôles")
            params_ifrs=gr.Dataframe(interactive=False,label="Coefficients IFRS appliqués")
            export=gr.File(label="Classeur Excel final — Direct / Réassurance / CPC")

        maj_annees.click(_maj_annees,inputs=[annee_hist,annee_proj],outputs=[hist_n3,hist_n2,hist_n1,taux_cession,taux_recup,taux_rec_reass,taux_comm_reass,sp_loc_ex,sp_loc_glob,sp_ifrs_ex,sp_ifrs_glob])
        init_btn.click(_initialiser,inputs=[hist_n3,hist_n2,hist_n1,annee_hist,annee_proj],outputs=[hyp_d_state,hyp_r_state,init_status])
        charger_fichier.click(_charger_fichier_hypotheses,inputs=[fichier_import],outputs=[annee_hist,annee_proj,hist_n3,hist_n2,hist_n1,dl_dep,dl_fin,rl_dep,rl_fin,taux_cession,taux_recup,taux_rec_reass,taux_comm_reass,sp_loc_ex,sp_loc_glob,sp_ifrs_ex,sp_ifrs_glob,hyp_d_state,hyp_r_state,import_status])
        flux.change(_lignes_flux,inputs=[flux],outputs=[ligne])
        ligne.change(_charger_pilotage,inputs=[flux,ligne,hyp_d_state,hyp_r_state,annee_proj],outputs=[ajust_grid,pilot_note])
        flux.change(_charger_pilotage,inputs=[flux,ligne,hyp_d_state,hyp_r_state,annee_proj],outputs=[ajust_grid,pilot_note])
        point_event=point_btn.click(_appliquer_point,inputs=[flux,ligne,branche,mois_point,ajustement_point,hyp_d_state,hyp_r_state,annee_proj],outputs=[hyp_d_state,hyp_r_state,ajust_grid,pilot_status])

        calc_inputs=[hist_n3,hist_n2,hist_n1,annee_hist,annee_proj,dl_dep,dl_fin,rl_dep,rl_fin,taux_cession,taux_recup,taux_rec_reass,taux_comm_reass,sp_loc_ex,sp_loc_glob,sp_ifrs_ex,sp_ifrs_glob,hyp_d_state,hyp_r_state]
        calc_outputs=[statut,d_state,r_state,di_state,ri_state,s_state,si_state,diagnostics,apd_state,apr_state,hyp_d_state,hyp_r_state,params_ifrs,export,hist_state,direct_html,reass_html,cpc_html,synth_local,synth_ifrs]
        calculer.click(_recalculer,inputs=calc_inputs,outputs=calc_outputs).then(_courbe,inputs=[d_state,r_state,di_state,ri_state,hist_state,apd_state,apr_state,referentiel,flux,ligne,branche,annee_proj],outputs=[courbe])
        afficher.click(_changer_bloc,inputs=[d_state,r_state,di_state,ri_state,bloc,resultat_ref],outputs=[direct_html,reass_html,cpc_html])
        for comp in [referentiel,flux,ligne,branche]:
            comp.change(_courbe,inputs=[d_state,r_state,di_state,ri_state,hist_state,apd_state,apr_state,referentiel,flux,ligne,branche,annee_proj],outputs=[courbe])
        point_event.then(_recalculer,inputs=calc_inputs,outputs=calc_outputs).then(_courbe,inputs=[d_state,r_state,di_state,ri_state,hist_state,apd_state,apr_state,referentiel,flux,ligne,branche,annee_proj],outputs=[courbe])
        grid_event=appliquer_grid.click(_appliquer_grille,inputs=[flux,ligne,ajust_grid,hyp_d_state,hyp_r_state,annee_proj],outputs=[hyp_d_state,hyp_r_state,pilot_status])
        grid_event.then(_recalculer,inputs=calc_inputs,outputs=calc_outputs).then(_courbe,inputs=[d_state,r_state,di_state,ri_state,hist_state,apd_state,apr_state,referentiel,flux,ligne,branche,annee_proj],outputs=[courbe])
    return demo

if __name__ == "__main__":
    app=build_app(); port=int(os.environ.get("PORT","7860")); app.launch(server_name="0.0.0.0",server_port=port,show_error=True,theme=THEME,css=CSS)
