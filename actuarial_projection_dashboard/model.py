from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
import math
import numpy as np
import pandas as pd
from scipy.optimize import least_squares

BRANCHES = [
    "Automobile", "Santé", "Accident corporel", "Incendie",
    "BDM - Construction", "RC - RC Déc", "RD", "Transport",
]

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

DIRECT_TARGET_COLUMNS = [
    "branch", "gwp_ytd", "pap_close", "pane_close", "commission_ytd",
    "paid_current_ytd", "paid_prior_ytd", "recourse_current_ytd", "recourse_prior_ytd",
    "upr_close", "case_close_current", "case_close_prior", "ibnr_close_current",
    "ibnr_close_prior",
]

REASS_TARGET_COLUMNS = [
    "branch", "ceded_premium_ytd", "reass_commission_ytd", "recovered_paid_current_ytd",
    "recovered_paid_prior_ytd", "ceded_upr_close", "recoverable_case_close_current",
    "recoverable_case_close_prior", "recoverable_ibnr_close_current",
    "recoverable_ibnr_close_prior",
]

ASSUMPTION_COLUMNS = [
    "branch",
    "sp_exercice", "mode_sp_exercice",
    "sp_global", "mode_sp_global",
    "rec_target_rate", "mode_rec_target_rate",
    "commission_rate", "mode_commission_rate",
    "annual_premium_growth", "mode_annual_premium_growth",
    "upr_release_rate", "mode_upr_release_rate",
    "new_business_upr_share", "mode_new_business_upr_share",
    "payment_rate_current", "mode_payment_rate_current",
    "payment_rate_prior", "mode_payment_rate_prior",
    "ibnr_share_current", "mode_ibnr_share_current",
    "ibnr_share_prior", "mode_ibnr_share_prior",
    "premium_cession_rate", "mode_premium_cession_rate",
    "claim_recovery_current", "mode_claim_recovery_current",
    "claim_recovery_prior", "mode_claim_recovery_prior",
    "reass_commission_rate", "mode_reass_commission_rate",
]

PARAM_META = {
    "premium_multiplier": (0.05, 10.0, 1.0),
    "sp_exercice": (-0.5, 4.0, 0.55),
    "sp_global": (-1.0, 5.0, 0.65),
    "commission_rate": (0.0, 0.70, 0.15),
    "annual_premium_growth": (-0.80, 2.00, 0.05),
    "upr_release_rate": (0.0, 1.00, 1.0 / 12.0),
    "new_business_upr_share": (0.0, 1.50, 0.50),
    "payment_rate_current": (0.0, 1.00, 0.35),
    "payment_rate_prior": (0.0, 1.00, 0.40),
    "ibnr_share_current": (0.0, 1.00, 0.25),
    "ibnr_share_prior": (0.0, 1.00, 0.10),
    "premium_cession_rate": (0.0, 1.00, 0.25),
    "claim_recovery_current": (0.0, 1.50, 0.25),
    "claim_recovery_prior": (0.0, 1.50, 0.25),
    "reass_commission_rate": (0.0, 0.70, 0.15),
}

MODE_VALUES = ["Estimé", "Cible", "Fixé"]


def _num(v, default=0.0):
    if v is None:
        return float(default)
    try:
        if pd.isna(v):
            return float(default)
    except Exception:
        pass
    try:
        return float(v)
    except Exception:
        return float(default)


def _rate(v, default):
    x = _num(v, default)
    if abs(x) > 5.0:  # allows users to type 55 instead of 0.55
        x /= 100.0
    return x


def empty_direct_start(branches=BRANCHES):
    df = pd.DataFrame([{c: 0.0 for c in DIRECT_START_COLUMNS if c != "branch"} | {"branch": b} for b in branches])
    return df[DIRECT_START_COLUMNS]


def empty_reass_start(branches=BRANCHES):
    df = pd.DataFrame([{c: 0.0 for c in REASS_START_COLUMNS if c != "branch"} | {"branch": b} for b in branches])
    return df[REASS_START_COLUMNS]


def empty_direct_targets(branches=BRANCHES):
    rows = []
    for b in branches:
        row = {c: np.nan for c in DIRECT_TARGET_COLUMNS if c != "branch"}
        row["branch"] = b
        rows.append(row)
    return pd.DataFrame(rows)[DIRECT_TARGET_COLUMNS]


def empty_reass_targets(branches=BRANCHES):
    rows = []
    for b in branches:
        row = {c: np.nan for c in REASS_TARGET_COLUMNS if c != "branch"}
        row["branch"] = b
        rows.append(row)
    return pd.DataFrame(rows)[REASS_TARGET_COLUMNS]


def default_assumptions(branches=BRANCHES):
    rows = []
    for b in branches:
        r = {
            "branch": b,
            "sp_exercice": 0.55, "mode_sp_exercice": "Estimé",
            "sp_global": 0.65, "mode_sp_global": "Estimé",
            "rec_target_rate": 0.25, "mode_rec_target_rate": "Estimé",
            "commission_rate": 0.15, "mode_commission_rate": "Estimé",
            "annual_premium_growth": 0.05, "mode_annual_premium_growth": "Estimé",
            "upr_release_rate": 1/12, "mode_upr_release_rate": "Estimé",
            "new_business_upr_share": 0.50, "mode_new_business_upr_share": "Estimé",
            "payment_rate_current": 0.35, "mode_payment_rate_current": "Estimé",
            "payment_rate_prior": 0.40, "mode_payment_rate_prior": "Estimé",
            "ibnr_share_current": 0.25, "mode_ibnr_share_current": "Estimé",
            "ibnr_share_prior": 0.10, "mode_ibnr_share_prior": "Estimé",
            "premium_cession_rate": 0.25, "mode_premium_cession_rate": "Estimé",
            "claim_recovery_current": 0.25, "mode_claim_recovery_current": "Estimé",
            "claim_recovery_prior": 0.25, "mode_claim_recovery_prior": "Estimé",
            "reass_commission_rate": 0.15, "mode_reass_commission_rate": "Estimé",
        }
        rows.append(r)
    return pd.DataFrame(rows)[ASSUMPTION_COLUMNS]


def normalize_table(df: Optional[pd.DataFrame], columns: List[str], branches=BRANCHES) -> pd.DataFrame:
    if df is None or len(df) == 0:
        if columns == DIRECT_START_COLUMNS:
            return empty_direct_start(branches)
        if columns == REASS_START_COLUMNS:
            return empty_reass_start(branches)
        if columns == DIRECT_TARGET_COLUMNS:
            return empty_direct_targets(branches)
        if columns == REASS_TARGET_COLUMNS:
            return empty_reass_targets(branches)
    d = pd.DataFrame(df).copy()
    for c in columns:
        if c not in d.columns:
            d[c] = np.nan if c != "branch" else None
    d = d[columns]
    d = d[d["branch"].notna()].copy()
    return d


def normalize_assumptions(df: Optional[pd.DataFrame], branches=BRANCHES) -> pd.DataFrame:
    base = default_assumptions(branches).set_index("branch")
    if df is None or len(df) == 0:
        return base.reset_index()[ASSUMPTION_COLUMNS]
    d = pd.DataFrame(df).copy()
    if "branch" not in d.columns:
        return base.reset_index()[ASSUMPTION_COLUMNS]
    d = d.set_index("branch")
    for b in base.index:
        if b not in d.index:
            d.loc[b] = base.loc[b]
    for c in ASSUMPTION_COLUMNS[1:]:
        if c not in d.columns:
            d[c] = base[c]
        else:
            d[c] = d[c].where(d[c].notna(), base[c])
    return d.reset_index()[ASSUMPTION_COLUMNS]


def month_range(start_period: str, n_periods: int) -> List[pd.Timestamp]:
    p = pd.Period(start_period, freq="M")
    return [(p + i).to_timestamp("M") for i in range(1, int(n_periods) + 1)]


def uniform_seasonality():
    return np.ones(12, dtype=float) / 12.0


def estimate_profiles(history_direct: Optional[pd.DataFrame], history_reass: Optional[pd.DataFrame], branches=BRANCHES) -> Dict[str, dict]:
    profiles: Dict[str, dict] = {}
    hd = pd.DataFrame(history_direct).copy() if history_direct is not None else pd.DataFrame()
    hr = pd.DataFrame(history_reass).copy() if history_reass is not None else pd.DataFrame()
    if not hd.empty and "period" in hd.columns:
        hd["period"] = pd.to_datetime(hd["period"])
    if not hr.empty and "period" in hr.columns:
        hr["period"] = pd.to_datetime(hr["period"])

    for b in branches:
        prof = {
            "seasonality": uniform_seasonality(),
            "commission_rate": 0.15,
            "premium_cession_rate": 0.25,
            "claim_recovery_current": 0.25,
            "claim_recovery_prior": 0.25,
            "reass_commission_rate": 0.15,
            "sp_exercice": 0.55,
            "sp_global": 0.65,
            "payment_rate_current": 0.35,
            "payment_rate_prior": 0.40,
            "ibnr_share_current": 0.25,
            "ibnr_share_prior": 0.10,
            "annual_premium_growth": 0.05,
        }
        db = hd[hd.get("branch", pd.Series(dtype=str)) == b].sort_values("period") if not hd.empty else pd.DataFrame()
        rb = hr[hr.get("branch", pd.Series(dtype=str)) == b].sort_values("period") if not hr.empty else pd.DataFrame()

        if len(db) >= 2 and "gwp_ytd" in db:
            monthly_weights = []
            for _, yg in db.groupby(db["period"].dt.year):
                yg = yg.sort_values("period")
                ytd = pd.to_numeric(yg["gwp_ytd"], errors="coerce").fillna(0).to_numpy(float)
                inc = np.diff(np.r_[0.0, ytd])
                total = ytd[-1] if len(ytd) else 0
                if total > 0:
                    arr = np.zeros(12)
                    for m, val in zip(yg["period"].dt.month.to_numpy(), inc):
                        arr[int(m)-1] = max(0.0, float(val))
                    if arr.sum() > 0:
                        monthly_weights.append(arr / arr.sum())
            if monthly_weights:
                s = np.mean(monthly_weights, axis=0)
                prof["seasonality"] = s / s.sum() if s.sum() > 0 else uniform_seasonality()

            ratios = pd.to_numeric(db.get("commission_ytd"), errors="coerce") / pd.to_numeric(db.get("gwp_ytd"), errors="coerce").replace(0, np.nan)
            if ratios.notna().any():
                prof["commission_rate"] = float(np.clip(ratios.median(), 0, 0.7))

            # Loss ratio estimates from accounting identity, using year-opening reserves.
            try:
                rows = []
                for year, yg in db.groupby(db["period"].dt.year):
                    yg = yg.sort_values("period")
                    first = yg.iloc[0]
                    upr_year_open = _num(first.get("upr_open"))
                    prior_open = _num(first.get("case_open_prior")) + _num(first.get("ibnr_open_prior"))
                    for _, r in yg.iterrows():
                        earned = _num(r.get("gwp_ytd")) + upr_year_open - _num(r.get("upr_close"))
                        if abs(earned) < 1e-9:
                            continue
                        cur_inc = _num(r.get("paid_current_ytd")) + _num(r.get("case_close_current")) + _num(r.get("ibnr_close_current"))
                        prior_move = _num(r.get("paid_prior_ytd")) + _num(r.get("case_close_prior")) + _num(r.get("ibnr_close_prior")) - prior_open
                        rows.append((cur_inc/earned, (cur_inc + prior_move)/earned))
                if rows:
                    vals = np.array(rows, float)
                    prof["sp_exercice"] = float(np.clip(np.nanmedian(vals[:,0]), -0.5, 4.0))
                    prof["sp_global"] = float(np.clip(np.nanmedian(vals[:,1]), -1.0, 5.0))
            except Exception:
                pass

            last = db.iloc[-1]
            out_cur = _num(last.get("case_close_current")) + _num(last.get("ibnr_close_current"))
            if out_cur > 0:
                prof["ibnr_share_current"] = float(np.clip(_num(last.get("ibnr_close_current"))/out_cur, 0, 1))
            out_pr = _num(last.get("case_close_prior")) + _num(last.get("ibnr_close_prior"))
            if out_pr > 0:
                prof["ibnr_share_prior"] = float(np.clip(_num(last.get("ibnr_close_prior"))/out_pr, 0, 1))

        if not rb.empty:
            if "ceded_premium_ytd" in rb.columns and not db.empty:
                merged = pd.merge(
                    db[["period","gwp_ytd"]], rb[["period","ceded_premium_ytd"]], on="period", how="inner"
                )
                rat = pd.to_numeric(merged["ceded_premium_ytd"], errors="coerce") / pd.to_numeric(merged["gwp_ytd"], errors="coerce").replace(0,np.nan)
                if rat.notna().any():
                    prof["premium_cession_rate"] = float(np.clip(rat.median(),0,1))
            if "reass_commission_ytd" in rb.columns:
                rat = pd.to_numeric(rb["reass_commission_ytd"], errors="coerce") / pd.to_numeric(rb["ceded_premium_ytd"], errors="coerce").replace(0,np.nan)
                if rat.notna().any():
                    prof["reass_commission_rate"] = float(np.clip(rat.median(),0,0.7))
            if not db.empty:
                m = pd.merge(db[["period","paid_current_ytd","paid_prior_ytd"]], rb[["period","recovered_paid_current_ytd","recovered_paid_prior_ytd"]], on="period", how="inner")
                ratc = pd.to_numeric(m["recovered_paid_current_ytd"], errors="coerce") / pd.to_numeric(m["paid_current_ytd"], errors="coerce").replace(0,np.nan)
                ratp = pd.to_numeric(m["recovered_paid_prior_ytd"], errors="coerce") / pd.to_numeric(m["paid_prior_ytd"], errors="coerce").replace(0,np.nan)
                if ratc.notna().any(): prof["claim_recovery_current"] = float(np.clip(ratc.median(),0,1.5))
                if ratp.notna().any(): prof["claim_recovery_prior"] = float(np.clip(ratp.median(),0,1.5))
        profiles[b] = prof
    return profiles


def _get_target(row: pd.Series, key: str):
    if row is None or key not in row.index:
        return None
    v = row[key]
    try:
        if pd.isna(v):
            return None
    except Exception:
        pass
    try:
        return float(v)
    except Exception:
        return None


def _mode_value(row: pd.Series, param: str, profile: dict):
    lo, hi, dflt = PARAM_META[param]
    if param == "premium_multiplier":
        return 1.0, "Estimé"
    raw = row.get(param, profile.get(param, dflt)) if row is not None else profile.get(param, dflt)
    val = _rate(raw, profile.get(param, dflt))
    val = float(np.clip(val, lo, hi))
    mode = str(row.get("mode_" + param, "Estimé")) if row is not None else "Estimé"
    if mode not in MODE_VALUES:
        mode = "Estimé"
    return val, mode


def _annual_base_from_start(start: pd.Series, start_period: pd.Period, seasonality: np.ndarray) -> float:
    ytd = max(0.0, _num(start.get("gwp_ytd")))
    cumw = float(np.sum(seasonality[: start_period.month]))
    if ytd > 0 and cumw > 1e-9:
        return ytd / cumw
    return max(ytd * (12.0 / max(1, start_period.month)), 1.0)


def _linear_target_path(open_value: float, target_value: Optional[float], n: int) -> List[float]:
    if target_value is None or n <= 0:
        return [open_value] * n
    return list(np.linspace(open_value, target_value, n + 1)[1:])


def simulate_branch(
    branch: str,
    start_direct: pd.Series,
    start_reass: pd.Series,
    target_direct: pd.Series,
    target_reass: pd.Series,
    assumptions: pd.Series,
    profile: dict,
    start_period: str,
    n_periods: int,
    params: Dict[str, float],
) -> Tuple[pd.DataFrame, pd.DataFrame, List[dict]]:
    start_p = pd.Period(start_period, freq="M")
    dates = month_range(start_period, n_periods)
    season = np.array(profile.get("seasonality", uniform_seasonality()), dtype=float)
    if season.sum() <= 0:
        season = uniform_seasonality()
    season = season / season.sum()

    annual_base = _annual_base_from_start(start_direct, start_p, season)
    p_mult = params["premium_multiplier"]
    growth = params["annual_premium_growth"]

    # Fixed opening states come from the last actual closing state, never from the optimizer.
    upr_close_prev = _num(start_direct.get("upr_close"))
    case_cur_prev = _num(start_direct.get("case_close_current"))
    case_pr_prev = _num(start_direct.get("case_close_prior"))
    ibnr_cur_prev = _num(start_direct.get("ibnr_close_current"))
    ibnr_pr_prev = _num(start_direct.get("ibnr_close_prior"))
    pap_close_prev = _num(start_direct.get("pap_close"))
    pane_close_prev = _num(start_direct.get("pane_close"))

    ceded_upr_close_prev = _num(start_reass.get("ceded_upr_close"))
    rcase_cur_prev = _num(start_reass.get("recoverable_case_close_current"))
    rcase_pr_prev = _num(start_reass.get("recoverable_case_close_prior"))
    ribnr_cur_prev = _num(start_reass.get("recoverable_ibnr_close_current"))
    ribnr_pr_prev = _num(start_reass.get("recoverable_ibnr_close_prior"))

    pap_path = _linear_target_path(pap_close_prev, _get_target(target_direct, "pap_close"), n_periods)
    pane_path = _linear_target_path(pane_close_prev, _get_target(target_direct, "pane_close"), n_periods)

    # YTD accumulators. They reset on 1 January; stock openings carry forward.
    gwp_ytd = _num(start_direct.get("gwp_ytd"))
    comm_ytd = _num(start_direct.get("commission_ytd"))
    paid_cur_ytd = _num(start_direct.get("paid_current_ytd"))
    paid_pr_ytd = _num(start_direct.get("paid_prior_ytd"))
    recourse_cur_ytd = _num(start_direct.get("recourse_current_ytd"))
    recourse_pr_ytd = _num(start_direct.get("recourse_prior_ytd"))
    earned_ytd = gwp_ytd + _num(start_direct.get("upr_open")) - upr_close_prev
    incurred_cur_ytd_prev = paid_cur_ytd + case_cur_prev + ibnr_cur_prev
    prior_open_at_year = _num(start_direct.get("case_open_prior")) + _num(start_direct.get("ibnr_open_prior"))
    incurred_pr_ytd_prev = paid_pr_ytd + case_pr_prev + ibnr_pr_prev - prior_open_at_year

    ceded_premium_ytd = _num(start_reass.get("ceded_premium_ytd"))
    reass_comm_ytd = _num(start_reass.get("reass_commission_ytd"))
    recov_paid_cur_ytd = _num(start_reass.get("recovered_paid_current_ytd"))
    recov_paid_pr_ytd = _num(start_reass.get("recovered_paid_prior_ytd"))
    ceded_earned_ytd = ceded_premium_ytd + _num(start_reass.get("ceded_upr_open")) - ceded_upr_close_prev

    direct_rows = []
    reass_rows = []
    issues: List[dict] = []
    current_year = start_p.year

    for i, dt in enumerate(dates):
        period = pd.Period(dt, freq="M")
        if period.year != current_year:
            # Calendar reset of flows/YTD. Previous current-year outstanding becomes prior-year outstanding.
            current_year = period.year
            case_pr_prev = case_pr_prev + case_cur_prev
            ibnr_pr_prev = ibnr_pr_prev + ibnr_cur_prev
            case_cur_prev = 0.0
            ibnr_cur_prev = 0.0
            rcase_pr_prev = rcase_pr_prev + rcase_cur_prev
            ribnr_pr_prev = ribnr_pr_prev + ribnr_cur_prev
            rcase_cur_prev = 0.0
            ribnr_cur_prev = 0.0
            gwp_ytd = comm_ytd = paid_cur_ytd = paid_pr_ytd = recourse_cur_ytd = recourse_pr_ytd = 0.0
            ceded_premium_ytd = reass_comm_ytd = recov_paid_cur_ytd = recov_paid_pr_ytd = 0.0
            earned_ytd = ceded_earned_ytd = 0.0
            incurred_cur_ytd_prev = incurred_pr_ytd_prev = 0.0
            prior_open_at_year = case_pr_prev + ibnr_pr_prev

        year_offset = period.year - start_p.year
        annual_total = max(0.0, annual_base * p_mult * ((1.0 + growth) ** max(0, year_offset)))
        gwp_inc = max(0.0, annual_total * season[period.month - 1])
        gwp_ytd += gwp_inc

        pap_open = pap_close_prev
        pane_open = pane_close_prev
        pap_close = max(0.0, float(pap_path[i])) if i < len(pap_path) else pap_open
        pane_close = max(0.0, float(pane_path[i])) if i < len(pane_path) else pane_open
        revenue = gwp_ytd - pap_open + pap_close - pane_open + pane_close

        upr_open = upr_close_prev
        upr_close = max(0.0, upr_open * (1.0 - params["upr_release_rate"]) + gwp_inc * params["new_business_upr_share"])
        earned_inc = gwp_inc + upr_open - upr_close
        earned_ytd += earned_inc

        commission_inc = max(0.0, gwp_inc * params["commission_rate"])
        comm_ytd += commission_inc

        target_cur_inc_ytd = params["sp_exercice"] * earned_ytd
        target_global_inc_ytd = params["sp_global"] * earned_ytd
        target_prior_move_ytd = target_global_inc_ytd - target_cur_inc_ytd
        cur_inc = target_cur_inc_ytd - incurred_cur_ytd_prev
        pr_inc = target_prior_move_ytd - incurred_pr_ytd_prev

        # Claims identity: incurred = paid + closing outstanding - opening outstanding.
        cur_open_out = case_cur_prev + ibnr_cur_prev
        available_cur = cur_open_out + cur_inc
        if available_cur < -1e-6:
            issues.append({"branch": branch, "period": str(period), "severity": "Alerte", "message": "Le S/P exercice demande une reprise supérieure aux provisions disponibles."})
            available_cur = 0.0
        paid_cur_inc = max(0.0, min(available_cur, available_cur * params["payment_rate_current"]))
        cur_close_out = max(0.0, available_cur - paid_cur_inc)
        ibnr_cur_close = cur_close_out * params["ibnr_share_current"]
        case_cur_close = cur_close_out - ibnr_cur_close

        pr_open_out = case_pr_prev + ibnr_pr_prev
        available_pr = pr_open_out + pr_inc
        if available_pr < -1e-6:
            issues.append({"branch": branch, "period": str(period), "severity": "Alerte", "message": "Le S/P global implique une reprise des antérieurs supérieure aux provisions disponibles."})
            available_pr = 0.0
        paid_pr_inc = max(0.0, min(available_pr, available_pr * params["payment_rate_prior"]))
        pr_close_out = max(0.0, available_pr - paid_pr_inc)
        ibnr_pr_close = pr_close_out * params["ibnr_share_prior"]
        case_pr_close = pr_close_out - ibnr_pr_close

        # Realized incurred after non-negativity constraints.
        realized_cur_inc = paid_cur_inc + cur_close_out - cur_open_out
        realized_pr_inc = paid_pr_inc + pr_close_out - pr_open_out
        incurred_cur_ytd_prev += realized_cur_inc
        incurred_pr_ytd_prev += realized_pr_inc
        paid_cur_ytd += paid_cur_inc
        paid_pr_ytd += paid_pr_inc

        # Recourse is informational in this MVP; it does not distort the claims identity.
        recourse_cur_inc = 0.0
        recourse_pr_inc = 0.0
        recourse_cur_ytd += recourse_cur_inc
        recourse_pr_ytd += recourse_pr_inc

        sp_ex = incurred_cur_ytd_prev / earned_ytd if abs(earned_ytd) > 1e-9 else np.nan
        sp_gl = (incurred_cur_ytd_prev + incurred_pr_ytd_prev) / earned_ytd if abs(earned_ytd) > 1e-9 else np.nan
        comm_rate_real = comm_ytd / gwp_ytd if abs(gwp_ytd) > 1e-9 else np.nan

        direct_rows.append({
            "period": period.to_timestamp("M"), "branch": branch,
            "gwp_increment": gwp_inc, "gwp_ytd": gwp_ytd,
            "pap_open": pap_open, "pap_close": pap_close, "pane_open": pane_open, "pane_close": pane_close,
            "revenue": revenue,
            "commission_increment": commission_inc, "commission_ytd": comm_ytd,
            "paid_current_increment": paid_cur_inc, "paid_current_ytd": paid_cur_ytd,
            "paid_prior_increment": paid_pr_inc, "paid_prior_ytd": paid_pr_ytd,
            "recourse_current_ytd": recourse_cur_ytd, "recourse_prior_ytd": recourse_pr_ytd,
            "upr_open": upr_open, "upr_close": upr_close, "upr_variation": upr_close - upr_open,
            "earned_premium_increment": earned_inc, "earned_premium_ytd": earned_ytd,
            "case_open_current": case_cur_prev, "case_close_current": case_cur_close,
            "case_open_prior": case_pr_prev, "case_close_prior": case_pr_close,
            "ibnr_open_current": ibnr_cur_prev, "ibnr_close_current": ibnr_cur_close,
            "ibnr_open_prior": ibnr_pr_prev, "ibnr_close_prior": ibnr_pr_close,
            "incurred_current_increment": realized_cur_inc, "incurred_current_ytd": incurred_cur_ytd_prev,
            "incurred_prior_increment": realized_pr_inc, "incurred_prior_ytd": incurred_pr_ytd_prev,
            "sp_exercice": sp_ex, "sp_global": sp_gl, "commission_rate": comm_rate_real,
        })

        # Reinsurance: premiums and claim recoveries are separate drivers.
        ceded_prem_inc = gwp_inc * params["premium_cession_rate"]
        ceded_premium_ytd += ceded_prem_inc
        ceded_upr_open = ceded_upr_close_prev
        ceded_upr_close = max(0.0, upr_close * params["premium_cession_rate"])
        ceded_earned_inc = ceded_prem_inc + ceded_upr_open - ceded_upr_close
        ceded_earned_ytd += ceded_earned_inc
        reass_comm_inc = ceded_prem_inc * params["reass_commission_rate"]
        reass_comm_ytd += reass_comm_inc

        recovered_paid_cur_inc = paid_cur_inc * params["claim_recovery_current"]
        recovered_paid_pr_inc = paid_pr_inc * params["claim_recovery_prior"]
        recov_paid_cur_ytd += recovered_paid_cur_inc
        recov_paid_pr_ytd += recovered_paid_pr_inc

        recoverable_case_cur_close = case_cur_close * params["claim_recovery_current"]
        recoverable_ibnr_cur_close = ibnr_cur_close * params["claim_recovery_current"]
        recoverable_case_pr_close = case_pr_close * params["claim_recovery_prior"]
        recoverable_ibnr_pr_close = ibnr_pr_close * params["claim_recovery_prior"]

        recovered_incurred_cur_inc = recovered_paid_cur_inc + (recoverable_case_cur_close + recoverable_ibnr_cur_close) - (rcase_cur_prev + ribnr_cur_prev)
        recovered_incurred_pr_inc = recovered_paid_pr_inc + (recoverable_case_pr_close + recoverable_ibnr_pr_close) - (rcase_pr_prev + ribnr_pr_prev)
        recovery_sp = (recovered_incurred_cur_inc + recovered_incurred_pr_inc) / ceded_earned_inc if abs(ceded_earned_inc) > 1e-9 else np.nan

        reass_rows.append({
            "period": period.to_timestamp("M"), "branch": branch,
            "ceded_premium_increment": ceded_prem_inc, "ceded_premium_ytd": ceded_premium_ytd,
            "reass_commission_increment": reass_comm_inc, "reass_commission_ytd": reass_comm_ytd,
            "ceded_upr_open": ceded_upr_open, "ceded_upr_close": ceded_upr_close,
            "ceded_upr_variation": ceded_upr_close - ceded_upr_open,
            "ceded_earned_premium_increment": ceded_earned_inc, "ceded_earned_premium_ytd": ceded_earned_ytd,
            "recovered_paid_current_increment": recovered_paid_cur_inc, "recovered_paid_current_ytd": recov_paid_cur_ytd,
            "recovered_paid_prior_increment": recovered_paid_pr_inc, "recovered_paid_prior_ytd": recov_paid_pr_ytd,
            "recoverable_case_open_current": rcase_cur_prev, "recoverable_case_close_current": recoverable_case_cur_close,
            "recoverable_case_open_prior": rcase_pr_prev, "recoverable_case_close_prior": recoverable_case_pr_close,
            "recoverable_ibnr_open_current": ribnr_cur_prev, "recoverable_ibnr_close_current": recoverable_ibnr_cur_close,
            "recoverable_ibnr_open_prior": ribnr_pr_prev, "recoverable_ibnr_close_prior": recoverable_ibnr_pr_close,
            "recovered_incurred_current_increment": recovered_incurred_cur_inc,
            "recovered_incurred_prior_increment": recovered_incurred_pr_inc,
            "cession_rate": params["premium_cession_rate"],
            "claim_recovery_current": params["claim_recovery_current"],
            "claim_recovery_prior": params["claim_recovery_prior"],
            "reass_commission_rate": params["reass_commission_rate"],
            "recovery_sp_period": recovery_sp,
        })

        # Carry closing stocks forward: next opening is fixed by accounting continuity.
        upr_close_prev = upr_close
        case_cur_prev, case_pr_prev = case_cur_close, case_pr_close
        ibnr_cur_prev, ibnr_pr_prev = ibnr_cur_close, ibnr_pr_close
        pap_close_prev, pane_close_prev = pap_close, pane_close
        ceded_upr_close_prev = ceded_upr_close
        rcase_cur_prev, rcase_pr_prev = recoverable_case_cur_close, recoverable_case_pr_close
        ribnr_cur_prev, ribnr_pr_prev = recoverable_ibnr_cur_close, recoverable_ibnr_pr_close

    return pd.DataFrame(direct_rows), pd.DataFrame(reass_rows), issues


def _target_residuals(final_row: pd.Series, target_row: pd.Series, keys: List[str], strict_weight: float):
    res = []
    for k in keys:
        t = _get_target(target_row, k)
        if t is None or k not in final_row.index:
            continue
        s = _num(final_row[k])
        scale = max(abs(t), abs(s), 1_000_000.0)
        res.append(strict_weight * (s - t) / scale)
    return res


def calibrate_branch(
    branch: str,
    start_direct: pd.Series,
    start_reass: pd.Series,
    target_direct: pd.Series,
    target_reass: pd.Series,
    assumptions: pd.Series,
    profile: dict,
    start_period: str,
    n_periods: int,
    target_policy: str = "Cible",
):
    base = {}
    modes = {}
    for p in PARAM_META:
        if p == "premium_multiplier":
            base[p], modes[p] = 1.0, "Estimé"
        else:
            base[p], modes[p] = _mode_value(assumptions, p, profile)

    var_names = [p for p in PARAM_META if modes.get(p, "Estimé") != "Fixé"]
    x0 = np.array([base[p] for p in var_names], float)
    lb = np.array([PARAM_META[p][0] for p in var_names], float)
    ub = np.array([PARAM_META[p][1] for p in var_names], float)
    x0 = np.clip(x0, lb + 1e-8, ub - 1e-8)
    target_weight = 18.0 if target_policy.lower().startswith("strict") else 7.0

    direct_keys = [c for c in DIRECT_TARGET_COLUMNS if c != "branch"]
    reass_keys = [c for c in REASS_TARGET_COLUMNS if c != "branch"]

    def unpack(x):
        p = dict(base)
        for n, v in zip(var_names, x):
            p[n] = float(v)
        return p

    def residual(x):
        p = unpack(x)
        d, r, _ = simulate_branch(branch, start_direct, start_reass, target_direct, target_reass, assumptions, profile, start_period, n_periods, p)
        fr_d = d.iloc[-1] if len(d) else pd.Series(dtype=float)
        fr_r = r.iloc[-1] if len(r) else pd.Series(dtype=float)
        res = []
        res.extend(_target_residuals(fr_d, target_direct, direct_keys, target_weight))
        res.extend(_target_residuals(fr_r, target_reass, reass_keys, target_weight))
        # User-friendly REC target: it constrains the horizon ratio without forcing a naive monthly formula.
        rec_raw = assumptions.get("rec_target_rate", np.nan)
        try:
            rec_missing = pd.isna(rec_raw)
        except Exception:
            rec_missing = False
        if not rec_missing and abs(_num(fr_d.get("gwp_ytd"))) > 1e-9:
            rec_target = _rate(rec_raw, 0.25)
            rec_mode = str(assumptions.get("mode_rec_target_rate", "Cible"))
            rec_weight = 18.0 if rec_mode == "Fixé" else (4.0 if rec_mode == "Cible" else 0.35)
            res.append(rec_weight * ((_num(fr_d.get("upr_close")) / _num(fr_d.get("gwp_ytd"))) - rec_target))
        # Parameter modes: Fixed parameters are excluded, Cible is strong, Estimé is a regularization prior.
        for name in var_names:
            lo, hi, _ = PARAM_META[name]
            scale = max(hi - lo, 1e-6)
            desired = base[name]
            if modes.get(name) == "Cible":
                res.append(3.0 * (p[name] - desired) / scale)
            else:
                prior = profile.get(name, desired)
                res.append(0.35 * (p[name] - prior) / scale)
        return np.asarray(res if res else [0.0], dtype=float)

    if var_names:
        sol = least_squares(residual, x0, bounds=(lb, ub), max_nfev=450, xtol=1e-9, ftol=1e-9, gtol=1e-9)
        params = unpack(sol.x)
        opt_status = {"success": bool(sol.success), "cost": float(sol.cost), "message": str(sol.message)}
    else:
        params = base
        opt_status = {"success": True, "cost": 0.0, "message": "Tous les paramètres sont fixés."}

    direct, reass, issues = simulate_branch(branch, start_direct, start_reass, target_direct, target_reass, assumptions, profile, start_period, n_periods, params)
    return direct, reass, params, issues, opt_status


def _row_for_branch(df: pd.DataFrame, branch: str) -> pd.Series:
    hit = df[df["branch"] == branch]
    if hit.empty:
        return pd.Series({"branch": branch})
    return hit.iloc[0]


def run_projection(
    start_direct: pd.DataFrame,
    start_reass: pd.DataFrame,
    target_direct: pd.DataFrame,
    target_reass: pd.DataFrame,
    assumptions: pd.DataFrame,
    start_period: str,
    n_periods: int,
    history_direct: Optional[pd.DataFrame] = None,
    history_reass: Optional[pd.DataFrame] = None,
    target_policy: str = "Cible",
):
    sd = normalize_table(start_direct, DIRECT_START_COLUMNS)
    sr = normalize_table(start_reass, REASS_START_COLUMNS)
    td = normalize_table(target_direct, DIRECT_TARGET_COLUMNS)
    tr = normalize_table(target_reass, REASS_TARGET_COLUMNS)
    ah = normalize_assumptions(assumptions)
    branches = [b for b in BRANCHES if b in set(sd["branch"]) | set(td["branch"]) | set(ah["branch"])]
    profiles = estimate_profiles(history_direct, history_reass, branches)

    all_d, all_r, diag, param_rows = [], [], [], []
    for b in branches:
        d, r, p, issues, stat = calibrate_branch(
            b, _row_for_branch(sd,b), _row_for_branch(sr,b), _row_for_branch(td,b), _row_for_branch(tr,b),
            _row_for_branch(ah,b), profiles[b], start_period, int(n_periods), target_policy
        )
        all_d.append(d); all_r.append(r)
        param_rows.append({"branch": b, **p, "optimizer_cost": stat["cost"], "optimizer_success": stat["success"]})
        diag.extend(issues)

        if len(d):
            fd = d.iloc[-1]; fr = r.iloc[-1]
            # Target reconciliation diagnostics.
            for key in [c for c in DIRECT_TARGET_COLUMNS if c != "branch"]:
                t = _get_target(_row_for_branch(td,b), key)
                if t is not None and key in fd.index:
                    gap = _num(fd[key]) - t
                    tol = max(1_000.0, abs(t)*0.005)
                    if abs(gap) > tol:
                        diag.append({"branch":b,"period":str(pd.Period(fd["period"],freq="M")),"severity":"Écart cible","message":f"{key}: cible {t:,.0f}, obtenu {_num(fd[key]):,.0f}, écart {gap:,.0f}."})
            for key in [c for c in REASS_TARGET_COLUMNS if c != "branch"]:
                t = _get_target(_row_for_branch(tr,b), key)
                if t is not None and key in fr.index:
                    gap = _num(fr[key]) - t
                    tol = max(1_000.0, abs(t)*0.005)
                    if abs(gap) > tol:
                        diag.append({"branch":b,"period":str(pd.Period(fr["period"],freq="M")),"severity":"Écart cible","message":f"Réass {key}: cible {t:,.0f}, obtenu {_num(fr[key]):,.0f}, écart {gap:,.0f}."})

    direct = pd.concat(all_d, ignore_index=True) if all_d else pd.DataFrame()
    reass = pd.concat(all_r, ignore_index=True) if all_r else pd.DataFrame()
    params_df = pd.DataFrame(param_rows)
    diag_df = pd.DataFrame(diag, columns=["branch","period","severity","message"]) if diag else pd.DataFrame(columns=["branch","period","severity","message"])

    summary_rows = []
    if not direct.empty:
        for period, dg in direct.groupby("period"):
            rg = reass[reass["period"] == period]
            gross_earned = dg["earned_premium_increment"].sum()
            gross_incurred = dg["incurred_current_increment"].sum() + dg["incurred_prior_increment"].sum()
            gross_comm = dg["commission_increment"].sum()
            ceded_earned = rg["ceded_earned_premium_increment"].sum() if not rg.empty else 0.0
            rec_incurred = (rg["recovered_incurred_current_increment"].sum() + rg["recovered_incurred_prior_increment"].sum()) if not rg.empty else 0.0
            reass_comm = rg["reass_commission_increment"].sum() if not rg.empty else 0.0
            net_earned = gross_earned - ceded_earned
            net_incurred = gross_incurred - rec_incurred
            net_comm = gross_comm - reass_comm
            tech_result = net_earned - net_incurred - net_comm
            summary_rows.append({
                "period": period,
                "gross_written_premium": dg["gwp_increment"].sum(),
                "gross_earned_premium": gross_earned,
                "gross_incurred_claims": gross_incurred,
                "gross_commission": gross_comm,
                "ceded_earned_premium": ceded_earned,
                "recovered_incurred_claims": rec_incurred,
                "reinsurance_commission": reass_comm,
                "net_earned_premium": net_earned,
                "net_incurred_claims": net_incurred,
                "net_commission": net_comm,
                "technical_result_before_general_expenses": tech_result,
                "gross_loss_ratio": gross_incurred/gross_earned if abs(gross_earned)>1e-9 else np.nan,
                "net_loss_ratio": net_incurred/net_earned if abs(net_earned)>1e-9 else np.nan,
            })
    summary = pd.DataFrame(summary_rows)
    return direct, reass, summary, diag_df, params_df


def make_legacy_direct_block(direct: pd.DataFrame) -> pd.DataFrame:
    """Long-form block close to Direct Local, but built from coherent standard identities."""
    if direct.empty:
        return pd.DataFrame(columns=["period","branch","line","value"])
    rows=[]
    for _, r in direct.iterrows():
        vals = {
            "Primes Emises": r["gwp_ytd"],
            "PAP Ouverture": r["pap_open"], "PAP Clôture": r["pap_close"],
            "PANE Ouverture": r["pane_open"], "PANE Clôture": r["pane_close"],
            "Chiffre d'Affaire": r["revenue"],
            "Sinistres payés Per.": r["paid_current_ytd"], "Sinistres payés Ant.": r["paid_prior_ytd"],
            "Sinistres Payés net des recours": r["paid_current_ytd"] + r["paid_prior_ytd"] - r["recourse_current_ytd"] - r["recourse_prior_ytd"],
            "Commissions": r["commission_ytd"],
            "REC Ouverture": r["upr_open"], "REC Clôture": r["upr_close"], "Variation de REC": r["upr_variation"],
            "IBNR Ouverture Per.": r["ibnr_open_current"], "IBNR Clôture Per.": r["ibnr_close_current"],
            "IBNR Ouverture Ant.": r["ibnr_open_prior"], "IBNR Clôture Ant.": r["ibnr_close_prior"],
            "SAP Ouverture Per.": r["case_open_current"], "SAP Clôture Per.": r["case_close_current"],
            "SAP Ouverture Ant.": r["case_open_prior"], "SAP Clôture Ant.": r["case_close_prior"],
            "S/P de l'exercice": r["sp_exercice"], "S/P global": r["sp_global"], "taux commissions": r["commission_rate"],
        }
        for line, val in vals.items():
            rows.append({"period":r["period"],"branch":r["branch"],"line":line,"value":val})
    return pd.DataFrame(rows)


def make_legacy_reass_block(reass: pd.DataFrame) -> pd.DataFrame:
    if reass.empty:
        return pd.DataFrame(columns=["period","branch","line","value"])
    rows=[]
    for _, r in reass.iterrows():
        vals = {
            "Primes Emises": r["ceded_premium_ytd"],
            "Commissions": r["reass_commission_ytd"],
            "Sinistres payés Per.": r["recovered_paid_current_ytd"],
            "Sinistres payés Ant.": r["recovered_paid_prior_ytd"],
            "REC Ouverture": r["ceded_upr_open"], "REC Clôture": r["ceded_upr_close"], "Variation de REC": r["ceded_upr_variation"],
            "SAP Ouverture Per.": r["recoverable_case_open_current"], "SAP Clôture Per.": r["recoverable_case_close_current"],
            "SAP Ouverture Ant.": r["recoverable_case_open_prior"], "SAP Clôture Ant.": r["recoverable_case_close_prior"],
            "IBNR Ouverture Per.": r["recoverable_ibnr_open_current"], "IBNR Clôture Per.": r["recoverable_ibnr_close_current"],
            "IBNR Ouverture Ant.": r["recoverable_ibnr_open_prior"], "IBNR Clôture Ant.": r["recoverable_ibnr_close_prior"],
            "Taux de cession primes": r["cession_rate"],
            "Taux récupération sinistres Per.": r["claim_recovery_current"],
            "Taux récupération sinistres Ant.": r["claim_recovery_prior"],
            "Taux commission réassurance": r["reass_commission_rate"],
        }
        for line, val in vals.items():
            rows.append({"period":r["period"],"branch":r["branch"],"line":line,"value":val})
    return pd.DataFrame(rows)
