from __future__ import annotations

from typing import Dict, List, Optional, Tuple
import math
import numpy as np
import pandas as pd

BRANCHES = [
    "Automobile", "Santé", "Accident corporel", "Incendie",
    "BDM - Construction", "RC - RC Déc", "RD", "Transport",
]

# -----------------------------------------------------------------------------
# Input blocks
# -----------------------------------------------------------------------------
DIRECT_START_COLUMNS = [
    "branch", "gwp_ytd", "pap_open", "pap_close", "pane_open", "pane_close",
    "commission_ytd", "paid_current_ytd", "paid_prior_ytd", "recourse_current_ytd",
    "recourse_prior_ytd", "upr_open", "upr_close", "case_open_current",
    "case_close_current", "case_open_prior", "case_close_prior", "ibnr_open_current",
    "ibnr_close_current", "ibnr_open_prior", "ibnr_close_prior",
]

REASS_START_COLUMNS = [
    "branch", "ceded_premium_ytd", "reass_commission_ytd", "recovered_paid_current_ytd",
    "recovered_paid_prior_ytd", "ceded_upr_open", "ceded_upr_close",
    "recoverable_case_open_current", "recoverable_case_close_current",
    "recoverable_case_open_prior", "recoverable_case_close_prior",
    "recoverable_ibnr_open_current", "recoverable_ibnr_close_current",
    "recoverable_ibnr_open_prior", "recoverable_ibnr_close_prior",
]

# Hypothesis tables use human-readable percentage points: 5 = 5%.
HYP_COLUMNS = ["period", "branch", "metric", "base_pct", "adjustment_pts"]

DIRECT_METRICS = {
    "Primes Emises": {"kind": "progression", "default": 5.0, "field": "gwp_ytd"},
    "Charge sinistres Per.": {"kind": "progression", "default": 5.0, "field": "incurred_current_ytd"},
    "Charge sinistres Ant.": {"kind": "progression", "default": 2.0, "field": "incurred_prior_ytd"},
    "Sinistres payés Per.": {"kind": "progression", "default": 5.0, "field": "paid_current_ytd"},
    "Sinistres payés Ant.": {"kind": "progression", "default": 5.0, "field": "paid_prior_ytd"},
    "Recours Per.": {"kind": "progression", "default": 0.0, "field": "recourse_current_ytd"},
    "Recours Ant.": {"kind": "progression", "default": 0.0, "field": "recourse_prior_ytd"},
    "Taux commission / primes": {"kind": "rate", "default": 15.0, "field": "commission_rate", "min": 0.0, "max": 100.0},
    # REC/GWP can exceed 100% early in the year because the closing reserve also
    # contains unearned premium originating from the prior year.
    "Taux REC clôture / primes": {"kind": "rate", "default": 20.0, "field": "upr_rate", "min": 0.0, "max": 300.0},
    "Part IBNR Per. / provisions": {"kind": "rate", "default": 25.0, "field": "ibnr_share_current", "min": 0.0, "max": 100.0},
    "Part IBNR Ant. / provisions": {"kind": "rate", "default": 10.0, "field": "ibnr_share_prior", "min": 0.0, "max": 100.0},
}

REASS_METRICS = {
    "Taux cession primes": {"kind": "rate", "default": 25.0, "field": "cession_rate"},
    "Taux récupération sinistres": {"kind": "rate", "default": 25.0, "field": "recovery_rate"},
    "Taux commission réassurance": {"kind": "rate", "default": 15.0, "field": "reass_commission_rate"},
}

CIBLES_DIRECT_COLUMNS = [
    "year", "branch",
    "gwp_start", "gwp_end",
    "incurred_current_start", "incurred_current_end",
    "incurred_prior_start", "incurred_prior_end",
    "paid_current_start", "paid_current_end",
    "paid_prior_start", "paid_prior_end",
    "recourse_current_start", "recourse_current_end",
    "recourse_prior_start", "recourse_prior_end",
    "commission_end", "upr_close_end",
]

CIBLES_REASS_COLUMNS = [
    "year", "branch",
    "ceded_premium_start", "ceded_premium_end",
    "recovered_incurred_start", "recovered_incurred_end",
    "reass_commission_end",
]

DIRECT_TARGET_MAP = {
    "gwp_end": "Primes Emises",
    "incurred_current_end": "Charge sinistres Per.",
    "incurred_prior_end": "Charge sinistres Ant.",
    "paid_current_end": "Sinistres payés Per.",
    "paid_prior_end": "Sinistres payés Ant.",
    "recourse_current_end": "Recours Per.",
    "recourse_prior_end": "Recours Ant.",
}

DIRECT_START_TARGET_MAP = {
    "gwp_start": "gwp_ytd",
    "incurred_current_start": "incurred_current_ytd",
    "incurred_prior_start": "incurred_prior_ytd",
    "paid_current_start": "paid_current_ytd",
    "paid_prior_start": "paid_prior_ytd",
    "recourse_current_start": "recourse_current_ytd",
    "recourse_prior_start": "recourse_prior_ytd",
}


def _num(v, default=0.0) -> float:
    if v is None:
        return float(default)
    try:
        if pd.isna(v):
            return float(default)
    except Exception:
        pass
    try:
        x = float(v)
        return x if math.isfinite(x) else float(default)
    except Exception:
        return float(default)


def _opt_num(v):
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except Exception:
        pass
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def _safe_ratio(a, b):
    b = _num(b)
    return _num(a) / b if abs(b) > 1e-9 else np.nan


def _rate_from_points(v: float, lo: float = -0.99, hi: float = 5.0) -> float:
    return float(np.clip(_num(v) / 100.0, lo, hi))


def empty_direct_start(branches=BRANCHES):
    rows=[]
    for b in branches:
        r={c:0.0 for c in DIRECT_START_COLUMNS if c!="branch"}; r["branch"]=b; rows.append(r)
    return pd.DataFrame(rows)[DIRECT_START_COLUMNS]


def empty_reass_start(branches=BRANCHES):
    rows=[]
    for b in branches:
        r={c:0.0 for c in REASS_START_COLUMNS if c!="branch"}; r["branch"]=b; rows.append(r)
    return pd.DataFrame(rows)[REASS_START_COLUMNS]


def month_range(start_period: str, n_periods: int) -> List[pd.Timestamp]:
    p=pd.Period(str(start_period),freq="M")
    return [(p+i).to_timestamp("M") for i in range(1,int(n_periods)+1)]


def projection_years(start_period: str, n_periods: int) -> List[int]:
    return sorted({p.year for p in month_range(start_period,n_periods)})


def empty_cibles_direct(start_period: str, n_periods: int, branches=BRANCHES):
    rows=[]
    for y in projection_years(start_period,n_periods):
        for b in branches:
            r={c:np.nan for c in CIBLES_DIRECT_COLUMNS if c not in ("year","branch")}
            r.update({"year":y,"branch":b}); rows.append(r)
    return pd.DataFrame(rows)[CIBLES_DIRECT_COLUMNS]


def empty_cibles_reass(start_period: str, n_periods: int, branches=BRANCHES):
    rows=[]
    for y in projection_years(start_period,n_periods):
        for b in branches:
            r={c:np.nan for c in CIBLES_REASS_COLUMNS if c not in ("year","branch")}
            r.update({"year":y,"branch":b}); rows.append(r)
    return pd.DataFrame(rows)[CIBLES_REASS_COLUMNS]


def _normalize_start(df: Optional[pd.DataFrame], cols, branches=BRANCHES):
    base = empty_direct_start(branches) if cols==DIRECT_START_COLUMNS else empty_reass_start(branches)
    if df is None or len(df)==0:
        return base
    d=pd.DataFrame(df).copy()
    if "branch" not in d.columns:
        return base
    for c in cols:
        if c not in d.columns:
            d[c]=0.0 if c!="branch" else ""
    d=d[cols]
    out=base.set_index("branch")
    for _,r in d.iterrows():
        b=r.get("branch")
        if b in out.index:
            for c in cols[1:]: out.loc[b,c]=_num(r.get(c))
    return out.reset_index()[cols]


def _incurred_from_direct_row(r: pd.Series) -> Tuple[float,float]:
    cur=(
        _num(r.get("paid_current_ytd"))-_num(r.get("recourse_current_ytd"))
        +_num(r.get("case_close_current"))+_num(r.get("ibnr_close_current"))
        -_num(r.get("case_open_current"))-_num(r.get("ibnr_open_current"))
    )
    prior=(
        _num(r.get("paid_prior_ytd"))-_num(r.get("recourse_prior_ytd"))
        +_num(r.get("case_close_prior"))+_num(r.get("ibnr_close_prior"))
        -_num(r.get("case_open_prior"))-_num(r.get("ibnr_open_prior"))
    )
    return cur,prior


def _recovered_incurred_from_row(r: pd.Series) -> Tuple[float,float]:
    cur=(
        _num(r.get("recovered_paid_current_ytd"))
        +_num(r.get("recoverable_case_close_current"))+_num(r.get("recoverable_ibnr_close_current"))
        -_num(r.get("recoverable_case_open_current"))-_num(r.get("recoverable_ibnr_open_current"))
    )
    prior=(
        _num(r.get("recovered_paid_prior_ytd"))
        +_num(r.get("recoverable_case_close_prior"))+_num(r.get("recoverable_ibnr_close_prior"))
        -_num(r.get("recoverable_case_open_prior"))-_num(r.get("recoverable_ibnr_open_prior"))
    )
    return cur,prior


def _history_direct_enriched(history_direct: Optional[pd.DataFrame]) -> pd.DataFrame:
    if history_direct is None or len(history_direct)==0:
        return pd.DataFrame()
    d=pd.DataFrame(history_direct).copy()
    if "period" not in d.columns or "branch" not in d.columns:
        return pd.DataFrame()
    d["period"]=pd.to_datetime(d["period"])
    vals=[]
    for _,r in d.iterrows():
        cur,prior=_incurred_from_direct_row(r)
        rr=r.to_dict(); rr["incurred_current_ytd"]=cur; rr["incurred_prior_ytd"]=prior; vals.append(rr)
    return pd.DataFrame(vals).sort_values(["branch","period"])


def _history_reass_enriched(history_reass: Optional[pd.DataFrame]) -> pd.DataFrame:
    if history_reass is None or len(history_reass)==0:
        return pd.DataFrame()
    d=pd.DataFrame(history_reass).copy()
    if "period" not in d.columns or "branch" not in d.columns:
        return pd.DataFrame()
    d["period"]=pd.to_datetime(d["period"])
    vals=[]
    for _,r in d.iterrows():
        cur,prior=_recovered_incurred_from_row(r)
        rr=r.to_dict(); rr["recovered_incurred_current_ytd"]=cur; rr["recovered_incurred_prior_ytd"]=prior; vals.append(rr)
    return pd.DataFrame(vals).sort_values(["branch","period"])


def _progression_samples(d: pd.DataFrame, branch: str, field: str, month: int) -> List[float]:
    if d.empty or field not in d.columns:
        return []
    g=d[d["branch"]==branch].sort_values("period")
    out=[]
    for _,r in g.iterrows():
        p=pd.Timestamp(r["period"])
        if p.month!=month: continue
        prev_period=(p-pd.offsets.MonthEnd(1)).to_period("M")
        prev=g[g["period"].dt.to_period("M")==prev_period]
        if prev.empty: continue
        a=_num(prev.iloc[-1].get(field)); b=_num(r.get(field))
        if abs(a)>1e-6:
            x=(b/a-1.0)*100.0
            if math.isfinite(x) and -99.5 <= x <= 1000:
                out.append(x)
    return out


def _rate_samples_direct(d: pd.DataFrame, branch: str, metric: str, month: int) -> List[float]:
    if d.empty: return []
    g=d[(d["branch"]==branch)&(d["period"].dt.month==month)]
    out=[]
    for _,r in g.iterrows():
        gwp=_num(r.get("gwp_ytd"))
        if metric=="Taux commission / primes" and gwp>0:
            out.append(100*_num(r.get("commission_ytd"))/gwp)
        elif metric=="Taux REC clôture / primes" and gwp>0:
            out.append(100*_num(r.get("upr_close"))/gwp)
        elif metric=="Part IBNR Per. / provisions":
            tot=_num(r.get("case_close_current"))+_num(r.get("ibnr_close_current"))
            if tot>0: out.append(100*_num(r.get("ibnr_close_current"))/tot)
        elif metric=="Part IBNR Ant. / provisions":
            tot=_num(r.get("case_close_prior"))+_num(r.get("ibnr_close_prior"))
            if tot>0: out.append(100*_num(r.get("ibnr_close_prior"))/tot)
    return [x for x in out if math.isfinite(x)]


def _historical_pct_direct(d: pd.DataFrame, branch: str, metric: str, month: int) -> Tuple[float,str]:
    meta=DIRECT_METRICS[metric]
    if meta["kind"]=="progression":
        s=_progression_samples(d,branch,meta["field"],month)
    else:
        s=_rate_samples_direct(d,branch,metric,month)
    if s:
        v=float(np.nanmedian(s)); source="Historique"
        if meta["kind"]=="rate":
            bounded=float(np.clip(v,meta.get("min",0.0),meta.get("max",100.0)))
        else:
            bounded=float(np.clip(v,-95.0,500.0))
        if abs(bounded-v)>1e-9: source="Historique borné"
        return bounded,source
    # January is a YTD reset when no historical pair is available.
    if meta["kind"]=="progression" and month==1:
        return -91.67,"Reset annuel estimé"
    return float(meta["default"]),"Défaut"


def build_hyp_direct(history_direct: Optional[pd.DataFrame], start_period: str, n_periods: int) -> pd.DataFrame:
    d=_history_direct_enriched(history_direct)
    rows=[]
    for p in month_range(start_period,n_periods):
        for b in BRANCHES:
            for metric in DIRECT_METRICS:
                base,source=_historical_pct_direct(d,b,metric,p.month)
                rows.append({"period":str(pd.Period(p,freq="M")),"branch":b,"metric":metric,"base_pct":base,"adjustment_pts":0.0,"source":source})
    return pd.DataFrame(rows)[HYP_COLUMNS+["source"]]


def _reass_rate_samples(hd: pd.DataFrame, hr: pd.DataFrame, branch: str, metric: str, month: int) -> List[float]:
    if hr.empty: return []
    r=hr[(hr["branch"]==branch)&(hr["period"].dt.month==month)]
    out=[]
    if metric=="Taux commission réassurance":
        for _,x in r.iterrows():
            cp=_num(x.get("ceded_premium_ytd"))
            if cp>0: out.append(100*_num(x.get("reass_commission_ytd"))/cp)
        return out
    if hd.empty: return []
    g=hd[(hd["branch"]==branch)&(hd["period"].dt.month==month)]
    m=pd.merge(g,r,on="period",suffixes=("_d","_r")) if not g.empty and not r.empty else pd.DataFrame()
    for _,x in m.iterrows():
        if metric=="Taux cession primes":
            den=_num(x.get("gwp_ytd")); num=_num(x.get("ceded_premium_ytd"))
        else:
            den=_num(x.get("incurred_current_ytd"))+_num(x.get("incurred_prior_ytd"))
            num=_num(x.get("recovered_incurred_current_ytd"))+_num(x.get("recovered_incurred_prior_ytd"))
        if abs(den)>1e-6:
            out.append(100*num/den)
    return out


def build_hyp_reass(history_direct: Optional[pd.DataFrame], history_reass: Optional[pd.DataFrame], start_period: str, n_periods: int) -> pd.DataFrame:
    hd=_history_direct_enriched(history_direct); hr=_history_reass_enriched(history_reass)
    rows=[]
    for p in month_range(start_period,n_periods):
        for b in BRANCHES:
            for metric,meta in REASS_METRICS.items():
                s=_reass_rate_samples(hd,hr,b,metric,p.month)
                base=float(np.nanmedian(s)) if s else float(meta["default"])
                rows.append({"period":str(pd.Period(p,freq="M")),"branch":b,"metric":metric,"base_pct":base,"adjustment_pts":0.0,"source":"Historique" if s else "Défaut"})
    return pd.DataFrame(rows)[HYP_COLUMNS+["source"]]


def normalize_hyp(df: Optional[pd.DataFrame], expected: pd.DataFrame) -> pd.DataFrame:
    e=expected.copy()
    if df is None or len(df)==0:
        return e
    d=pd.DataFrame(df).copy()
    for c in ["period","branch","metric","base_pct","adjustment_pts"]:
        if c not in d.columns:
            d[c]=np.nan
    d["period"]=d["period"].astype(str)
    key=["period","branch","metric"]
    e=e.set_index(key)
    d=d.set_index(key)
    for idx in e.index:
        if idx in d.index:
            for c in ["base_pct","adjustment_pts"]:
                v=_opt_num(d.loc[idx,c] if not isinstance(d.loc[idx,c],pd.Series) else d.loc[idx,c].iloc[0])
                if v is not None: e.loc[idx,c]=v
    return e.reset_index()


def normalize_cibles(df: Optional[pd.DataFrame], columns: List[str], start_period: str, n_periods: int) -> pd.DataFrame:
    base=empty_cibles_direct(start_period,n_periods) if columns==CIBLES_DIRECT_COLUMNS else empty_cibles_reass(start_period,n_periods)
    if df is None or len(df)==0: return base
    d=pd.DataFrame(df).copy()
    for c in columns:
        if c not in d.columns: d[c]=np.nan
    out=base.set_index(["year","branch"])
    for _,r in d.iterrows():
        try: key=(int(float(r.get("year"))),r.get("branch"))
        except Exception: continue
        if key not in out.index: continue
        for c in columns[2:]:
            v=_opt_num(r.get(c))
            if v is not None: out.loc[key,c]=v
    return out.reset_index()[columns]


def _hyp_lookup(hyp: pd.DataFrame, period: pd.Timestamp, branch: str, metric: str) -> Tuple[float,float]:
    p=str(pd.Period(period,freq="M"))
    x=hyp[(hyp["period"].astype(str)==p)&(hyp["branch"]==branch)&(hyp["metric"]==metric)]
    if x.empty:
        return DIRECT_METRICS.get(metric,REASS_METRICS.get(metric,{"default":0.0}))["default"],0.0
    r=x.iloc[0]
    return _num(r.get("base_pct")),_num(r.get("adjustment_pts"))


def _target_row(cibles: pd.DataFrame, year: int, branch: str) -> Optional[pd.Series]:
    if cibles is None or len(cibles)==0: return None
    x=cibles[(pd.to_numeric(cibles["year"],errors="coerce")==year)&(cibles["branch"]==branch)]
    return None if x.empty else x.iloc[0]


def _solve_uniform_adjustment(start: float, target: float, pcts: List[float]) -> Optional[float]:
    if target is None or not math.isfinite(target) or start is None or not math.isfinite(start): return None
    if len(pcts)==0: return None
    if abs(start)<1e-9:
        return None
    def f(adj):
        v=float(start)
        for p in pcts:
            factor=1.0+(p+adj)/100.0
            if factor<=0: return -1e300
            v*=factor
        return v-target
    lo=max(-99.0-min(pcts)+1e-6,-500.0); hi=500.0
    flo=f(lo); fhi=f(hi)
    if not math.isfinite(flo) or not math.isfinite(fhi) or flo*fhi>0:
        return None
    for _ in range(100):
        mid=(lo+hi)/2; fm=f(mid)
        if abs(fm)<=max(1.0,abs(target)*1e-10): return mid
        if flo*fm<=0: hi=mid
        else: lo=mid; flo=fm
    return (lo+hi)/2


def _initial_state(row: pd.Series) -> Dict[str,float]:
    cur,prior=_incurred_from_direct_row(row)
    return {
        "gwp_ytd":_num(row.get("gwp_ytd")),
        "pap_open":_num(row.get("pap_open")),"pap_close":_num(row.get("pap_close")),
        "pane_open":_num(row.get("pane_open")),"pane_close":_num(row.get("pane_close")),
        "commission_ytd":_num(row.get("commission_ytd")),
        "paid_current_ytd":_num(row.get("paid_current_ytd")),"paid_prior_ytd":_num(row.get("paid_prior_ytd")),
        "recourse_current_ytd":_num(row.get("recourse_current_ytd")),"recourse_prior_ytd":_num(row.get("recourse_prior_ytd")),
        "upr_open":max(0.0,_num(row.get("upr_open"))),"upr_close":max(0.0,_num(row.get("upr_close"))),
        "case_open_current":max(0.0,_num(row.get("case_open_current"))),"case_close_current":max(0.0,_num(row.get("case_close_current"))),
        "case_open_prior":max(0.0,_num(row.get("case_open_prior"))),"case_close_prior":max(0.0,_num(row.get("case_close_prior"))),
        "ibnr_open_current":max(0.0,_num(row.get("ibnr_open_current"))),"ibnr_close_current":max(0.0,_num(row.get("ibnr_close_current"))),
        "ibnr_open_prior":max(0.0,_num(row.get("ibnr_open_prior"))),"ibnr_close_prior":max(0.0,_num(row.get("ibnr_close_prior"))),
        "incurred_current_ytd":cur,"incurred_prior_ytd":prior,
    }


def _metric_state_field(metric: str) -> str:
    return DIRECT_METRICS[metric]["field"]


def _year_adjustments_for_direct(
    branch: str, year: int, periods: List[pd.Timestamp], state_before: Dict[str,float], hyp: pd.DataFrame,
    cible: Optional[pd.Series], start_override: Dict[str,float]
) -> Dict[str,float]:
    out={m:0.0 for m in DIRECT_METRICS}
    # Progression targets: one transparent uniform +/-Y point shift over free months.
    for target_col,metric in DIRECT_TARGET_MAP.items():
        if cible is None: continue
        target=_opt_num(cible.get(target_col))
        if target is None: continue
        field=_metric_state_field(metric)
        start_val=start_override.get(field,state_before.get(field,0.0))
        free_periods=periods[:]
        # When a January start value is explicitly provided, January is an anchor, not a growth step.
        start_col=target_col.replace("_end","_start")
        if periods and periods[0].month==1 and cible is not None and _opt_num(cible.get(start_col)) is not None:
            free_periods=periods[1:]
        pcts=[]
        for p in free_periods:
            b,a=_hyp_lookup(hyp,p,branch,metric); pcts.append(b+a)
        adj=_solve_uniform_adjustment(start_val,target,pcts)
        if adj is not None: out[metric]=adj

    # Amount targets for commission and REC are translated into rate targets.
    # First estimate year-end GWP using the already-calibrated premium progression.
    gwp_start=start_override.get("gwp_ytd",state_before.get("gwp_ytd",0.0))
    gwp_periods=periods[:]
    if periods and periods[0].month==1 and "gwp_ytd" in start_override:
        gwp_periods=periods[1:]
    gwp_end=float(gwp_start)
    for pp in gwp_periods:
        b,a=_hyp_lookup(hyp,pp,branch,"Primes Emises")
        gwp_end*=max(0.0,1.0+(b+a+out.get("Primes Emises",0.0))/100.0)
    if cible is not None and periods:
        for target_col,metric in [("commission_end","Taux commission / primes"),("upr_close_end","Taux REC clôture / primes")]:
            target=_opt_num(cible.get(target_col))
            if target is None or gwp_end<=1e-9: continue
            desired=100.0*target/gwp_end
            b,a=_hyp_lookup(hyp,periods[-1],branch,metric)
            out[metric]=desired-(b+a)
    return out


def _project_direct(
    sd: pd.DataFrame, hyp: pd.DataFrame, cibles: pd.DataFrame, start_period: str, n_periods: int
) -> Tuple[pd.DataFrame,pd.DataFrame,List[dict]]:
    periods=month_range(start_period,n_periods); start_p=pd.Period(start_period,freq="M")
    rows=[]; applied_rows=[]; diagnostics=[]
    for branch in BRANCHES:
        sr=sd[sd["branch"]==branch].iloc[0]
        state=_initial_state(sr)
        prev_period=start_p.to_timestamp("M")
        prev_earned=state["gwp_ytd"]+state["upr_open"]-state["upr_close"]
        # Cache annual opening balances; fixed throughout each calendar year.
        annual_open={
            "year":prev_period.year,
            "upr_open":state["upr_open"],
            "case_open_current":state["case_open_current"],"case_open_prior":state["case_open_prior"],
            "ibnr_open_current":state["ibnr_open_current"],"ibnr_open_prior":state["ibnr_open_prior"],
            "pap_open":state["pap_open"],"pap_close":state["pap_close"],"pane_open":state["pane_open"],"pane_close":state["pane_close"],
        }
        grouped: Dict[int,List[pd.Timestamp]]={}
        for p in periods: grouped.setdefault(p.year,[]).append(p)
        year_adjustments={}
        year_start_overrides={}
        for year in sorted(grouped):
            ps=grouped[year]
            cible=_target_row(cibles,year,branch)
            ov={}
            if ps and ps[0].month==1 and cible is not None:
                for c,f in DIRECT_START_TARGET_MAP.items():
                    v=_opt_num(cible.get(c))
                    if v is not None: ov[f]=v
            year_start_overrides[year]=ov
            # The state_before is exact for the first projection year. For later years,
            # target adjustment will be refreshed lazily when that year starts.
            if year==ps[0].year and year==periods[0].year:
                year_adjustments[year]=_year_adjustments_for_direct(branch,year,ps,state,hyp,cible,ov)

        current_year=None
        year_adj={m:0.0 for m in DIRECT_METRICS}
        for p in periods:
            new_year=(current_year is None and p.year!=prev_period.year) or (current_year is not None and p.year!=current_year)
            if new_year:
                # December closing becomes the new annual opening. Current-year claim opening is zero;
                # all outstanding claims enter the prior-year opening bucket.
                annual_open={
                    "year":p.year,
                    "upr_open":max(0.0,state["upr_close"]),
                    "case_open_current":0.0,
                    "case_open_prior":max(0.0,state["case_close_current"]+state["case_close_prior"]),
                    "ibnr_open_current":0.0,
                    "ibnr_open_prior":max(0.0,state["ibnr_close_current"]+state["ibnr_close_prior"]),
                    "pap_open":state["pap_close"],"pap_close":state["pap_close"],
                    "pane_open":state["pane_close"],"pane_close":state["pane_close"],
                }
                prev_earned=0.0
            current_year=p.year
            ps=grouped[p.year]; cible=_target_row(cibles,p.year,branch); ov=year_start_overrides.get(p.year,{})
            if p==ps[0]:
                year_adj=_year_adjustments_for_direct(branch,p.year,ps,state,hyp,cible,ov)

            vals={}
            applied={}
            for metric,meta in DIRECT_METRICS.items():
                base,manual=_hyp_lookup(hyp,p,branch,metric)
                target_adj=year_adj.get(metric,0.0)
                pct=base+manual+target_adj
                # Rate hypotheses have business bounds.
                if meta["kind"]=="rate": pct=float(np.clip(pct,meta.get("min",0.0),meta.get("max",100.0)))
                else: pct=max(pct,-99.0)
                applied[metric]=(base,manual,target_adj,pct)

            jan_anchor=(p.month==1 and p==ps[0])
            def progress(metric,field,nonnegative=True):
                if jan_anchor and field in ov:
                    v=ov[field]
                else:
                    v=state[field]*(1.0+applied[metric][3]/100.0)
                return max(0.0,v) if nonnegative else v

            vals["gwp_ytd"]=progress("Primes Emises","gwp_ytd")
            vals["incurred_current_ytd"]=progress("Charge sinistres Per.","incurred_current_ytd")
            vals["incurred_prior_ytd"]=progress("Charge sinistres Ant.","incurred_prior_ytd",nonnegative=False)
            vals["paid_current_ytd"]=progress("Sinistres payés Per.","paid_current_ytd")
            vals["paid_prior_ytd"]=progress("Sinistres payés Ant.","paid_prior_ytd")
            vals["recourse_current_ytd"]=progress("Recours Per.","recourse_current_ytd")
            vals["recourse_prior_ytd"]=progress("Recours Ant.","recourse_prior_ytd")

            # Cumulative gross paid cannot be below recourse.
            vals["recourse_current_ytd"]=min(vals["recourse_current_ytd"],vals["paid_current_ytd"])
            vals["recourse_prior_ytd"]=min(vals["recourse_prior_ytd"],vals["paid_prior_ytd"])

            # Openings fixed through the year.
            for f in ["upr_open","case_open_current","case_open_prior","ibnr_open_current","ibnr_open_prior","pap_open","pap_close","pane_open","pane_close"]:
                vals[f]=annual_open[f]

            # Commission and REC are rates applied to written premium, per user specification.
            commission_rate=applied["Taux commission / primes"][3]/100.0
            upr_rate=applied["Taux REC clôture / primes"][3]/100.0
            vals["commission_ytd"]=vals["gwp_ytd"]*commission_rate
            vals["upr_close"]=max(0.0,vals["gwp_ytd"]*upr_rate)
            earned=vals["gwp_ytd"]+vals["upr_open"]-vals["upr_close"]
            if earned+1e-6 < prev_earned:
                vals["upr_close"]=max(0.0,vals["gwp_ytd"]+vals["upr_open"]-prev_earned)
                earned=prev_earned
                diagnostics.append({"branch":branch,"period":str(pd.Period(p,freq='M')),"severity":"Correction cohérence","message":"REC clôture plafonnée afin de garantir une prime acquise cumulée non décroissante."})
            vals["earned_premium_ytd"]=max(0.0,earned); prev_earned=vals["earned_premium_ytd"]
            vals["upr_variation"]=vals["upr_close"]-vals["upr_open"]

            # Reserve identity: Charge = paid - recours + closing reserve - opening reserve.
            open_cur=vals["case_open_current"]+vals["ibnr_open_current"]
            open_pr=vals["case_open_prior"]+vals["ibnr_open_prior"]
            close_cur=open_cur+vals["incurred_current_ytd"]-(vals["paid_current_ytd"]-vals["recourse_current_ytd"])
            close_pr=open_pr+vals["incurred_prior_ytd"]-(vals["paid_prior_ytd"]-vals["recourse_prior_ytd"])
            if close_cur<0:
                vals["incurred_current_ytd"]=(vals["paid_current_ytd"]-vals["recourse_current_ytd"])-open_cur
                close_cur=0.0
                diagnostics.append({"branch":branch,"period":str(pd.Period(p,freq='M')),"severity":"Correction cohérence","message":"Charge exercice ajustée: la projection aurait produit des provisions courantes négatives."})
            if close_pr<0:
                vals["incurred_prior_ytd"]=(vals["paid_prior_ytd"]-vals["recourse_prior_ytd"])-open_pr
                close_pr=0.0
                diagnostics.append({"branch":branch,"period":str(pd.Period(p,freq='M')),"severity":"Correction cohérence","message":"Charge antérieurs ajustée: la projection aurait produit des provisions antérieures négatives."})
            sh_cur=applied["Part IBNR Per. / provisions"][3]/100.0
            sh_pr=applied["Part IBNR Ant. / provisions"][3]/100.0
            vals["ibnr_close_current"]=close_cur*sh_cur; vals["case_close_current"]=close_cur-vals["ibnr_close_current"]
            vals["ibnr_close_prior"]=close_pr*sh_pr; vals["case_close_prior"]=close_pr-vals["ibnr_close_prior"]
            vals["revenue"]=vals["gwp_ytd"]+vals["pap_open"]-vals["pap_close"]+vals["pane_open"]-vals["pane_close"]

            # Period movements. At January YTD resets; the January amount is the period movement.
            same_year=(p.year==prev_period.year)
            def inc(field): return vals[field]-state[field] if same_year else vals[field]
            vals["gwp_increment"]=inc("gwp_ytd")
            vals["earned_premium_increment"]=vals["earned_premium_ytd"]-(state.get("earned_premium_ytd",state["gwp_ytd"]+state["upr_open"]-state["upr_close"]) if same_year else 0.0)
            vals["commission_increment"]=inc("commission_ytd")
            vals["incurred_current_increment"]=inc("incurred_current_ytd")
            vals["incurred_prior_increment"]=inc("incurred_prior_ytd")
            vals["sp_exercice"]=_safe_ratio(vals["incurred_current_ytd"],vals["earned_premium_ytd"])
            vals["sp_global"]=_safe_ratio(vals["incurred_current_ytd"]+vals["incurred_prior_ytd"],vals["earned_premium_ytd"])
            vals["commission_rate_written"]=_safe_ratio(vals["commission_ytd"],vals["gwp_ytd"])
            vals["commission_ratio_earned"]=_safe_ratio(vals["commission_ytd"],vals["earned_premium_ytd"])
            vals["combined_ratio_before_general_expenses"]=(vals["sp_global"]+vals["commission_ratio_earned"] if np.isfinite(vals["sp_global"]) and np.isfinite(vals["commission_ratio_earned"]) else np.nan)
            vals["period"]=p; vals["branch"]=branch
            rows.append(vals)
            for metric,(base,manual,tadj,pct) in applied.items():
                applied_rows.append({"period":str(pd.Period(p,freq='M')),"branch":branch,"metric":metric,"base_pct":base,"adjustment_pts":manual,"target_adjustment_pts":tadj,"applied_pct":pct})
            state.update(vals); prev_period=p
    return pd.DataFrame(rows),pd.DataFrame(applied_rows),diagnostics


def _reass_target_adjustments(direct: pd.DataFrame, hyp: pd.DataFrame, cibles: pd.DataFrame, periods: List[pd.Timestamp], branch: str):
    out={}
    for year in sorted({p.year for p in periods}):
        ps=[p for p in periods if p.year==year]
        cible=_target_row(cibles,year,branch); shifts={m:(0.0,0.0) for m in REASS_METRICS}
        if cible is None or not ps:
            out[year]=shifts; continue
        first,last=ps[0],ps[-1]
        dlast=direct[(direct['period']==last)&(direct['branch']==branch)].iloc[0]
        dfirst=direct[(direct['period']==first)&(direct['branch']==branch)].iloc[0]
        # Cession: derive shifts required at beginning/end when targets are provided.
        cs=_opt_num(cible.get('ceded_premium_start')); ce=_opt_num(cible.get('ceded_premium_end'))
        b0,a0=_hyp_lookup(hyp,first,branch,'Taux cession primes'); b1,a1=_hyp_lookup(hyp,last,branch,'Taux cession primes')
        y0=(100*cs/_num(dfirst.get('gwp_ytd'))-(b0+a0)) if cs is not None and _num(dfirst.get('gwp_ytd'))>1e-9 else None
        y1=(100*ce/_num(dlast.get('gwp_ytd'))-(b1+a1)) if ce is not None and _num(dlast.get('gwp_ytd'))>1e-9 else None
        if y0 is None and y1 is not None: y0=y1
        if y1 is None and y0 is not None: y1=y0
        if y0 is not None: shifts['Taux cession primes']=(y0,y1)
        # Recovery uses gross incurred claims.
        rs=_opt_num(cible.get('recovered_incurred_start')); re=_opt_num(cible.get('recovered_incurred_end'))
        inc0=_num(dfirst.get('incurred_current_ytd'))+_num(dfirst.get('incurred_prior_ytd')); inc1=_num(dlast.get('incurred_current_ytd'))+_num(dlast.get('incurred_prior_ytd'))
        b0,a0=_hyp_lookup(hyp,first,branch,'Taux récupération sinistres'); b1,a1=_hyp_lookup(hyp,last,branch,'Taux récupération sinistres')
        y0=(100*rs/inc0-(b0+a0)) if rs is not None and abs(inc0)>1e-9 else None
        y1=(100*re/inc1-(b1+a1)) if re is not None and abs(inc1)>1e-9 else None
        if y0 is None and y1 is not None: y0=y1
        if y1 is None and y0 is not None: y1=y0
        if y0 is not None: shifts['Taux récupération sinistres']=(y0,y1)
        # Commission end target uses expected ceded premium at year-end after cession adjustment.
        rc=_opt_num(cible.get('reass_commission_end'))
        if rc is not None:
            cshift=shifts['Taux cession primes'][1]
            bc,ac=_hyp_lookup(hyp,last,branch,'Taux cession primes'); cess=float(np.clip((bc+ac+cshift)/100.0,0,1))
            ceded_end=_num(dlast.get('gwp_ytd'))*cess
            br,ar=_hyp_lookup(hyp,last,branch,'Taux commission réassurance')
            if ceded_end>1e-9:
                y=100*rc/ceded_end-(br+ar); shifts['Taux commission réassurance']=(y,y)
        out[year]=shifts
    return out


def _project_reass(
    direct: pd.DataFrame, sr: pd.DataFrame, hyp: pd.DataFrame, cibles: pd.DataFrame,
    start_period: str, n_periods: int
) -> Tuple[pd.DataFrame,pd.DataFrame,List[dict]]:
    periods=month_range(start_period,n_periods); rows=[]; applied_rows=[]; diagnostics=[]
    for branch in BRANCHES:
        r0=sr[sr["branch"]==branch].iloc[0]
        state={c:_num(r0.get(c)) for c in REASS_START_COLUMNS if c!="branch"}
        prev_period=pd.Period(start_period,freq="M").to_timestamp("M")
        annual_open={
            "year":prev_period.year,
            "ceded_upr_open":max(0.0,state["ceded_upr_open"]),
            "recoverable_case_open_current":max(0.0,state["recoverable_case_open_current"]),
            "recoverable_case_open_prior":max(0.0,state["recoverable_case_open_prior"]),
            "recoverable_ibnr_open_current":max(0.0,state["recoverable_ibnr_open_current"]),
            "recoverable_ibnr_open_prior":max(0.0,state["recoverable_ibnr_open_prior"]),
        }
        prev_ceded_earned=state["ceded_premium_ytd"]+state["ceded_upr_open"]-state["ceded_upr_close"]
        target_shifts=_reass_target_adjustments(direct,hyp,cibles,periods,branch)
        for p in periods:
            d=direct[(direct["period"]==p)&(direct["branch"]==branch)].iloc[0]
            if p.year!=prev_period.year:
                annual_open={
                    "year":p.year,
                    "ceded_upr_open":max(0.0,state["ceded_upr_close"]),
                    "recoverable_case_open_current":0.0,
                    "recoverable_case_open_prior":max(0.0,state["recoverable_case_close_current"]+state["recoverable_case_close_prior"]),
                    "recoverable_ibnr_open_current":0.0,
                    "recoverable_ibnr_open_prior":max(0.0,state["recoverable_ibnr_close_current"]+state["recoverable_ibnr_close_prior"]),
                }
                prev_ceded_earned=0.0
            cible=_target_row(cibles,p.year,branch)
            applied={}
            year_ps=[x for x in periods if x.year==p.year]; pos=year_ps.index(p); frac=(pos/(len(year_ps)-1)) if len(year_ps)>1 else 1.0
            for metric,meta in REASS_METRICS.items():
                base,manual=_hyp_lookup(hyp,p,branch,metric)
                y0,y1=target_shifts.get(p.year,{}).get(metric,(0.0,0.0)); target_adj=y0+(y1-y0)*frac
                pct=float(np.clip(base+manual+target_adj,0.0,100.0)); applied[metric]=[base,manual,target_adj,pct]

            cession=applied["Taux cession primes"][3]/100.0
            recovery=applied["Taux récupération sinistres"][3]/100.0
            # When the imported Reass opening is missing (e.g. Direct/Reass calendars
            # do not match), synthesise it once from the gross annual opening and the
            # selected cession/recovery rates. It then remains fixed for the year.
            if abs(annual_open["ceded_upr_open"])<1e-9 and _num(d.get("upr_open"))>0:
                annual_open["ceded_upr_open"]=_num(d.get("upr_open"))*cession
            gross_case_open_cur=_num(d.get("case_open_current")); gross_case_open_pr=_num(d.get("case_open_prior"))
            gross_ibnr_open_cur=_num(d.get("ibnr_open_current")); gross_ibnr_open_pr=_num(d.get("ibnr_open_prior"))
            if abs(annual_open["recoverable_case_open_current"])+abs(annual_open["recoverable_ibnr_open_current"])<1e-9 and gross_case_open_cur+gross_ibnr_open_cur>0:
                annual_open["recoverable_case_open_current"]=gross_case_open_cur*recovery; annual_open["recoverable_ibnr_open_current"]=gross_ibnr_open_cur*recovery
            if abs(annual_open["recoverable_case_open_prior"])+abs(annual_open["recoverable_ibnr_open_prior"])<1e-9 and gross_case_open_pr+gross_ibnr_open_pr>0:
                annual_open["recoverable_case_open_prior"]=gross_case_open_pr*recovery; annual_open["recoverable_ibnr_open_prior"]=gross_ibnr_open_pr*recovery
            ceded=_num(d.get("gwp_ytd"))*cession
            gross_inc=_num(d.get("incurred_current_ytd"))+_num(d.get("incurred_prior_ytd"))

            vals={"period":p,"branch":branch,"cession_rate":cession,"claim_recovery_current":recovery,"claim_recovery_prior":recovery,"recovery_rate":recovery}
            vals["ceded_premium_ytd"]=ceded
            vals["ceded_upr_open"]=annual_open["ceded_upr_open"]
            vals["ceded_upr_close"]=max(0.0,_num(d.get("upr_close"))*cession)
            vals["ceded_earned_premium_ytd"]=vals["ceded_premium_ytd"]+vals["ceded_upr_open"]-vals["ceded_upr_close"]
            if vals["ceded_earned_premium_ytd"]+1e-6<prev_ceded_earned:
                vals["ceded_upr_close"]=max(0.0,vals["ceded_premium_ytd"]+vals["ceded_upr_open"]-prev_ceded_earned)
                vals["ceded_earned_premium_ytd"]=prev_ceded_earned
            prev_ceded_earned=vals["ceded_earned_premium_ytd"]
            vals["ceded_upr_variation"]=vals["ceded_upr_close"]-vals["ceded_upr_open"]

            # Reinsurance is explicitly percentage-driven from the gross incurred charge.
            # Openings stay fixed; the closing recoverable reserve absorbs the accounting
            # movement required by the selected recovery percentage.
            vals["recoverable_case_open_current"]=annual_open["recoverable_case_open_current"]
            vals["recoverable_case_open_prior"]=annual_open["recoverable_case_open_prior"]
            vals["recoverable_ibnr_open_current"]=annual_open["recoverable_ibnr_open_current"]
            vals["recoverable_ibnr_open_prior"]=annual_open["recoverable_ibnr_open_prior"]
            vals["recovered_incurred_current_ytd"]=_num(d.get("incurred_current_ytd"))*recovery
            vals["recovered_incurred_prior_ytd"]=_num(d.get("incurred_prior_ytd"))*recovery
            vals["recovered_paid_current_ytd"]=max(0.0,_num(d.get("paid_current_ytd"))-_num(d.get("recourse_current_ytd")))*recovery
            vals["recovered_paid_prior_ytd"]=max(0.0,_num(d.get("paid_prior_ytd"))-_num(d.get("recourse_prior_ytd")))*recovery
            open_cur=vals["recoverable_case_open_current"]+vals["recoverable_ibnr_open_current"]
            open_pr=vals["recoverable_case_open_prior"]+vals["recoverable_ibnr_open_prior"]
            close_cur=max(0.0,open_cur+vals["recovered_incurred_current_ytd"]-vals["recovered_paid_current_ytd"])
            close_pr=max(0.0,open_pr+vals["recovered_incurred_prior_ytd"]-vals["recovered_paid_prior_ytd"])
            gross_cur=_num(d.get("case_close_current"))+_num(d.get("ibnr_close_current")); gross_pr=_num(d.get("case_close_prior"))+_num(d.get("ibnr_close_prior"))
            ibshare_cur=_safe_ratio(_num(d.get("ibnr_close_current")),gross_cur) if gross_cur>1e-9 else 0.0
            ibshare_pr=_safe_ratio(_num(d.get("ibnr_close_prior")),gross_pr) if gross_pr>1e-9 else 0.0
            ibshare_cur=0.0 if not np.isfinite(ibshare_cur) else float(np.clip(ibshare_cur,0,1)); ibshare_pr=0.0 if not np.isfinite(ibshare_pr) else float(np.clip(ibshare_pr,0,1))
            vals["recoverable_ibnr_close_current"]=close_cur*ibshare_cur; vals["recoverable_case_close_current"]=close_cur-vals["recoverable_ibnr_close_current"]
            vals["recoverable_ibnr_close_prior"]=close_pr*ibshare_pr; vals["recoverable_case_close_prior"]=close_pr-vals["recoverable_ibnr_close_prior"]

            comm_rate=applied["Taux commission réassurance"][3]/100.0
            vals["reass_commission_rate"]=comm_rate; vals["reass_commission_ytd"]=ceded*comm_rate

            same_year=(p.year==prev_period.year)
            def incr(field): return vals[field]-state.get(field,0.0) if same_year else vals[field]
            vals["ceded_premium_increment"]=incr("ceded_premium_ytd")
            vals["ceded_earned_premium_increment"]=vals["ceded_earned_premium_ytd"]-(state.get("ceded_earned_premium_ytd",state["ceded_premium_ytd"]+state["ceded_upr_open"]-state["ceded_upr_close"]) if same_year else 0.0)
            vals["reass_commission_increment"]=incr("reass_commission_ytd")
            vals["recovered_incurred_current_increment"]=vals["recovered_incurred_current_ytd"]-(state.get("recovered_incurred_current_ytd",0.0) if same_year else 0.0)
            vals["recovered_incurred_prior_increment"]=vals["recovered_incurred_prior_ytd"]-(state.get("recovered_incurred_prior_ytd",0.0) if same_year else 0.0)
            vals["cession_rate_written_ytd"]=_safe_ratio(vals["ceded_premium_ytd"],d.get("gwp_ytd"))
            vals["cession_rate_earned_ytd"]=_safe_ratio(vals["ceded_earned_premium_ytd"],d.get("earned_premium_ytd"))
            vals["recovery_ratio_global_ytd"]=_safe_ratio(vals["recovered_incurred_current_ytd"]+vals["recovered_incurred_prior_ytd"],gross_inc)
            rows.append(vals)
            for metric,(base,manual,tadj,pct) in applied.items():
                applied_rows.append({"period":str(pd.Period(p,freq='M')),"branch":branch,"metric":metric,"base_pct":base,"adjustment_pts":manual,"target_adjustment_pts":tadj,"applied_pct":pct})
            state.update(vals); prev_period=p
    return pd.DataFrame(rows),pd.DataFrame(applied_rows),diagnostics


def _summary(direct: pd.DataFrame,reass: pd.DataFrame) -> pd.DataFrame:
    rows=[]
    for p,dg in direct.groupby("period"):
        rg=reass[reass["period"]==p]
        gross_written=dg["gwp_increment"].sum(); gross_earned=dg["earned_premium_increment"].sum()
        gross_inc=dg["incurred_current_increment"].sum()+dg["incurred_prior_increment"].sum(); gross_comm=dg["commission_increment"].sum()
        ceded_written=rg["ceded_premium_increment"].sum(); ceded_earned=rg["ceded_earned_premium_increment"].sum()
        rec_inc=rg["recovered_incurred_current_increment"].sum()+rg["recovered_incurred_prior_increment"].sum(); reass_comm=rg["reass_commission_increment"].sum()
        net_earned=gross_earned-ceded_earned; net_inc=gross_inc-rec_inc; net_comm=gross_comm-reass_comm
        tech=net_earned-net_inc-net_comm
        gey=dg["earned_premium_ytd"].sum(); giy=(dg["incurred_current_ytd"]+dg["incurred_prior_ytd"]).sum(); gicy=dg["incurred_current_ytd"].sum(); gcy=dg["commission_ytd"].sum(); gwy=dg["gwp_ytd"].sum()
        cey=rg["ceded_earned_premium_ytd"].sum(); cwy=rg["ceded_premium_ytd"].sum(); riy=(rg["recovered_incurred_current_ytd"]+rg["recovered_incurred_prior_ytd"]).sum(); rcy=rg["reass_commission_ytd"].sum()
        ney=gey-cey; niy=giy-riy; ncy=gcy-rcy
        rows.append({
            "period":p,"gross_written_premium":gross_written,"gross_earned_premium":gross_earned,"gross_incurred_claims":gross_inc,"gross_commission":gross_comm,
            "ceded_written_premium":ceded_written,"ceded_earned_premium":ceded_earned,"recovered_incurred_claims":rec_inc,"reinsurance_commission":reass_comm,
            "net_earned_premium":net_earned,"net_incurred_claims":net_inc,"net_commission":net_comm,"technical_result_before_general_expenses":tech,
            "gross_sp_exercice_ytd":_safe_ratio(gicy,gey),"gross_sp_global_ytd":_safe_ratio(giy,gey),"gross_commission_ratio_ytd":_safe_ratio(gcy,gey),
            "gross_combined_ratio_before_general_expenses_ytd":_safe_ratio(giy,gey)+_safe_ratio(gcy,gey) if abs(gey)>1e-9 else np.nan,
            "written_cession_rate_ytd":_safe_ratio(cwy,gwy),"earned_cession_rate_ytd":_safe_ratio(cey,gey),"claims_recovery_rate_ytd":_safe_ratio(riy,giy),
            "net_loss_ratio_ytd":_safe_ratio(niy,ney),"net_commission_ratio_ytd":_safe_ratio(ncy,ney),
            "net_combined_ratio_before_general_expenses_ytd":_safe_ratio(niy,ney)+_safe_ratio(ncy,ney) if abs(ney)>1e-9 else np.nan,
        })
    return pd.DataFrame(rows)


def run_projection(
    start_direct: pd.DataFrame, start_reass: pd.DataFrame,
    hyp_direct: pd.DataFrame, hyp_reass: pd.DataFrame,
    cibles_direct: pd.DataFrame, cibles_reass: pd.DataFrame,
    start_period: str, n_periods: int,
    history_direct: Optional[pd.DataFrame]=None, history_reass: Optional[pd.DataFrame]=None,
):
    n=int(n_periods)
    if n<1 or n>120: raise ValueError("Le nombre de périodes doit être compris entre 1 et 120.")
    sd=_normalize_start(start_direct,DIRECT_START_COLUMNS); sr=_normalize_start(start_reass,REASS_START_COLUMNS)
    expected_hd=build_hyp_direct(history_direct,start_period,n); expected_hr=build_hyp_reass(history_direct,history_reass,start_period,n)
    hd=normalize_hyp(hyp_direct,expected_hd); hr=normalize_hyp(hyp_reass,expected_hr)
    cd=normalize_cibles(cibles_direct,CIBLES_DIRECT_COLUMNS,start_period,n); cr=normalize_cibles(cibles_reass,CIBLES_REASS_COLUMNS,start_period,n)
    direct,applied_d,diag_d=_project_direct(sd,hd,cd,start_period,n)
    reass,applied_r,diag_r=_project_reass(direct,sr,hr,cr,start_period,n)
    summary=_summary(direct,reass)
    diagnostics=list(diag_d)+list(diag_r)
    # Structural controls.
    for b,g in direct.groupby("branch"):
        for y,yg in g.groupby(pd.to_datetime(g["period"]).dt.year):
            yg=yg.sort_values("period")
            for f in ["upr_open","case_open_current","case_open_prior","ibnr_open_current","ibnr_open_prior","pap_open","pap_close","pane_open","pane_close"]:
                if yg[f].max()-yg[f].min()>1.0:
                    diagnostics.append({"branch":b,"period":str(y),"severity":"Erreur structurelle","message":f"{f} varie dans l'exercice alors qu'il doit rester fixe."})
            if (np.diff(yg["earned_premium_ytd"].to_numpy(float))<-1.0).any():
                diagnostics.append({"branch":b,"period":str(y),"severity":"Erreur structurelle","message":"Prime acquise cumulée décroissante détectée."})
    # Flag unusually large user/historical progression assumptions without silently
    # overwriting them. January resets are excluded from this check.
    for _,x in applied_d.iterrows():
        if x.get("metric") in DIRECT_METRICS and DIRECT_METRICS[x.get("metric")]["kind"]=="progression":
            try: month=int(str(x.get("period"))[5:7])
            except Exception: month=0
            pct=_num(x.get("applied_pct"))
            if month!=1 and (pct>250 or pct<-80):
                diagnostics.append({"branch":x.get("branch"),"period":x.get("period"),"severity":"Hypothèse à vérifier","message":f"{x.get('metric')}: progression appliquée {pct:.1f}% ; vérifier qu'elle est volontaire."})
    diag=pd.DataFrame(diagnostics,columns=["branch","period","severity","message"]) if diagnostics else pd.DataFrame(columns=["branch","period","severity","message"])
    return direct,reass,summary,diag,applied_d,applied_r,hd,hr,cd,cr


def make_legacy_direct_block(direct: pd.DataFrame) -> pd.DataFrame:
    rows=[]
    for _,r in pd.DataFrame(direct).iterrows():
        vals={
            "Primes Emises":r.get("gwp_ytd",0),"PAP Ouverture":r.get("pap_open",0),"PAP Clôture":r.get("pap_close",0),"PANE Ouverture":r.get("pane_open",0),"PANE Clôture":r.get("pane_close",0),
            "Chiffre d'Affaire":r.get("revenue",0),"Sinistres payés Per.":r.get("paid_current_ytd",0),"Sinistres payés Ant.":r.get("paid_prior_ytd",0),
            "Sinistres Payés net des recours":_num(r.get("paid_current_ytd"))+_num(r.get("paid_prior_ytd"))-_num(r.get("recourse_current_ytd"))-_num(r.get("recourse_prior_ytd")),
            "Commissions":r.get("commission_ytd",0),"REC Ouverture":r.get("upr_open",0),"REC Clôture":r.get("upr_close",0),"Variation de REC":r.get("upr_variation",0),"Primes acquises":r.get("earned_premium_ytd",0),
            "IBNR Ouverture Per.":r.get("ibnr_open_current",0),"IBNR Clôture Per.":r.get("ibnr_close_current",0),"IBNR Ouverture Ant.":r.get("ibnr_open_prior",0),"IBNR Clôture Ant.":r.get("ibnr_close_prior",0),
            "SAP Ouverture Per.":r.get("case_open_current",0),"SAP Clôture Per.":r.get("case_close_current",0),"SAP Ouverture Ant.":r.get("case_open_prior",0),"SAP Clôture Ant.":r.get("case_close_prior",0),
            "S/P de l'exercice":r.get("sp_exercice",np.nan),"S/P global":r.get("sp_global",np.nan),"taux commissions":r.get("commission_ratio_earned",np.nan),"taux commissions / primes émises":r.get("commission_rate_written",np.nan),
        }
        for line,v in vals.items(): rows.append({"period":r.get("period"),"branch":r.get("branch"),"line":line,"value":v})
    return pd.DataFrame(rows)


def make_legacy_reass_block(reass: pd.DataFrame) -> pd.DataFrame:
    rows=[]
    for _,r in pd.DataFrame(reass).iterrows():
        vals={
            "Primes Emises":r.get("ceded_premium_ytd",0),"Commissions":r.get("reass_commission_ytd",0),"Sinistres payés Per.":r.get("recovered_paid_current_ytd",0),"Sinistres payés Ant.":r.get("recovered_paid_prior_ytd",0),
            "REC Ouverture":r.get("ceded_upr_open",0),"REC Clôture":r.get("ceded_upr_close",0),"Variation de REC":r.get("ceded_upr_variation",0),"Primes acquises cédées":r.get("ceded_earned_premium_ytd",0),
            "SAP Ouverture Per.":r.get("recoverable_case_open_current",0),"SAP Clôture Per.":r.get("recoverable_case_close_current",0),"SAP Ouverture Ant.":r.get("recoverable_case_open_prior",0),"SAP Clôture Ant.":r.get("recoverable_case_close_prior",0),
            "IBNR Ouverture Per.":r.get("recoverable_ibnr_open_current",0),"IBNR Clôture Per.":r.get("recoverable_ibnr_close_current",0),"IBNR Ouverture Ant.":r.get("recoverable_ibnr_open_prior",0),"IBNR Clôture Ant.":r.get("recoverable_ibnr_close_prior",0),
            "Taux cession primes":r.get("cession_rate",0),"Taux récupération sinistres":r.get("recovery_rate",0),"Taux commission réassurance":r.get("reass_commission_rate",0),
        }
        for line,v in vals.items(): rows.append({"period":r.get("period"),"branch":r.get("branch"),"line":line,"value":v})
    return pd.DataFrame(rows)
