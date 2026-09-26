from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Tuple

import gradio as gr
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from openpyxl import load_workbook

from prime_engine import BRANCHES, MONTHS, project_branch
from claims_engine import (
    SP_SETTING_COLS, blank_sp_settings, blank_portfolio_manual,
    build_portfolio_target, optimize_sp_matrix, calculate_claims_and_result, portfolio_metrics,
)

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = BASE_DIR / "hypotheses_primes_commissions_v1.xlsx"

THEME = gr.themes.Soft(primary_hue="emerald", neutral_hue="slate", radius_size="lg")
CSS = """
.gradio-container{max-width:1700px!important;margin:0 auto;background:#F5F7FA!important}
#hero{background:linear-gradient(135deg,#0B5D50,#17365D);border-radius:22px;padding:24px 28px;margin-bottom:14px;color:#fff}
#hero h1{font-size:27px;margin:0 0 6px;color:#fff} #hero p{margin:0;color:#DDEDEA}
.card{background:#fff!important;border:1px solid #E1E7EE!important;border-radius:18px!important;padding:8px!important;box-shadow:0 2px 12px rgba(24,50,70,.04)!important}
.section-title h3{color:#17365D!important;margin-bottom:4px!important}.muted{font-size:13px;color:#66788A}
.kpi{background:#fff;border:1px solid #E1E7EE;border-radius:14px;padding:11px 13px}.kpi b{font-size:18px;color:#17365D}
button.primary{font-weight:700!important}
.matrix table{font-size:12px!important}.matrix th{white-space:nowrap!important}.matrix td{white-space:nowrap!important}
.rate-settings table{font-size:12px!important}
.compact input{font-size:13px!important}
.prime-editor table{font-size:13px!important}.prime-editor td,.prime-editor th{padding:8px 10px!important}
.prime-editor{border:1px solid #D9E3EA!important;border-radius:16px!important;overflow:hidden!important}
.prime-result table{font-size:12px!important}
.sp-editor table{font-size:13px!important}.sp-editor{border:1px solid #D9E3EA!important;border-radius:16px!important;overflow:hidden!important}
.sp-kpi{background:#fff;border:1px solid #DCE6ED;border-radius:14px;padding:12px 14px}
#prime-workspace{background:#fff;border:1px solid #E1E7EE;border-radius:20px;padding:14px 16px;box-shadow:0 4px 18px rgba(24,50,70,.05)}
#prime-toolbar{background:#EEF7F4;border:1px solid #D5EBE4;border-radius:16px;padding:8px 12px}
footer{display:none!important}
"""

BRANCH_COLS = BRANCHES
MONTH_GRID_COLS = ["Mois"] + BRANCHES
RATE_SETTING_COLS = ["Branche", "Mode", "Départ (%)", "Atterrissage (%)", "Marge baisse (pts)", "Marge hausse (pts)"]
ANCHOR_COLS = [
    "Branche",
    "Départ Direct (facultatif)", "Atterrissage Direct",
    "Départ Réassurance (facultatif)", "Atterrissage Réassurance",
    "REC ouverture Direct CIMA 72%",
    "REC ouverture Réass Local CIMA",
    "REC ouverture Réass IFRS 100%",
]

COMMISSION_ANCHOR_COLS = [
    "Branche",
    "Commission Direct départ", "Commission Direct atterrissage",
    "Commission Réass départ", "Commission Réass atterrissage",
    "DAC Ouv Direct IFRS", "DAC Clo Direct IFRS",
    "REC Ouv prorata Direct IFRS", "REC Clo prorata Direct IFRS",
    "DAC Ouv Réass IFRS", "DAC Clo Réass IFRS",
    "REC Ouv 100% Réass IFRS", "REC Clo 100% Réass IFRS",
]


def blank_month_matrix(value=np.nan) -> pd.DataFrame:
    d = {"Mois": MONTHS}
    for b in BRANCHES:
        d[b] = [value] * 12
    return pd.DataFrame(d)


def blank_history() -> pd.DataFrame:
    return blank_month_matrix(np.nan)


def blank_anchors() -> pd.DataFrame:
    d = {c: [] for c in ANCHOR_COLS}
    for b in BRANCHES:
        d["Branche"].append(b)
        for c in ANCHOR_COLS[1:]:
            d[c].append(np.nan)
    return pd.DataFrame(d)


def blank_commission_anchors() -> pd.DataFrame:
    d = {c: [] for c in COMMISSION_ANCHOR_COLS}
    for b in BRANCHES:
        d["Branche"].append(b)
        for c in COMMISSION_ANCHOR_COLS[1:]:
            d[c].append(np.nan)
    return pd.DataFrame(d)


def default_rate_settings(kind: str) -> pd.DataFrame:
    rows = []
    default_mode = "Fixe" if kind in {"commission", "dac"} else "Linéaire"
    for b in BRANCHES:
        rows.append([b, default_mode, np.nan, np.nan, 2.0, 2.0])
    return pd.DataFrame(rows, columns=RATE_SETTING_COLS)


def _num(v, default=np.nan):
    try:
        if v is None or (isinstance(v, float) and np.isnan(v)) or str(v).strip() == "":
            return default
        x = float(str(v).replace(" ", "").replace(",", "."))
        return x if np.isfinite(x) else default
    except Exception:
        return default


def _matrix_col(df, branch: str) -> np.ndarray:
    d = pd.DataFrame(df).copy()
    if branch not in d.columns:
        return np.full(12, np.nan)
    vals = [_num(v) for v in d[branch].tolist()[:12]]
    if len(vals) < 12:
        vals += [np.nan] * (12 - len(vals))
    return np.asarray(vals, dtype=float)


def _anchor_row(df, branch: str) -> pd.Series:
    d = pd.DataFrame(df).copy()
    if "Branche" in d.columns:
        m = d[d["Branche"].astype(str).str.strip() == branch]
        if not m.empty:
            return m.iloc[0]
    return pd.Series(dtype=object)


def _setting_row(df, branch: str) -> pd.Series:
    d = pd.DataFrame(df).copy()
    if "Branche" in d.columns:
        m = d[d["Branche"].astype(str).str.strip() == branch]
        if not m.empty:
            return m.iloc[0]
    return pd.Series(dtype=object)


def _rate_config(settings, historical, manual, branch: str, implied_start=None, implied_end=None) -> Dict:
    r = _setting_row(settings, branch)
    mode = str(r.get("Mode", "Linéaire") or "Linéaire")
    start = _num(r.get("Départ (%)"))
    end = _num(r.get("Atterrissage (%)"))
    if implied_start is not None and not np.isfinite(start):
        start = float(implied_start)
    if implied_end is not None and not np.isfinite(end):
        end = float(implied_end)
    fixed = end
    return {
        "mode": mode,
        "fixed": fixed,
        "start": start,
        "end": end,
        "historical": _matrix_col(historical, branch),
        "manual": _matrix_col(manual, branch),
        "margin_down": max(0.0, _num(r.get("Marge baisse (pts)"), 0.0)),
        "margin_up": max(0.0, _num(r.get("Marge hausse (pts)"), 0.0)),
    }


def _month_matrix_from_results(results: Dict[str, pd.DataFrame], column: str) -> pd.DataFrame:
    out = {"Mois": MONTHS}
    for b in BRANCHES:
        t = results[b]
        out[b] = t[column].tolist() if column in t.columns else [np.nan] * 12
    return pd.DataFrame(out)


def _fmt_currency(v):
    if v is None or not np.isfinite(_num(v)):
        return "—"
    x = _num(v, 0.0)
    ax = abs(x)
    if ax >= 1e9:
        return f"{x/1e9:,.2f} Md".replace(",", " ")
    if ax >= 1e6:
        return f"{x/1e6:,.1f} M".replace(",", " ")
    return f"{x:,.0f}".replace(",", " ")


def _summary_html(results: Dict[str, pd.DataFrame], view: str) -> str:
    gross = sum(float(results[b]["Prime brute"].iloc[-1]) for b in BRANCHES)
    ceded = sum(float(results[b]["Prime réassurance"].iloc[-1]) for b in BRANCHES)
    net = gross - ceded
    earned_col = "Prime acquise nette IFRS" if view == "IFRS" else "Prime acquise nette Local"
    earned = sum(float(results[b][earned_col].iloc[-1]) for b in BRANCHES)
    rate = 100 * ceded / gross if abs(gross) > 1e-12 else 0.0
    return f"""
    <div style='display:grid;grid-template-columns:repeat(5,minmax(150px,1fr));gap:10px'>
      <div class='kpi'><span>Prime brute</span><br><b>{_fmt_currency(gross)}</b></div>
      <div class='kpi'><span>Prime réassurance</span><br><b>{_fmt_currency(ceded)}</b></div>
      <div class='kpi'><span>Prime nette</span><br><b>{_fmt_currency(net)}</b></div>
      <div class='kpi'><span>Taux de cession</span><br><b>{rate:.1f}%</b></div>
      <div class='kpi'><span>Prime acquise nette {view}</span><br><b>{_fmt_currency(earned)}</b></div>
    </div>"""


def _branch_kpi_html(results: Dict[str, pd.DataFrame], anchors, branch: str, view: str) -> str:
    b = branch if branch in BRANCHES else BRANCHES[0]
    t = results[b]
    ar = _anchor_row(anchors, b)
    gross_target = _num(ar.get("Atterrissage Direct"), np.nan)
    reass_target = _num(ar.get("Atterrissage Réassurance"), np.nan)
    earned_col = "Prime acquise nette IFRS" if view == "IFRS" else "Prime acquise nette Local"
    cession_dec = float(t["Taux cession (%)"].iloc[-1])
    gross_dec = float(t["Prime brute"].iloc[-1])
    reass_dec = float(t["Prime réassurance"].iloc[-1])
    earned_dec = float(t[earned_col].iloc[-1])
    target_g = _fmt_currency(gross_target) if np.isfinite(gross_target) else "—"
    target_r = _fmt_currency(reass_target) if np.isfinite(reass_target) else "—"
    return f"""
    <div style='display:grid;grid-template-columns:repeat(6,minmax(130px,1fr));gap:8px'>
      <div class='kpi'><span>Branche</span><br><b>{b}</b></div>
      <div class='kpi'><span>Cible Direct</span><br><b>{target_g}</b></div>
      <div class='kpi'><span>Projection Direct</span><br><b>{_fmt_currency(gross_dec)}</b></div>
      <div class='kpi'><span>Cible Réass</span><br><b>{target_r}</b></div>
      <div class='kpi'><span>Cession Déc.</span><br><b>{cession_dec:.2f}%</b></div>
      <div class='kpi'><span>Prime acquise nette {view}</span><br><b>{_fmt_currency(earned_dec)}</b></div>
    </div>"""


def _branch_editor_table(results: Dict[str, pd.DataFrame], branch: str, view: str) -> pd.DataFrame:
    b = branch if branch in BRANCHES else BRANCHES[0]
    t = results[b]
    reass_rate_col = "Taux variation REC Réass IFRS (%)" if view == "IFRS" else "Taux variation REC Réass Local (%)"
    return pd.DataFrame({
        "Mois": MONTHS,
        "Prime brute": t["Prime brute"].to_numpy(float),
        "Taux cession (%)": t["Taux cession (%)"].to_numpy(float),
        "Taux REC Direct (%)": t["Taux variation REC Direct (%)"].to_numpy(float),
        "Taux REC Réass (%)": t[reass_rate_col].to_numpy(float),
    })


def _branch_result_table(results: Dict[str, pd.DataFrame], branch: str, view: str) -> pd.DataFrame:
    b = branch if branch in BRANCHES else BRANCHES[0]
    t = results[b]
    if view == "IFRS":
        d_earned = "Prime acquise Direct IFRS"
        r_earned = "Prime acquise Réass IFRS"
        n_earned = "Prime acquise nette IFRS"
    else:
        d_earned = "Prime acquise Direct Local"
        r_earned = "Prime acquise Réass Local"
        n_earned = "Prime acquise nette Local"
    return pd.DataFrame({
        "Mois": MONTHS,
        "Prime Réassurance": t["Prime réassurance"].to_numpy(float),
        "Prime nette": t["Prime nette"].to_numpy(float),
        "Prime acquise Direct": t[d_earned].to_numpy(float),
        "Prime acquise Réass": t[r_earned].to_numpy(float),
        "Prime acquise nette": t[n_earned].to_numpy(float),
    })


def _ratio_pct(num, den):
    n = _num(num, np.nan)
    d = _num(den, np.nan)
    if not np.isfinite(n) or not np.isfinite(d) or abs(d) <= 1e-12:
        return np.nan
    return 100.0 * n / d


def _commission_summary_html(results: Dict[str, pd.DataFrame], view: str) -> str:
    dcomm = sum(float(results[b]["Commission Direct"].iloc[-1]) for b in BRANCHES)
    rcomm = sum(float(results[b]["Commission Réassurance"].iloc[-1]) for b in BRANCHES)
    if view == "IFRS":
        net_comm = sum(float(results[b]["Commission nette CPC IFRS"].iloc[-1]) for b in BRANCHES)
        net_earned = sum(float(results[b]["Prime acquise nette IFRS"].iloc[-1]) for b in BRANCHES)
        var_dac = sum(float(results[b]["Variation DAC Direct IFRS"].iloc[-1]) for b in BRANCHES)
    else:
        net_comm = sum(float(results[b]["Commission nette CPC Local"].iloc[-1]) for b in BRANCHES)
        net_earned = sum(float(results[b]["Prime acquise nette Local"].iloc[-1]) for b in BRANCHES)
        var_dac = 0.0
    cpc_rate = 100.0 * net_comm / net_earned if abs(net_earned) > 1e-12 else np.nan
    rate_txt = "—" if not np.isfinite(cpc_rate) else f"{cpc_rate:.2f}%"
    return f"""
    <div style='display:grid;grid-template-columns:repeat(5,minmax(150px,1fr));gap:10px'>
      <div class='kpi'><span>Commission Direct</span><br><b>{_fmt_currency(dcomm)}</b></div>
      <div class='kpi'><span>Commission Réassurance</span><br><b>{_fmt_currency(rcomm)}</b></div>
      <div class='kpi'><span>Variation DAC Direct</span><br><b>{_fmt_currency(var_dac) if view=='IFRS' else '—'}</b></div>
      <div class='kpi'><span>Commission nette CPC</span><br><b>{_fmt_currency(net_comm)}</b></div>
      <div class='kpi'><span>Taux commission CPC · {view}</span><br><b>{rate_txt}</b></div>
    </div>"""


def run_projection(
    hist_n3, hist_n2, hist_n1, anchors,
    gross_manual,
    cession_settings, cession_hist, cession_manual,
    rec_direct_settings, rec_direct_hist, rec_direct_manual,
    rec_reass_local_settings, rec_reass_local_hist, rec_reass_local_manual,
    rec_reass_ifrs_settings, rec_reass_ifrs_hist, rec_reass_ifrs_manual,
    view, selected_branch,
    commission_anchors=None,
    direct_commission_settings=None, direct_commission_manual=None,
    reass_commission_settings=None, reass_commission_manual=None,
    direct_dac_settings=None, direct_dac_manual=None,
    reass_dac_settings=None, reass_dac_manual=None,
):
    histories = [pd.DataFrame(hist_n3), pd.DataFrame(hist_n2), pd.DataFrame(hist_n1)]
    results: Dict[str, pd.DataFrame] = {}
    diags: List[str] = []
    empty_rates = blank_month_matrix()
    if commission_anchors is None:
        commission_anchors = blank_commission_anchors()
    if direct_commission_settings is None: direct_commission_settings = default_rate_settings("commission")
    if reass_commission_settings is None: reass_commission_settings = default_rate_settings("commission")
    if direct_dac_settings is None: direct_dac_settings = default_rate_settings("dac")
    if reass_dac_settings is None: reass_dac_settings = default_rate_settings("dac")
    if direct_commission_manual is None: direct_commission_manual = blank_month_matrix()
    if reass_commission_manual is None: reass_commission_manual = blank_month_matrix()
    if direct_dac_manual is None: direct_dac_manual = blank_month_matrix()
    if reass_dac_manual is None: reass_dac_manual = blank_month_matrix()

    for b in BRANCHES:
        h = []
        for hd in histories:
            a = _matrix_col(hd, b)
            if np.isfinite(a).sum() >= 2:
                h.append(a)
        ar = _anchor_row(anchors, b)
        car = _anchor_row(commission_anchors, b)
        gross_landing = _num(ar.get("Atterrissage Direct"), np.nan)
        reass_landing = _num(ar.get("Atterrissage Réassurance"), np.nan)
        if not np.isfinite(gross_landing):
            gross_landing = np.nan
            for hh in reversed(h):
                if np.isfinite(hh[-1]):
                    gross_landing = hh[-1]
                    break
            if not np.isfinite(gross_landing):
                gross_landing = 0.0
        gross_departure = _num(ar.get("Départ Direct (facultatif)"), np.nan)
        reass_departure = _num(ar.get("Départ Réassurance (facultatif)"), np.nan)
        if not np.isfinite(gross_departure):
            gross_departure = None
        if not np.isfinite(reass_departure):
            reass_departure = None

        anchors_map = {}
        manual_g = _matrix_col(gross_manual, b)
        for i, v in enumerate(manual_g):
            if np.isfinite(v):
                anchors_map[i] = float(v)

        implied = 100 * reass_landing / gross_landing if np.isfinite(reass_landing) and gross_landing else 0.0
        cconf = _rate_config(cession_settings, cession_hist, cession_manual, b, implied_end=implied)
        rdconf = _rate_config(rec_direct_settings, rec_direct_hist, rec_direct_manual, b)
        rlconf = _rate_config(rec_reass_local_settings, rec_reass_local_hist, rec_reass_local_manual, b)
        riconf = _rate_config(rec_reass_ifrs_settings, rec_reass_ifrs_hist, rec_reass_ifrs_manual, b)

        dcomm_start = _ratio_pct(car.get("Commission Direct départ"), gross_departure)
        dcomm_end = _ratio_pct(car.get("Commission Direct atterrissage"), gross_landing)
        # La Réassurance dépend de la commission Direct : le paramètre piloté est
        # le taux de récupération de commission Réassurance.
        rcomm_start = _ratio_pct(car.get("Commission Réass départ"), car.get("Commission Direct départ"))
        rcomm_end = _ratio_pct(car.get("Commission Réass atterrissage"), car.get("Commission Direct atterrissage"))
        # Taux effectif sur prime cédée uniquement pour la logique DAC / contrôle.
        rcomm_effective_start = _ratio_pct(car.get("Commission Réass départ"), reass_departure)
        rcomm_effective_end = _ratio_pct(car.get("Commission Réass atterrissage"), reass_landing)
        ddac_start = _ratio_pct(car.get("DAC Ouv Direct IFRS"), car.get("REC Ouv prorata Direct IFRS"))
        ddac_end = _ratio_pct(car.get("DAC Clo Direct IFRS"), car.get("REC Clo prorata Direct IFRS"))
        rdac_start = _ratio_pct(car.get("DAC Ouv Réass IFRS"), car.get("REC Ouv 100% Réass IFRS"))
        rdac_end = _ratio_pct(car.get("DAC Clo Réass IFRS"), car.get("REC Clo 100% Réass IFRS"))
        # Le DAC Réassurance reste fondé sur le taux de commission effectif sur prime cédée.
        if not np.isfinite(rdac_start): rdac_start = rcomm_effective_start
        if not np.isfinite(rdac_end): rdac_end = rcomm_effective_end

        dcconf = _rate_config(direct_commission_settings, empty_rates, direct_commission_manual, b,
                              implied_start=dcomm_start if np.isfinite(dcomm_start) else None,
                              implied_end=dcomm_end if np.isfinite(dcomm_end) else None)
        rcconf = _rate_config(reass_commission_settings, empty_rates, reass_commission_manual, b,
                              implied_start=rcomm_start if np.isfinite(rcomm_start) else None,
                              implied_end=rcomm_end if np.isfinite(rcomm_end) else None)
        ddconf = _rate_config(direct_dac_settings, empty_rates, direct_dac_manual, b,
                              implied_start=ddac_start if np.isfinite(ddac_start) else None,
                              implied_end=ddac_end if np.isfinite(ddac_end) else None)
        rdcconf = _rate_config(reass_dac_settings, empty_rates, reass_dac_manual, b,
                               implied_start=rdac_start if np.isfinite(rdac_start) else None,
                               implied_end=rdac_end if np.isfinite(rdac_end) else None)

        res = project_branch(
            histories_gross=h,
            gross_landing=float(gross_landing),
            reass_landing=None if not np.isfinite(reass_landing) else float(reass_landing),
            gross_departure=gross_departure,
            gross_manual_anchors=anchors_map,
            cession_config=cconf,
            rec_direct_config=rdconf,
            rec_reass_local_config=rlconf,
            rec_reass_ifrs_config=riconf,
            rec_open_direct_cima72=_num(ar.get("REC ouverture Direct CIMA 72%"), 0.0),
            rec_open_reass_cima72=_num(ar.get("REC ouverture Réass Local CIMA"), 0.0),
            rec_open_reass_ifrs100=_num(ar.get("REC ouverture Réass IFRS 100%"), 0.0),
            direct_commission_config=dcconf,
            reass_commission_config=rcconf,
            direct_dac_config=ddconf,
            reass_dac_config=rdcconf,
            dac_open_direct_ifrs=_num(car.get("DAC Ouv Direct IFRS"), np.nan),
            dac_open_reass_ifrs=_num(car.get("DAC Ouv Réass IFRS"), np.nan),
        )
        results[b] = res.table
        for x in res.diagnostics["Diagnostic"].tolist():
            if x != "Aucune incohérence détectée":
                diags.append(f"{b} — {x}")

    gross = _month_matrix_from_results(results, "Prime brute")
    cession = _month_matrix_from_results(results, "Taux cession (%)")
    ceded = _month_matrix_from_results(results, "Prime réassurance")
    net = _month_matrix_from_results(results, "Prime nette")

    if view == "IFRS":
        direct_var = _month_matrix_from_results(results, "Variation REC Direct prorata")
        direct_close = _month_matrix_from_results(results, "REC clôture Direct prorata")
        direct_earned = _month_matrix_from_results(results, "Prime acquise Direct IFRS")
        reass_rate = _month_matrix_from_results(results, "Taux variation REC Réass IFRS (%)")
        reass_var = _month_matrix_from_results(results, "Variation REC Réass IFRS 100%")
        reass_close = _month_matrix_from_results(results, "REC clôture Réass IFRS 100%")
        reass_earned = _month_matrix_from_results(results, "Prime acquise Réass IFRS")
        net_earned = _month_matrix_from_results(results, "Prime acquise nette IFRS")
        cpc_comm_rate = _month_matrix_from_results(results, "Taux commission CPC IFRS (%)")
        rec_label = "REC Réassurance IFRS 100%"
    else:
        direct_var = _month_matrix_from_results(results, "Variation REC Direct CIMA 72%")
        direct_close = _month_matrix_from_results(results, "REC clôture Direct CIMA 72%")
        direct_earned = _month_matrix_from_results(results, "Prime acquise Direct Local")
        reass_rate = _month_matrix_from_results(results, "Taux variation REC Réass Local (%)")
        reass_var = _month_matrix_from_results(results, "Variation REC Réass Local")
        reass_close = _month_matrix_from_results(results, "REC clôture Réass Local")
        reass_earned = _month_matrix_from_results(results, "Prime acquise Réass Local")
        net_earned = _month_matrix_from_results(results, "Prime acquise nette Local")
        cpc_comm_rate = _month_matrix_from_results(results, "Taux commission CPC Local (%)")
        rec_label = "REC Réassurance Local CIMA"

    rd_rate = _month_matrix_from_results(results, "Taux variation REC Direct (%)")

    landing_rows = []
    commission_landing_rows = []
    for bb in BRANCHES:
        ar = _anchor_row(anchors, bb)
        car = _anchor_row(commission_anchors, bb)
        gd = _num(ar.get("Atterrissage Direct"), np.nan)
        rr = _num(ar.get("Atterrissage Réassurance"), np.nan)
        implied = 100.0 * rr / gd if np.isfinite(gd) and abs(gd) > 1e-12 and np.isfinite(rr) else np.nan
        applied = float(results[bb]["Taux cession (%)"].iloc[-1])
        ceded_dec = float(results[bb]["Prime réassurance"].iloc[-1])
        gap = ceded_dec - rr if np.isfinite(rr) else np.nan
        landing_rows.append({
            "Branche": bb,
            "Atterrissage Direct": gd,
            "Atterrissage Réassurance": rr,
            "Taux cession implicite (%)": implied,
            "Taux Décembre appliqué (%)": applied,
            "Écart Réassurance": gap,
        })
        commission_landing_rows.append({
            "Branche": bb,
            "Taux Direct départ (%)": _ratio_pct(car.get("Commission Direct départ"), ar.get("Départ Direct (facultatif)")),
            "Taux Direct atterrissage (%)": _ratio_pct(car.get("Commission Direct atterrissage"), gd),
            "Taux récupération Réass départ (%)": _ratio_pct(car.get("Commission Réass départ"), car.get("Commission Direct départ")),
            "Taux récupération Réass atterrissage (%)": _ratio_pct(car.get("Commission Réass atterrissage"), car.get("Commission Direct atterrissage")),
            "Taux commission Réass effectif atterrissage (%)": _ratio_pct(car.get("Commission Réass atterrissage"), rr),
            "Taux DAC Direct atterrissage (%)": _ratio_pct(car.get("DAC Clo Direct IFRS"), car.get("REC Clo prorata Direct IFRS")),
            "Taux DAC Réass atterrissage (%)": _ratio_pct(car.get("DAC Clo Réass IFRS"), car.get("REC Clo 100% Réass IFRS")),
            f"Taux CPC Décembre {view} (%)": float(results[bb]["Taux commission CPC IFRS (%)" if view=="IFRS" else "Taux commission CPC Local (%)"].iloc[-1]),
        })
    landing_summary = pd.DataFrame(landing_rows)
    commission_landing_summary = pd.DataFrame(commission_landing_rows)

    b = selected_branch if selected_branch in BRANCHES else BRANCHES[0]
    fig = go.Figure()
    hist_names = ["N-3", "N-2", "N-1"]
    for name, hd in zip(hist_names, histories):
        vals = _matrix_col(hd, b)
        if np.isfinite(vals).sum() >= 2:
            fig.add_trace(go.Scatter(x=MONTHS, y=vals, mode="lines+markers", name=name, line=dict(width=1.6)))
    t = results[b]
    fig.add_trace(go.Scatter(x=MONTHS, y=t["Prime brute"], mode="lines+markers", name="N · Prime brute", line=dict(width=4)))
    fig.add_trace(go.Scatter(x=MONTHS, y=t["Prime réassurance"], mode="lines+markers", name="N · Réassurance", line=dict(width=2.5)))
    fig.add_trace(go.Scatter(x=MONTHS, y=t["Prime nette"], mode="lines+markers", name="N · Nette", line=dict(width=2.5)))
    fig.update_layout(
        title=f"{b} · historique et projection des primes",
        height=430, margin=dict(l=20,r=20,t=60,b=30),
        legend=dict(orientation="h", y=-0.18), hovermode="x unified",
        yaxis_title="FCFA cumulés", xaxis_title=None, paper_bgcolor="white", plot_bgcolor="white",
    )

    commission_fig = go.Figure()
    commission_fig.add_trace(go.Scatter(x=MONTHS, y=t["Taux commission Direct (%)"], mode="lines+markers", name="Commission Direct", line=dict(width=3)))
    commission_fig.add_trace(go.Scatter(x=MONTHS, y=t["Taux récupération commission Réassurance (%)"], mode="lines+markers", name="Récupération commission Réass", line=dict(width=3)))
    commission_fig.add_trace(go.Scatter(x=MONTHS, y=t["Taux commission CPC IFRS (%)" if view=="IFRS" else "Taux commission CPC Local (%)"], mode="lines+markers", name=f"Taux CPC net · {view}", line=dict(width=4)))
    if view == "IFRS":
        commission_fig.add_trace(go.Scatter(x=MONTHS, y=t["Taux DAC Direct IFRS (%)"], mode="lines+markers", name="DAC Direct", line=dict(width=2)))
        commission_fig.add_trace(go.Scatter(x=MONTHS, y=t["Taux DAC Réassurance IFRS (%)"], mode="lines+markers", name="DAC Réass", line=dict(width=2)))
    commission_fig.update_layout(
        title=f"{b} · commission Direct, récupération Réassurance et taux CPC",
        height=420, margin=dict(l=20,r=20,t=60,b=30),
        legend=dict(orientation="h", y=-0.2), hovermode="x unified",
        yaxis_title="%", xaxis_title=None, paper_bgcolor="white", plot_bgcolor="white",
    )

    dcomm_rate = _month_matrix_from_results(results, "Taux commission Direct (%)")
    dcomm = _month_matrix_from_results(results, "Commission Direct")
    rcomm_rate = _month_matrix_from_results(results, "Taux récupération commission Réassurance (%)")
    rcomm = _month_matrix_from_results(results, "Commission Réassurance")
    ddac_rate = _month_matrix_from_results(results, "Taux DAC Direct IFRS (%)")
    ddac_open = _month_matrix_from_results(results, "DAC ouverture Direct IFRS")
    ddac_close = _month_matrix_from_results(results, "DAC clôture Direct IFRS")
    ddac_var = _month_matrix_from_results(results, "Variation DAC Direct IFRS")
    rdac_rate = _month_matrix_from_results(results, "Taux DAC Réassurance IFRS (%)")
    rdac_open = _month_matrix_from_results(results, "DAC ouverture Réassurance IFRS")
    rdac_close = _month_matrix_from_results(results, "DAC clôture Réassurance IFRS")
    rdac_var = _month_matrix_from_results(results, "Variation DAC Réassurance IFRS")

    diag_df = pd.DataFrame({"Diagnostic": diags[:250] if diags else ["Aucune incohérence détectée"]})
    return (
        _summary_html(results, view), landing_summary, fig,
        gross, cession, ceded, net,
        rd_rate, direct_var, direct_close, direct_earned,
        reass_rate, reass_var, reass_close, reass_earned, net_earned,
        _commission_summary_html(results, view), commission_landing_summary, commission_fig,
        dcomm_rate, dcomm, rcomm_rate, rcomm, cpc_comm_rate,
        ddac_rate, ddac_open, ddac_close, ddac_var,
        rdac_rate, rdac_open, rdac_close, rdac_var,
        diag_df,
        f"Vue {view} · Direct : {'REC prorata issue de la REC CIMA 72% / 72%' if view=='IFRS' else 'REC CIMA 72%'} · Réassurance : {rec_label}",
        _branch_kpi_html(results, anchors, b, view),
        _branch_editor_table(results, b, view),
        _branch_editor_table(results, b, view),
        _branch_result_table(results, b, view),
    )



def _ensure_month_grid(df) -> pd.DataFrame:
    d = pd.DataFrame(df).copy()
    if "Mois" not in d.columns:
        d.insert(0, "Mois", MONTHS[:len(d)])
    if len(d) < 12:
        for _ in range(12-len(d)):
            d.loc[len(d)] = [MONTHS[len(d)]] + [np.nan]*(len(d.columns)-1)
    return d.iloc[:12].reset_index(drop=True)


def _numeric_branch_frame(df) -> pd.DataFrame:
    d = _ensure_month_grid(df)
    out = pd.DataFrame(index=range(12))
    for b in BRANCHES:
        out[b] = [_num(v, 0.0) for v in (d[b].tolist() if b in d.columns else [0.0]*12)]
    return out


def _sp_matrix_with_months(values: pd.DataFrame) -> pd.DataFrame:
    d = pd.DataFrame(values).copy().reset_index(drop=True)
    d.insert(0, "Mois", MONTHS)
    return d


def _sp_summary_html(portfolio: pd.DataFrame, branch_table: pd.DataFrame, month: str, branch: str, view: str) -> str:
    idx = MONTHS.index(month) if month in MONTHS else 11
    p = portfolio.iloc[idx]
    b = branch_table.iloc[idx]
    prior = _num(b.get("Charge antérieurs"), 0.0)
    prior_label = "Boni antérieurs" if prior < 0 else "Mali antérieurs"
    prior_value = abs(prior)
    return f"""
    <div style='display:grid;grid-template-columns:repeat(7,minmax(130px,1fr));gap:9px'>
      <div class='sp-kpi'><span>Mois</span><br><b>{month}</b></div>
      <div class='sp-kpi'><span>S/P exercice portefeuille</span><br><b>{_num(p.get('S/P exercice portefeuille (%)'),0):.2f}%</b></div>
      <div class='sp-kpi'><span>S/P global portefeuille</span><br><b>{_num(p.get('S/P global portefeuille (%)'),0):.2f}%</b></div>
      <div class='sp-kpi'><span>Charge globale portefeuille</span><br><b>{_fmt_currency(p.get('Charge globale'))}</b></div>
      <div class='sp-kpi'><span>Résultat technique avant FG</span><br><b>{_fmt_currency(p.get('Résultat technique avant FG'))}</b></div>
      <div class='sp-kpi'><span>{branch} · {prior_label}</span><br><b>{_fmt_currency(prior_value)}</b></div>
      <div class='sp-kpi'><span>Marge technique · {view}</span><br><b>{_num(p.get('Marge technique avant FG (%)'),0):.2f}%</b></div>
    </div>"""


def _sp_branch_table(sp_ex, sp_global, charge_ex, charge_prior, charge_global, result, branch: str) -> pd.DataFrame:
    b = branch if branch in BRANCHES else BRANCHES[0]
    return pd.DataFrame({
        "Mois": MONTHS,
        "S/P exercice (%)": pd.DataFrame(sp_ex)[b].to_numpy(float),
        "S/P global (%)": pd.DataFrame(sp_global)[b].to_numpy(float),
        "Charge exercice": pd.DataFrame(charge_ex)[b].to_numpy(float),
        "Charge antérieurs": pd.DataFrame(charge_prior)[b].to_numpy(float),
        "Charge globale": pd.DataFrame(charge_global)[b].to_numpy(float),
        "Résultat technique avant FG": pd.DataFrame(result)[b].to_numpy(float),
    })


def _sp_editor_table(sp_ex, sp_global, branch: str) -> pd.DataFrame:
    b = branch if branch in BRANCHES else BRANCHES[0]
    return pd.DataFrame({
        "Mois": MONTHS,
        "S/P exercice (%)": pd.DataFrame(sp_ex)[b].to_numpy(float),
        "S/P global (%)": pd.DataFrame(sp_global)[b].to_numpy(float),
    })


def run_sp_projection(
    earned_grid, direct_commission_grid, reass_commission_grid, direct_dac_var_grid, view, selected_branch, sp_month,
    sp_ex_settings, sp_global_settings, sp_ex_manual, sp_global_manual, locked_branches,
    portfolio_mode, portfolio_ex_start, portfolio_ex_end, portfolio_global_start, portfolio_global_end, portfolio_manual,
):
    earned = _numeric_branch_frame(earned_grid)
    dcomm = _numeric_branch_frame(direct_commission_grid)
    rcomm = _numeric_branch_frame(reass_commission_grid)
    ddac = _numeric_branch_frame(direct_dac_var_grid)
    commission_net = dcomm-rcomm if view != "IFRS" else dcomm+ddac-rcomm

    pex_target = build_portfolio_target(portfolio_mode, portfolio_ex_start, portfolio_ex_end, portfolio_manual, "S/P exercice cible (%)")
    pgl_target = build_portfolio_target(portfolio_mode, portfolio_global_start, portfolio_global_end, portfolio_manual, "S/P global cible (%)")

    sp_ex, ex_lo, ex_hi, ex_ach, d1 = optimize_sp_matrix(
        earned, sp_ex_settings, sp_ex_manual, locked_branches or [], pex_target, 0.0, 0.0
    )
    sp_gl, gl_lo, gl_hi, gl_ach, d2 = optimize_sp_matrix(
        earned, sp_global_settings, sp_global_manual, locked_branches or [], pgl_target, 0.0, 0.0
    )
    charge_ex, charge_prior, charge_global, result = calculate_claims_and_result(earned, commission_net, sp_ex, sp_gl)
    portfolio = portfolio_metrics(earned, charge_ex, charge_global, commission_net, result)

    b = selected_branch if selected_branch in BRANCHES else BRANCHES[0]
    branch_table = _sp_branch_table(sp_ex,sp_gl,charge_ex,charge_prior,charge_global,result,b)
    editor = _sp_editor_table(sp_ex,sp_gl,b)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=MONTHS,y=sp_ex[b],mode="lines+markers",name="S/P exercice",line=dict(width=3)))
    fig.add_trace(go.Scatter(x=MONTHS,y=sp_gl[b],mode="lines+markers",name="S/P global",line=dict(width=3)))
    fig.add_trace(go.Scatter(x=MONTHS,y=ex_lo[b],mode="lines",name="Borne basse exercice",line=dict(width=1,dash="dot"),opacity=.45))
    fig.add_trace(go.Scatter(x=MONTHS,y=ex_hi[b],mode="lines",name="Borne haute exercice",line=dict(width=1,dash="dot"),opacity=.45,fill="tonexty"))
    if np.isfinite(pex_target).any():
        fig.add_trace(go.Scatter(x=MONTHS,y=pex_target,mode="lines",name="Cible portefeuille exercice",line=dict(width=2,dash="dash")))
    if np.isfinite(pgl_target).any():
        fig.add_trace(go.Scatter(x=MONTHS,y=pgl_target,mode="lines",name="Cible portefeuille global",line=dict(width=2,dash="dash")))
    fig.add_trace(go.Bar(x=MONTHS,y=result[b],name="Résultat technique",yaxis="y2",opacity=.22))
    fig.update_layout(
        title=f"{b} · S/P, bande autorisée et résultat technique",height=440,
        margin=dict(l=20,r=20,t=55,b=30),hovermode="x unified",
        yaxis=dict(title="S/P (%)"),
        yaxis2=dict(title="Résultat technique",overlaying="y",side="right",showgrid=False),
        legend=dict(orientation="h",y=1.12),
    )
    diag = pd.DataFrame({"Diagnostic": (d1+d2)[:200] if (d1+d2) else ["Cibles et plages cohérentes"]})
    return (
        _sp_summary_html(portfolio,branch_table,sp_month,b,view), fig, branch_table,
        _sp_matrix_with_months(sp_ex), _sp_matrix_with_months(sp_gl),
        _sp_matrix_with_months(charge_ex), _sp_matrix_with_months(charge_prior),
        _sp_matrix_with_months(charge_global), _sp_matrix_with_months(result), portfolio, diag,
        editor, editor.copy(),
    )


def apply_sp_branch_editor(editor, reference, branch, ex_manual, global_manual):
    ed = pd.DataFrame(editor).copy(); ref = pd.DataFrame(reference).copy()
    em = pd.DataFrame(ex_manual).copy(); gm = pd.DataFrame(global_manual).copy()
    if branch not in BRANCHES or len(ed)<12 or len(ref)<12:
        return em,gm
    def changed(a,b):
        aa,bb=_num(a,np.nan),_num(b,np.nan)
        if np.isfinite(aa)!=np.isfinite(bb): return True
        if not np.isfinite(aa): return False
        return abs(aa-bb)>1e-8
    for i in range(12):
        for col,target in [("S/P exercice (%)",em),("S/P global (%)",gm)]:
            if col in ed.columns and col in ref.columns and changed(ed.iloc[i][col],ref.iloc[i][col]):
                v=_num(ed.iloc[i][col],np.nan)
                target.loc[i,branch]=v if np.isfinite(v) else np.nan
    return em,gm


def reset_sp_branch(branch, ex_manual, global_manual):
    em=pd.DataFrame(ex_manual).copy(); gm=pd.DataFrame(global_manual).copy()
    if branch in BRANCHES:
        em.loc[:,branch]=np.nan; gm.loc[:,branch]=np.nan
    return em,gm

def apply_point_override(matrix, branch, month, value):
    d = pd.DataFrame(matrix).copy()
    if d.empty or branch not in d.columns or month not in MONTHS:
        return d
    idx = MONTHS.index(month)
    d.loc[idx, branch] = np.nan if not np.isfinite(_num(value)) else float(_num(value))
    return d


def clear_point_override(matrix, branch, month):
    return apply_point_override(matrix, branch, month, np.nan)


def apply_branch_table(editor, reference, branch, view, gross_m, cession_m, rec_direct_m, rec_local_m, rec_ifrs_m):
    """Applique seulement les cellules réellement modifiées dans le tableau compact.

    Une cellule vidée supprime l'override correspondant. Les cellules inchangées
    conservent l'état précédent, ce qui permet d'afficher les valeurs calculées
    sans transformer tout le tableau en contraintes manuelles.
    """
    ed = pd.DataFrame(editor).copy()
    ref = pd.DataFrame(reference).copy()
    if branch not in BRANCHES or len(ed) < 12 or len(ref) < 12:
        return gross_m, cession_m, rec_direct_m, rec_local_m, rec_ifrs_m

    mappings = [
        ("Prime brute", gross_m),
        ("Taux cession (%)", cession_m),
        ("Taux REC Direct (%)", rec_direct_m),
    ]
    out = [pd.DataFrame(x).copy() for _, x in mappings]
    rl = pd.DataFrame(rec_local_m).copy()
    ri = pd.DataFrame(rec_ifrs_m).copy()

    def changed(a, b):
        aa, bb = _num(a, np.nan), _num(b, np.nan)
        if not np.isfinite(aa) and not np.isfinite(bb): return False
        if np.isfinite(aa) != np.isfinite(bb): return True
        return abs(aa-bb) > max(1e-7, abs(bb)*1e-10)

    for i in range(12):
        for j, (col, _) in enumerate(mappings):
            if col not in ed.columns or col not in ref.columns: continue
            if changed(ed.iloc[i][col], ref.iloc[i][col]):
                v = _num(ed.iloc[i][col], np.nan)
                out[j].loc[i, branch] = v if np.isfinite(v) else np.nan
        col = "Taux REC Réass (%)"
        if col in ed.columns and col in ref.columns and changed(ed.iloc[i][col], ref.iloc[i][col]):
            v = _num(ed.iloc[i][col], np.nan)
            target = ri if view == "IFRS" else rl
            target.loc[i, branch] = v if np.isfinite(v) else np.nan
    return out[0], out[1], out[2], rl, ri


def reset_branch_overrides(branch, gross_m, cession_m, rec_direct_m, rec_local_m, rec_ifrs_m):
    mats = [pd.DataFrame(x).copy() for x in [gross_m, cession_m, rec_direct_m, rec_local_m, rec_ifrs_m]]
    if branch in BRANCHES:
        for m in mats:
            if branch in m.columns:
                m.loc[:, branch] = np.nan
    return tuple(mats)


def _sheet_matrix(ws, marker: str, percent: bool = False) -> pd.DataFrame:
    # Find exact marker in column A, header is next row, 12 months below.
    row = None
    for r in range(1, ws.max_row + 1):
        if str(ws.cell(r, 1).value or "").strip() == marker:
            row = r
            break
    if row is None:
        return blank_month_matrix()
    hdr = row + 1
    out = {"Mois": MONTHS}
    for j, b in enumerate(BRANCHES, start=2):
        vals = []
        for i in range(12):
            v = ws.cell(hdr + 1 + i, j).value
            if percent and v is not None:
                try:
                    v = float(v) * 100.0
                except Exception:
                    txt = str(v).strip()
                    if txt.endswith("%"):
                        try: v = float(txt[:-1].replace(",","."))
                        except Exception: pass
            vals.append(v)
        out[b] = vals
    return pd.DataFrame(out)


def _find_block_value(ws, block_title: str, line_label: str, branch: str, occurrence: int = 1):
    title_row = None
    for r in range(1, ws.max_row + 1):
        if str(ws.cell(r,1).value or "").strip() == block_title:
            title_row = r
            break
    if title_row is None:
        return np.nan
    # block ends at next all-caps title in col A or 120 rows later.
    header_row = title_row + 1
    headers = [str(ws.cell(header_row, c).value or "").strip() for c in range(1, 12)]
    try:
        branch_col = headers.index(branch) + 1
    except ValueError:
        return np.nan
    count = 0
    for r in range(header_row + 1, min(ws.max_row, title_row + 120) + 1):
        a = str(ws.cell(r,1).value or "").strip()
        b = str(ws.cell(r,2).value or "").strip()
        if r > header_row + 1 and a and a.upper() == a and "—" in a:
            break
        if b == line_label:
            count += 1
            if count == occurrence:
                return ws.cell(r, branch_col).value
    return np.nan


def load_template(file_obj):
    if file_obj is None:
        raise gr.Error("Sélectionnez un fichier Excel.")
    path = file_obj if isinstance(file_obj, str) else getattr(file_obj, "name", file_obj)
    wb = load_workbook(path, data_only=False, read_only=False)

    hist = wb["Historique primes"]
    h3 = _sheet_matrix(hist, "PRIMES ÉMISES CUMULÉES — N-3")
    h2 = _sheet_matrix(hist, "PRIMES ÉMISES CUMULÉES — N-2")
    h1 = _sheet_matrix(hist, "PRIMES ÉMISES CUMULÉES — N-1")

    taux = wb["Taux historiques"]
    c_hist = _sheet_matrix(taux, "TAUX DE CESSION — N-1", percent=True)
    rd_hist = _sheet_matrix(taux, "TAUX VARIATION REC DIRECT CIMA 72% — N-1", percent=True)
    rl_hist = _sheet_matrix(taux, "TAUX VARIATION REC RÉASS LOCAL — N-1", percent=True)
    ri_hist = _sheet_matrix(taux, "TAUX VARIATION REC RÉASS IFRS 100% — N-1", percent=True)

    anc_ws = wb["Ancrages globaux"]
    rows = []
    for b in BRANCHES:
        # First REC occurrence is CIMA in Direct Local / Reass Local.
        d_rec = _find_block_value(anc_ws, "DIRECT LOCAL — DÉPART (FACULTATIF)", "REC Ouverture", b, 1)
        if not np.isfinite(_num(d_rec)): d_rec = _find_block_value(anc_ws, "DIRECT LOCAL — ATTERRISSAGE", "REC Ouverture", b, 1)
        r_rec = _find_block_value(anc_ws, "REASS LOCAL — DÉPART (FACULTATIF)", "REC Ouverture", b, 1)
        if not np.isfinite(_num(r_rec)): r_rec = _find_block_value(anc_ws, "REASS LOCAL — ATTERRISSAGE", "REC Ouverture", b, 1)
        ri_rec = _find_block_value(anc_ws, "REASS IFRS — DÉPART (FACULTATIF)", "REC Ouverture 100%", b, 1)
        if not np.isfinite(_num(ri_rec)): ri_rec = _find_block_value(anc_ws, "REASS IFRS — ATTERRISSAGE", "REC Ouverture 100%", b, 1)
        rows.append({
            "Branche": b,
            "Départ Direct (facultatif)": _find_block_value(anc_ws, "DIRECT LOCAL — DÉPART (FACULTATIF)", "Primes Emises", b, 1),
            "Atterrissage Direct": _find_block_value(anc_ws, "DIRECT LOCAL — ATTERRISSAGE", "Primes Emises", b, 1),
            "Départ Réassurance (facultatif)": _find_block_value(anc_ws, "REASS LOCAL — DÉPART (FACULTATIF)", "Primes Emises", b, 1),
            "Atterrissage Réassurance": _find_block_value(anc_ws, "REASS LOCAL — ATTERRISSAGE", "Primes Emises", b, 1),
            "REC ouverture Direct CIMA 72%": d_rec,
            "REC ouverture Réass Local CIMA": r_rec,
            "REC ouverture Réass IFRS 100%": ri_rec,
        })
    anchors = pd.DataFrame(rows, columns=ANCHOR_COLS)

    commission_rows = []
    for b in BRANCHES:
        commission_rows.append({
            "Branche": b,
            "Commission Direct départ": _find_block_value(anc_ws, "DIRECT LOCAL — DÉPART (FACULTATIF)", "Commisions", b, 1),
            "Commission Direct atterrissage": _find_block_value(anc_ws, "DIRECT LOCAL — ATTERRISSAGE", "Commisions", b, 1),
            "Commission Réass départ": _find_block_value(anc_ws, "REASS LOCAL — DÉPART (FACULTATIF)", "Commisions", b, 1),
            "Commission Réass atterrissage": _find_block_value(anc_ws, "REASS LOCAL — ATTERRISSAGE", "Commisions", b, 1),
            "DAC Ouv Direct IFRS": _find_block_value(anc_ws, "DIRECT IFRS — DÉPART (FACULTATIF)", "DAC Ouv", b, 1),
            "DAC Clo Direct IFRS": _find_block_value(anc_ws, "DIRECT IFRS — ATTERRISSAGE", "DAC Clo", b, 1),
            "REC Ouv prorata Direct IFRS": _find_block_value(anc_ws, "DIRECT IFRS — DÉPART (FACULTATIF)", "REC Ouverture", b, 2),
            "REC Clo prorata Direct IFRS": _find_block_value(anc_ws, "DIRECT IFRS — ATTERRISSAGE", "REC Clôture", b, 2),
            "DAC Ouv Réass IFRS": _find_block_value(anc_ws, "REASS IFRS — DÉPART (FACULTATIF)", "DAC Ouv", b, 1),
            "DAC Clo Réass IFRS": _find_block_value(anc_ws, "REASS IFRS — ATTERRISSAGE", "DAC Clo", b, 1),
            "REC Ouv 100% Réass IFRS": _find_block_value(anc_ws, "REASS IFRS — DÉPART (FACULTATIF)", "REC Ouverture 100%", b, 1),
            "REC Clo 100% Réass IFRS": _find_block_value(anc_ws, "REASS IFRS — ATTERRISSAGE", "REC Clôture 100%", b, 1),
        })
    commission_anchors = pd.DataFrame(commission_rows, columns=COMMISSION_ANCHOR_COLS)
    return h3, h2, h1, anchors, commission_anchors, c_hist, rd_hist, rl_hist, ri_hist, "Fichier chargé avec succès."


def build_app():
    with gr.Blocks(title="Projection technique · Primes, Commissions & S/P") as demo:
        gr.HTML("""
        <div id='hero'>
          <h1>Projection technique · Primes, Commissions & S/P</h1>
          <p>Primes · Commissions · S/P exercice & global · Charges · Résultat technique · Local / IFRS</p>
        </div>
        """)

        with gr.Row():
            with gr.Column(scale=2, elem_classes="card"):
                gr.Markdown("### Données du modèle", elem_classes="section-title")
                gr.Markdown("Historique de 1 à 3 ans, ancrages globaux et taux historiques.", elem_classes="muted")
                download = gr.DownloadButton("Télécharger le fichier d’hypothèses", value=str(TEMPLATE_PATH), variant="primary")
            with gr.Column(scale=3, elem_classes="card"):
                upload = gr.File(label="Importer le fichier d’hypothèses complété", file_types=[".xlsx"], type="filepath")
                with gr.Row():
                    load_btn = gr.Button("Charger les données", variant="primary")
                    load_status = gr.Textbox(label="État", interactive=False)

        with gr.Accordion("Historique et ancrages", open=False):
            with gr.Tabs():
                with gr.Tab("N-3"):
                    hist_n3 = gr.Dataframe(value=blank_history(), headers=MONTH_GRID_COLS, interactive=True, elem_classes="matrix", label="Primes émises cumulées N-3")
                with gr.Tab("N-2"):
                    hist_n2 = gr.Dataframe(value=blank_history(), headers=MONTH_GRID_COLS, interactive=True, elem_classes="matrix", label="Primes émises cumulées N-2")
                with gr.Tab("N-1"):
                    hist_n1 = gr.Dataframe(value=blank_history(), headers=MONTH_GRID_COLS, interactive=True, elem_classes="matrix", label="Primes émises cumulées N-1")
            anchors = gr.Dataframe(value=blank_anchors(), headers=ANCHOR_COLS, interactive=True, elem_classes="matrix", label="Ancrages utiles au module Primes")
            commission_anchors = gr.State(blank_commission_anchors())

        with gr.Row(elem_id="prime-toolbar"):
            selected_branch = gr.Dropdown(BRANCHES, value=BRANCHES[0], label="Branche", scale=2)
            view = gr.Radio(["Local", "IFRS"], value="Local", label="Référentiel", scale=1)
            recalc = gr.Button("Recalculer", variant="primary", scale=1)

        summary = gr.HTML()

        with gr.Tabs():
            with gr.Tab("Primes"):
                with gr.Column(elem_id="prime-workspace"):
                    branch_kpis = gr.HTML()
                    chart = gr.Plot(label="Historique & projection")
                    gr.Markdown("### Ajustement mensuel de la branche", elem_classes="section-title")
                    gr.Markdown("Modifiez directement une ou plusieurs cellules. Une cellule effacée revient au calcul automatique.", elem_classes="muted")
                    branch_editor = gr.Dataframe(
                        value=pd.DataFrame({"Mois":MONTHS,"Prime brute":[np.nan]*12,"Taux cession (%)":[np.nan]*12,"Taux REC Direct (%)":[np.nan]*12,"Taux REC Réass (%)":[np.nan]*12}),
                        headers=["Mois","Prime brute","Taux cession (%)","Taux REC Direct (%)","Taux REC Réass (%)"],
                        interactive=True, elem_classes="prime-editor", label="Variables pilotables",
                        row_count=(12,"fixed"), column_count=(5,"fixed"),
                    )
                    branch_reference = gr.State(pd.DataFrame())
                    with gr.Row():
                        apply_branch_edits = gr.Button("Appliquer les modifications", variant="primary")
                        reset_branch_edits = gr.Button("Réinitialiser la branche")
                    branch_result = gr.Dataframe(
                        headers=["Mois","Prime Réassurance","Prime nette","Prime acquise Direct","Prime acquise Réass","Prime acquise nette"],
                        interactive=False, elem_classes="prime-result", label="Résultats calculés",
                    )
                    reference_note = gr.Markdown()

                with gr.Accordion("Paramètres de projection", open=False):
                    with gr.Tabs():
                        with gr.Tab("Cession"):
                            gr.Markdown("Mode **Fixe**, **Linéaire** ou **Manuel**. La trajectoire linéaire peut être encadrée par une marge basse/haute.", elem_classes="muted")
                            cession_landing = gr.Dataframe(interactive=False, elem_classes="matrix", label="Atterrissages et taux implicite")
                            cession_settings = gr.Dataframe(value=default_rate_settings("cession"), headers=RATE_SETTING_COLS, interactive=True, elem_classes="rate-settings", label="Règles par branche")
                            cession_hist = gr.Dataframe(value=blank_month_matrix(), headers=MONTH_GRID_COLS, interactive=True, elem_classes="matrix", label="Taux de cession N-1 (%)")
                            cession_manual = gr.Dataframe(value=blank_month_matrix(), headers=MONTH_GRID_COLS, interactive=True, elem_classes="matrix", label="Overrides mensuels N (%)")

                        with gr.Tab("REC Direct"):
                            gr.Markdown("Variation REC = Prime brute × taux. REC clôture = REC ouverture fixe + variation.", elem_classes="muted")
                            rec_direct_settings = gr.Dataframe(value=default_rate_settings("rec"), headers=RATE_SETTING_COLS, interactive=True, elem_classes="rate-settings", label="Règles REC Direct")
                            rec_direct_hist = gr.Dataframe(value=blank_month_matrix(), headers=MONTH_GRID_COLS, interactive=True, elem_classes="matrix", label="Taux N-1 (%)")
                            rec_direct_manual = gr.Dataframe(value=blank_month_matrix(), headers=MONTH_GRID_COLS, interactive=True, elem_classes="matrix", label="Overrides N (%)")

                        with gr.Tab("REC Réassurance"):
                            gr.Markdown("La REC Réassurance est appliquée à la prime cédée. Le taux IFRS 100% reste distinct du Local.", elem_classes="muted")
                            with gr.Tabs():
                                with gr.Tab("Local"):
                                    rec_reass_local_settings = gr.Dataframe(value=default_rate_settings("rec"), headers=RATE_SETTING_COLS, interactive=True, elem_classes="rate-settings", label="Règles REC Réass Local")
                                    rec_reass_local_hist = gr.Dataframe(value=blank_month_matrix(), headers=MONTH_GRID_COLS, interactive=True, elem_classes="matrix", label="Taux N-1 Local (%)")
                                    rec_reass_local_manual = gr.Dataframe(value=blank_month_matrix(), headers=MONTH_GRID_COLS, interactive=True, elem_classes="matrix", label="Overrides N Local (%)")
                                with gr.Tab("IFRS 100%"):
                                    rec_reass_ifrs_settings = gr.Dataframe(value=default_rate_settings("rec"), headers=RATE_SETTING_COLS, interactive=True, elem_classes="rate-settings", label="Règles REC Réass IFRS")
                                    rec_reass_ifrs_hist = gr.Dataframe(value=blank_month_matrix(), headers=MONTH_GRID_COLS, interactive=True, elem_classes="matrix", label="Taux N-1 IFRS (%)")
                                    rec_reass_ifrs_manual = gr.Dataframe(value=blank_month_matrix(), headers=MONTH_GRID_COLS, interactive=True, elem_classes="matrix", label="Overrides N IFRS (%)")

                with gr.Accordion("Vue portefeuille · 12 mois × 8 branches", open=False):
                    with gr.Row():
                        gross_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="Prime brute Direct", elem_classes="matrix")
                        ceded_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="Prime Réassurance", elem_classes="matrix")
                    with gr.Row():
                        cession_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="Taux de cession (%)", elem_classes="matrix")
                        net_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="Prime nette", elem_classes="matrix")
                    net_earned_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="Prime acquise nette", elem_classes="matrix")
                    with gr.Accordion("Détail REC", open=False):
                        with gr.Row():
                            rec_direct_rate_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="Taux REC Direct (%)", elem_classes="matrix")
                            rec_direct_var_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="Variation REC Direct", elem_classes="matrix")
                        with gr.Row():
                            rec_direct_close_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="REC clôture Direct", elem_classes="matrix")
                            direct_earned_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="Prime acquise Direct", elem_classes="matrix")
                        with gr.Row():
                            rec_reass_rate_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="Taux REC Réass (%)", elem_classes="matrix")
                            rec_reass_var_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="Variation REC Réass", elem_classes="matrix")
                        with gr.Row():
                            rec_reass_close_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="REC clôture Réass", elem_classes="matrix")
                            reass_earned_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="Prime acquise Réassurance", elem_classes="matrix")

            with gr.Tab("Commissions & DAC"):
                gr.Markdown("### Commissions · Direct / Réassurance / CPC", elem_classes="section-title")
                gr.Markdown("Le taux Direct est déduit de **Commission Direct / Prime brute**. La Réassurance dépend du Direct : **Commission Réassurance = Commission Direct × taux de récupération**. Le taux de récupération est déduit des blocs d'arrivée puis peut être fixe, linéaire ou modifié mois par mois.", elem_classes="muted")
                commission_summary = gr.HTML()
                commission_landing = gr.Dataframe(interactive=False, elem_classes="matrix", label="Taux implicites issus des ancrages")
                commission_chart = gr.Plot(label="Commissions, DAC et taux CPC")

                with gr.Accordion("Pilotage des commissions", open=True):
                    with gr.Row():
                        direct_commission_settings = gr.Dataframe(value=default_rate_settings("commission"), headers=RATE_SETTING_COLS, interactive=True, elem_classes="rate-settings", label="Commission Direct · règles par branche")
                        reass_commission_settings = gr.Dataframe(value=default_rate_settings("commission"), headers=RATE_SETTING_COLS, interactive=True, elem_classes="rate-settings", label="Récupération commission Réassurance · règles par branche")
                    with gr.Row():
                        direct_commission_manual = gr.Dataframe(value=blank_month_matrix(), headers=MONTH_GRID_COLS, interactive=True, elem_classes="matrix", label="Overrides mensuels · taux commission Direct (%)")
                        reass_commission_manual = gr.Dataframe(value=blank_month_matrix(), headers=MONTH_GRID_COLS, interactive=True, elem_classes="matrix", label="Overrides mensuels · taux récupération commission Réass (%)")

                    with gr.Row():
                        commission_point_branch = gr.Dropdown(BRANCHES, value=BRANCHES[0], label="Branche")
                        commission_point_month = gr.Dropdown(MONTHS, value=MONTHS[0], label="Mois")
                        direct_commission_override = gr.Number(label="Taux Direct (%)", precision=3)
                        reass_commission_override = gr.Number(label="Taux récupération Réass (%)", precision=3)
                    with gr.Row():
                        apply_direct_commission = gr.Button("Appliquer taux Direct")
                        apply_reass_commission = gr.Button("Appliquer récupération Réass")
                        clear_commission_point = gr.Button("Effacer ce mois")

                gr.Markdown("### Résultats commissions · 12 mois × 8 branches", elem_classes="section-title")
                with gr.Row():
                    direct_commission_rate_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="Taux commission Direct (%)", elem_classes="matrix")
                    reass_commission_rate_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="Taux récupération commission Réassurance (%)", elem_classes="matrix")
                with gr.Row():
                    direct_commission_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="Commission Direct", elem_classes="matrix")
                    reass_commission_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="Commission Réassurance", elem_classes="matrix")
                cpc_commission_rate_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="Taux de commission CPC sur prime acquise nette (%)", elem_classes="matrix")

                with gr.Accordion("DAC · IFRS uniquement", open=False):
                    gr.Markdown("DAC = REC 100% × taux DAC. L'ouverture DAC reste fixe sur l'exercice ; la clôture suit la REC 100% projetée. Variation DAC = ouverture − clôture.", elem_classes="muted")
                    with gr.Row():
                        direct_dac_settings = gr.Dataframe(value=default_rate_settings("dac"), headers=RATE_SETTING_COLS, interactive=True, elem_classes="rate-settings", label="DAC Direct · règles par branche")
                        reass_dac_settings = gr.Dataframe(value=default_rate_settings("dac"), headers=RATE_SETTING_COLS, interactive=True, elem_classes="rate-settings", label="DAC Réassurance · règles par branche")
                    with gr.Row():
                        direct_dac_manual = gr.Dataframe(value=blank_month_matrix(), headers=MONTH_GRID_COLS, interactive=True, elem_classes="matrix", label="Overrides mensuels · taux DAC Direct (%)")
                        reass_dac_manual = gr.Dataframe(value=blank_month_matrix(), headers=MONTH_GRID_COLS, interactive=True, elem_classes="matrix", label="Overrides mensuels · taux DAC Réass (%)")
                    with gr.Row():
                        direct_dac_rate_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="Taux DAC Direct IFRS (%)", elem_classes="matrix")
                        reass_dac_rate_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="Taux DAC Réass IFRS (%)", elem_classes="matrix")
                    with gr.Row():
                        direct_dac_open_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="DAC ouverture Direct IFRS", elem_classes="matrix")
                        direct_dac_close_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="DAC clôture Direct IFRS", elem_classes="matrix")
                    direct_dac_var_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="Variation DAC Direct IFRS", elem_classes="matrix")
                    with gr.Row():
                        reass_dac_open_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="DAC ouverture Réass IFRS", elem_classes="matrix")
                        reass_dac_close_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="DAC clôture Réass IFRS", elem_classes="matrix")
                    reass_dac_var_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="Variation DAC Réass IFRS", elem_classes="matrix")

            with gr.Tab("S/P & Charges"):
                gr.Markdown("### Pilotage S/P · exercice, global et résultat technique", elem_classes="section-title")
                gr.Markdown(
                    "Le **S/P exercice** détermine la charge de l'exercice. Le **S/P global** détermine la charge totale ; "
                    "la charge des antérieurs est le résiduel. Les branches verrouillées restent inchangées ; les autres "
                    "peuvent être optimisées dans leur plage pour atteindre une cible portefeuille.",
                    elem_classes="muted",
                )
                with gr.Row():
                    sp_month = gr.Dropdown(MONTHS, value=MONTHS[-1], label="Mois affiché", scale=1)
                    sp_recalc = gr.Button("Recalculer les S/P", variant="primary", scale=1)
                sp_summary = gr.HTML()
                sp_chart = gr.Plot(label="S/P, plages et résultat technique")

                gr.Markdown("### Ajustement de la branche sélectionnée", elem_classes="section-title")
                sp_branch_editor = gr.Dataframe(
                    value=pd.DataFrame({"Mois":MONTHS,"S/P exercice (%)":[np.nan]*12,"S/P global (%)":[np.nan]*12}),
                    headers=["Mois","S/P exercice (%)","S/P global (%)"],
                    interactive=True, row_count=(12,"fixed"), column_count=(3,"fixed"), elem_classes="sp-editor",
                    label="Modification mois par mois",
                )
                sp_branch_reference = gr.State(pd.DataFrame())
                with gr.Row():
                    apply_sp_edits = gr.Button("Appliquer les modifications", variant="primary")
                    reset_sp_edits = gr.Button("Réinitialiser la branche")
                sp_branch_result = gr.Dataframe(
                    headers=["Mois","S/P exercice (%)","S/P global (%)","Charge exercice","Charge antérieurs","Charge globale","Résultat technique avant FG"],
                    interactive=False, elem_classes="prime-result", label="Charges et résultat technique de la branche",
                )

                with gr.Accordion("Trajectoires et plages par branche", open=True):
                    locked_branches = gr.CheckboxGroup(BRANCHES, label="Branches verrouillées pour l'optimisation portefeuille")
                    with gr.Row():
                        sp_ex_settings = gr.Dataframe(
                            value=blank_sp_settings(), headers=SP_SETTING_COLS, interactive=True, elem_classes="rate-settings",
                            label="S/P exercice · Fixe ou Linéaire · plage autorisée",
                        )
                        sp_global_settings = gr.Dataframe(
                            value=blank_sp_settings(), headers=SP_SETTING_COLS, interactive=True, elem_classes="rate-settings",
                            label="S/P global · Fixe ou Linéaire · plage autorisée",
                        )
                    with gr.Accordion("Overrides mensuels 12 mois × 8 branches", open=False):
                        with gr.Row():
                            sp_ex_manual = gr.Dataframe(value=blank_month_matrix(), headers=MONTH_GRID_COLS, interactive=True, elem_classes="matrix", label="Overrides S/P exercice (%)")
                            sp_global_manual = gr.Dataframe(value=blank_month_matrix(), headers=MONTH_GRID_COLS, interactive=True, elem_classes="matrix", label="Overrides S/P global (%)")

                with gr.Accordion("Cible S/P du portefeuille", open=True):
                    gr.Markdown("La cible portefeuille est pondérée par la **prime acquise nette**. L'algorithme ne touche qu'aux branches non verrouillées et respecte leurs plages.", elem_classes="muted")
                    portfolio_mode = gr.Radio(["Libre","Fixe","Linéaire","Manuel"], value="Libre", label="Mode de cible portefeuille")
                    with gr.Row():
                        portfolio_ex_start = gr.Number(label="S/P exercice départ (%)", precision=3)
                        portfolio_ex_end = gr.Number(label="S/P exercice atterrissage (%)", precision=3)
                        portfolio_global_start = gr.Number(label="S/P global départ (%)", precision=3)
                        portfolio_global_end = gr.Number(label="S/P global atterrissage (%)", precision=3)
                    portfolio_manual = gr.Dataframe(
                        value=blank_portfolio_manual(),
                        headers=["Mois","S/P exercice cible (%)","S/P global cible (%)"],
                        interactive=True, row_count=(12,"fixed"), column_count=(3,"fixed"),
                        label="Cibles portefeuille mensuelles · facultatif",
                    )

                with gr.Accordion("Vue portefeuille · charges & résultat technique", open=False):
                    sp_portfolio = gr.Dataframe(interactive=False, elem_classes="matrix", label="Synthèse portefeuille mensuelle")
                    with gr.Row():
                        sp_ex_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, elem_classes="matrix", label="S/P exercice (%)")
                        sp_global_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, elem_classes="matrix", label="S/P global (%)")
                    with gr.Row():
                        charge_ex_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, elem_classes="matrix", label="Charge exercice")
                        charge_prior_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, elem_classes="matrix", label="Charge antérieurs")
                    with gr.Row():
                        charge_global_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, elem_classes="matrix", label="Charge globale")
                        technical_result_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, elem_classes="matrix", label="Résultat technique avant frais généraux")
                sp_diagnostics = gr.Dataframe(headers=["Diagnostic"], interactive=False, label="Diagnostic S/P")

            with gr.Tab("Diagnostics"):
                diagnostics = gr.Dataframe(headers=["Diagnostic"], interactive=False, label="Contrôles")

        gross_manual = gr.State(blank_month_matrix())

        load_btn.click(
            load_template,
            inputs=[upload],
            outputs=[hist_n3,hist_n2,hist_n1,anchors,commission_anchors,cession_hist,rec_direct_hist,rec_reass_local_hist,rec_reass_ifrs_hist,load_status],
        )

        inputs = [
            hist_n3,hist_n2,hist_n1,anchors,gross_manual,
            cession_settings,cession_hist,cession_manual,
            rec_direct_settings,rec_direct_hist,rec_direct_manual,
            rec_reass_local_settings,rec_reass_local_hist,rec_reass_local_manual,
            rec_reass_ifrs_settings,rec_reass_ifrs_hist,rec_reass_ifrs_manual,
            view,selected_branch,
            commission_anchors,
            direct_commission_settings,direct_commission_manual,
            reass_commission_settings,reass_commission_manual,
            direct_dac_settings,direct_dac_manual,
            reass_dac_settings,reass_dac_manual,
        ]
        outputs = [
            summary,cession_landing,chart,gross_grid,cession_grid,ceded_grid,net_grid,
            rec_direct_rate_grid,rec_direct_var_grid,rec_direct_close_grid,direct_earned_grid,
            rec_reass_rate_grid,rec_reass_var_grid,rec_reass_close_grid,reass_earned_grid,net_earned_grid,
            commission_summary,commission_landing,commission_chart,
            direct_commission_rate_grid,direct_commission_grid,reass_commission_rate_grid,reass_commission_grid,cpc_commission_rate_grid,
            direct_dac_rate_grid,direct_dac_open_grid,direct_dac_close_grid,direct_dac_var_grid,
            reass_dac_rate_grid,reass_dac_open_grid,reass_dac_close_grid,reass_dac_var_grid,
            diagnostics,reference_note,
            branch_kpis,branch_editor,branch_reference,branch_result,
        ]
        sp_inputs = [
            net_earned_grid,direct_commission_grid,reass_commission_grid,direct_dac_var_grid,view,selected_branch,sp_month,
            sp_ex_settings,sp_global_settings,sp_ex_manual,sp_global_manual,locked_branches,
            portfolio_mode,portfolio_ex_start,portfolio_ex_end,portfolio_global_start,portfolio_global_end,portfolio_manual,
        ]
        sp_outputs = [
            sp_summary,sp_chart,sp_branch_result,sp_ex_grid,sp_global_grid,charge_ex_grid,charge_prior_grid,
            charge_global_grid,technical_result_grid,sp_portfolio,sp_diagnostics,sp_branch_editor,sp_branch_reference,
        ]

        ev_recalc = recalc.click(run_projection, inputs=inputs, outputs=outputs)
        ev_recalc.then(run_sp_projection, inputs=sp_inputs, outputs=sp_outputs)
        ev_view = view.change(run_projection, inputs=inputs, outputs=outputs)
        ev_view.then(run_sp_projection, inputs=sp_inputs, outputs=sp_outputs)
        ev_branch = selected_branch.change(run_projection, inputs=inputs, outputs=outputs)
        ev_branch.then(run_sp_projection, inputs=sp_inputs, outputs=sp_outputs)

        # Tableau de pilotage compact : seules les cellules modifiées deviennent des overrides.
        apply_branch_edits.click(
            apply_branch_table,
            [branch_editor,branch_reference,selected_branch,view,gross_manual,cession_manual,rec_direct_manual,rec_reass_local_manual,rec_reass_ifrs_manual],
            [gross_manual,cession_manual,rec_direct_manual,rec_reass_local_manual,rec_reass_ifrs_manual],
        ).then(run_projection, inputs=inputs, outputs=outputs).then(run_sp_projection, inputs=sp_inputs, outputs=sp_outputs)

        reset_branch_edits.click(
            reset_branch_overrides,
            [selected_branch,gross_manual,cession_manual,rec_direct_manual,rec_reass_local_manual,rec_reass_ifrs_manual],
            [gross_manual,cession_manual,rec_direct_manual,rec_reass_local_manual,rec_reass_ifrs_manual],
        ).then(run_projection, inputs=inputs, outputs=outputs).then(run_sp_projection, inputs=sp_inputs, outputs=sp_outputs)

        apply_direct_commission.click(apply_point_override, [direct_commission_manual, commission_point_branch, commission_point_month, direct_commission_override], [direct_commission_manual]).then(run_projection, inputs=inputs, outputs=outputs).then(run_sp_projection, inputs=sp_inputs, outputs=sp_outputs)
        apply_reass_commission.click(apply_point_override, [reass_commission_manual, commission_point_branch, commission_point_month, reass_commission_override], [reass_commission_manual]).then(run_projection, inputs=inputs, outputs=outputs).then(run_sp_projection, inputs=sp_inputs, outputs=sp_outputs)

        def clear_comm_point(dc, rc, branch, month):
            return clear_point_override(dc,branch,month), clear_point_override(rc,branch,month)
        clear_commission_point.click(clear_comm_point, [direct_commission_manual,reass_commission_manual,commission_point_branch,commission_point_month], [direct_commission_manual,reass_commission_manual]).then(run_projection, inputs=inputs, outputs=outputs).then(run_sp_projection, inputs=sp_inputs, outputs=sp_outputs)

        # Pilotage S/P : recalcul immédiat des charges et du résultat technique.
        sp_recalc.click(run_sp_projection, inputs=sp_inputs, outputs=sp_outputs)
        sp_month.change(run_sp_projection, inputs=sp_inputs, outputs=sp_outputs)
        locked_branches.change(run_sp_projection, inputs=sp_inputs, outputs=sp_outputs)
        portfolio_mode.change(run_sp_projection, inputs=sp_inputs, outputs=sp_outputs)
        portfolio_ex_start.change(run_sp_projection, inputs=sp_inputs, outputs=sp_outputs)
        portfolio_ex_end.change(run_sp_projection, inputs=sp_inputs, outputs=sp_outputs)
        portfolio_global_start.change(run_sp_projection, inputs=sp_inputs, outputs=sp_outputs)
        portfolio_global_end.change(run_sp_projection, inputs=sp_inputs, outputs=sp_outputs)
        sp_ex_settings.change(run_sp_projection, inputs=sp_inputs, outputs=sp_outputs)
        sp_global_settings.change(run_sp_projection, inputs=sp_inputs, outputs=sp_outputs)
        portfolio_manual.change(run_sp_projection, inputs=sp_inputs, outputs=sp_outputs)
        sp_ex_manual.change(run_sp_projection, inputs=sp_inputs, outputs=sp_outputs)
        sp_global_manual.change(run_sp_projection, inputs=sp_inputs, outputs=sp_outputs)

        apply_sp_edits.click(
            apply_sp_branch_editor,
            [sp_branch_editor,sp_branch_reference,selected_branch,sp_ex_manual,sp_global_manual],
            [sp_ex_manual,sp_global_manual],
        ).then(run_sp_projection, inputs=sp_inputs, outputs=sp_outputs)
        reset_sp_edits.click(
            reset_sp_branch,[selected_branch,sp_ex_manual,sp_global_manual],[sp_ex_manual,sp_global_manual]
        ).then(run_sp_projection, inputs=sp_inputs, outputs=sp_outputs)

        demo.load(run_projection, inputs=inputs, outputs=outputs).then(run_sp_projection, inputs=sp_inputs, outputs=sp_outputs)
    return demo


if __name__ == "__main__":
    app = build_app()
    app.launch(server_name="0.0.0.0", server_port=int(os.environ.get("PORT", "7860")), show_error=True, theme=THEME, css=CSS)
