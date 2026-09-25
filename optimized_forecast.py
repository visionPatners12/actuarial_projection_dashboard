"""Constrained, rate driven projection for the existing Gradio application."""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd
from scipy.optimize import linprog, minimize

from model import BRANCHES, _summary


RATE_FIELDS = (
    "sp_current", "sp_global", "settlement_current", "settlement_prior",
    "ibnr_share_current", "ibnr_share_prior", "recourse_current",
    "recourse_prior", "rec_direct", "commission", "cession",
    "recovery_current", "recovery_prior", "rec_reass", "reass_commission",
    "ifrs_ibnr_factor", "ifrs_rec_factor",
)
REQUIRED = (
    "sp_current", "sp_global", "settlement_current", "ibnr_share_current",
    "recourse_current", "recourse_prior", "rec_direct", "commission",
    "cession", "recovery_current", "rec_reass", "reass_commission",
    "ifrs_ibnr_factor", "ifrs_rec_factor",
)
DIRECT_OPEN = (
    "upr_open", "case_open_current", "case_open_prior",
    "ibnr_open_current", "ibnr_open_prior", "pap_open", "pap_close",
    "pane_open", "pane_close",
)
REASS_OPEN = (
    "ceded_upr_open", "recoverable_case_open_current",
    "recoverable_case_open_prior", "recoverable_ibnr_open_current",
    "recoverable_ibnr_open_prior",
)
LOCK_FIELDS = {
    "gwp_ytd", "incurred_current_ytd", "incurred_prior_ytd",
    "paid_current_ytd", "paid_prior_ytd",
}


class ForecastInputError(ValueError):
    pass


@dataclass
class ForecastResult:
    direct: pd.DataFrame
    reass: pd.DataFrame
    direct_ifrs: pd.DataFrame
    reass_ifrs: pd.DataFrame
    cpc_local: pd.DataFrame
    cpc_ifrs: pd.DataFrame
    diagnostics: pd.DataFrame
    applied_rates: pd.DataFrame


def number(value):
    try:
        x = float(str(value).replace("\u00a0", "").replace(" ", "").replace(",", "."))
        return x if np.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def month(value):
    return str(pd.Period(value, freq="M"))


def qp(prior, equalities=(), lower=None, upper=None, smooth=False):
    """Lexicographic LP/QP: exact targets, minimum L1 change, then smoothing.

    CVXPY/OSQP is the production path. SciPy is the equivalent portable path
    for environments where the optional CVXPY wheel is unavailable.
    """
    prior = np.asarray(prior, dtype=float)
    scale = max(1.0, float(np.max(np.abs(prior))))
    p = prior / scale
    n = len(p)
    lb = np.zeros(n) if lower is None else np.asarray(lower, dtype=float) / scale
    ub = None if upper is None else np.asarray(upper, dtype=float) / scale
    eq = [(np.asarray(a, dtype=float), float(b) / scale) for a, b in equalities]
    d2 = np.diff(np.eye(n), n=2, axis=0) if n >= 3 else np.zeros((0, n))
    try:
        import cvxpy as cp
        x = cp.Variable(n)
        slack = cp.Variable(n, nonneg=True)
        constraints = [
            x >= lb, slack >= x-p, slack >= p-x,
        ] + [a @ x == b for a, b in eq]
        if ub is not None:
            constraints += [x[i] <= ub[i] for i in range(n) if np.isfinite(ub[i])]
        first = cp.Problem(cp.Minimize(cp.sum(slack)), constraints)
        first.solve(solver=cp.OSQP, warm_start=True, eps_abs=1e-8, eps_rel=1e-8)
        if first.status not in (cp.OPTIMAL, cp.OPTIMAL_INACCURATE):
            raise ForecastInputError(f"cibles incompatibles : {first.status}")
        optimum = float(first.value)
        constraints.append(cp.sum(slack) <= optimum+1e-6*max(1.0, optimum))
        second_obj = (cp.sum_squares(d2 @ x) if smooth and len(d2)
                      else cp.sum_squares(x-p))
        second = cp.Problem(cp.Minimize(second_obj), constraints)
        second.solve(solver=cp.OSQP, warm_start=True, eps_abs=1e-8, eps_rel=1e-8)
        if second.status not in (cp.OPTIMAL, cp.OPTIMAL_INACCURATE):
            raise ForecastInputError(f"lissage impossible : {second.status}")
        value = np.asarray(x.value).reshape(-1)
    except ImportError:
        eye = np.eye(n)
        a_ub = np.vstack([
            np.hstack([eye, -eye]),
            np.hstack([-eye, -eye]),
        ])
        b_ub = np.r_[p, -p]
        a_eq = (np.vstack([np.r_[a, np.zeros(n)] for a, _ in eq])
                if eq else None)
        b_eq = np.array([b for _, b in eq]) if eq else None
        bounds = [
            (lb[i], None if ub is None or not np.isfinite(ub[i]) else ub[i])
            for i in range(n)
        ] + [(0.0, None)]*n
        first = linprog(
            np.r_[np.zeros(n), np.ones(n)], A_ub=a_ub, b_ub=b_ub,
            A_eq=a_eq, b_eq=b_eq, bounds=bounds, method="highs")
        if not first.success:
            raise ForecastInputError(f"cibles incompatibles : {first.message}")
        optimum = float(first.fun)
        a_second = np.vstack([a_ub, np.r_[np.zeros(n), np.ones(n)]])
        b_second = np.r_[b_ub, optimum+1e-6*max(1.0, optimum)]
        constraints = [
            {"type": "ineq",
             "fun": lambda z: b_second-a_second @ z,
             "jac": lambda z: -a_second},
        ]
        if a_eq is not None:
            constraints.append({
                "type": "eq", "fun": lambda z: a_eq @ z-b_eq,
                "jac": lambda z: a_eq,
            })
        def fun(z):
            x0 = z[:n]
            e = d2 @ x0 if smooth and len(d2) else x0-p
            return float(e @ e)
        def jac(z):
            x0 = z[:n]
            gradient = (2*d2.T @ (d2 @ x0) if smooth and len(d2)
                        else 2*(x0-p))
            return np.r_[gradient, np.zeros(n)]
        second = minimize(
            fun, first.x, jac=jac, bounds=bounds, constraints=constraints,
            method="SLSQP", options={"ftol": 1e-12, "maxiter": 2000})
        if not second.success:
            raise ForecastInputError(f"lissage impossible : {second.message}")
        value = second.x[:n]
    answer = value*scale
    if np.any(answer < lb*scale-0.01):
        raise ForecastInputError("solution négative")
    if ub is not None and np.any(answer > ub*scale+0.01):
        raise ForecastInputError("solution dépasse une borne métier")
    for a, b in equalities:
        if not np.isclose(np.asarray(a) @ answer, b, rtol=1e-7,
                          atol=max(0.01, scale*1e-7)):
            raise ForecastInputError("cible exacte non respectée")
    return answer


def history_ratio(numerator, denominator, branch, num_field, den_field):
    if numerator is None or denominator is None:
        return None
    n = pd.DataFrame(numerator)
    d = pd.DataFrame(denominator)
    if num_field not in n or den_field not in d:
        return None
    n = n[n.branch == branch][["period", num_field]].copy()
    d = d[d.branch == branch][["period", den_field]].copy()
    n["period"] = n.period.map(month)
    d["period"] = d.period.map(month)
    pairs = n.merge(d, on="period", suffixes=("_num", "_den"))
    if pairs.empty:
        return None
    a = pd.to_numeric(pairs.iloc[:, 1], errors="coerce")
    b = pd.to_numeric(pairs.iloc[:, 2], errors="coerce")
    ratios = (a/b.where(b.abs() > 1e-9)).replace([np.inf, -np.inf], np.nan).dropna()
    return None if ratios.empty else float(ratios.median())


def prepare_rates(table, history_local=None, history_ifrs=None):
    raw = pd.DataFrame(table).copy()
    if "branch" not in raw or raw.branch.duplicated().any():
        raise ForecastInputError("Taux annuels : branche absente ou dupliquée.")
    raw = raw.set_index("branch")
    result = {}
    for branch in BRANCHES:
        if branch not in raw.index:
            raise ForecastInputError(f"{branch} : taux annuels absents.")
        row = raw.loc[branch]
        r = {key: number(row.get(key)) for key in RATE_FIELDS}
        for key, fallback in {
            "settlement_prior": "settlement_current",
            "ibnr_share_prior": "ibnr_share_current",
            "recovery_prior": "recovery_current",
        }.items():
            if r[key] is None:
                r[key] = r[fallback]
        for key, num_field, den_field in [
            ("recourse_current", "recourse_current_ytd", "paid_current_ytd"),
            ("recourse_prior", "recourse_prior_ytd", "paid_prior_ytd"),
        ]:
            if r[key] is None:
                ratio = history_ratio(history_local, history_local, branch,
                                      num_field, den_field)
                r[key] = None if ratio is None else ratio*100
        if r["ifrs_ibnr_factor"] is None:
            r["ifrs_ibnr_factor"] = history_ratio(
                history_ifrs, history_local, branch,
                "ibnr_close_current", "ibnr_close_current")
        if r["ifrs_rec_factor"] is None:
            r["ifrs_rec_factor"] = history_ratio(
                history_ifrs, history_local, branch,
                "ceded_upr_close", "ceded_upr_close")
        missing = [key for key in REQUIRED if r[key] is None]
        if missing:
            raise ForecastInputError(f"{branch} : taux requis manquants : {', '.join(missing)}.")
        for key, value in r.items():
            if value is None:
                continue
            if key.endswith("_factor"):
                if value < 0:
                    raise ForecastInputError(f"{branch} : facteur {key} négatif.")
            elif key.startswith("sp_"):
                if value < 0:
                    raise ForecastInputError(f"{branch} : S/P {key} négatif.")
            elif not 0 <= value <= 100:
                raise ForecastInputError(f"{branch} : taux {key} hors [0 %, 100 %].")
        result[branch] = r
    return result


def effective_rates(base, exceptions, branch, period):
    r = dict(base[branch])
    if exceptions is not None and len(exceptions):
        e = pd.DataFrame(exceptions)
        e = e[(e.branch == branch) & (e.period.astype(str) == period)]
        if not e.empty:
            for key in RATE_FIELDS:
                x = number(e.iloc[-1].get(key))
                if x is not None:
                    r[key] = x
    for key, value in r.items():
        if value is None:
            continue
        if key.endswith("_factor"):
            if value < 0:
                raise ForecastInputError(f"{branch} {period} : facteur {key} négatif.")
        elif key.startswith("sp_"):
            if value < 0:
                raise ForecastInputError(f"{branch} {period} : S/P {key} négatif.")
        elif not 0 <= value <= 100:
            raise ForecastInputError(f"{branch} {period} : taux {key} hors [0 %, 100 %].")
    return {key: (value if key.endswith("_factor") else value/100.0)
            for key, value in r.items() if value is not None}


def locked_value(lock, previous):
    value = number(lock["value"])
    if value is None:
        raise ForecastInputError("Verrou sans valeur.")
    mode = lock.get("mode", "cumul")
    if mode == "cumul":
        return value
    if mode == "increment":
        return previous+value
    if mode == "taux":
        if previous == 0:
            raise ForecastInputError("Taux verrouillé sur base nulle.")
        return previous*(1+value/100.0)
    raise ForecastInputError(f"Mode de verrou inconnu : {mode}.")


def start_row(frame, branch, last_period, fields):
    found = frame[(frame.branch == branch) & (frame.period == last_period)]
    if found.empty:
        raise ForecastInputError(f"{branch} : bloc de départ {last_period} absent.")
    row = found.iloc[-1]
    missing = [field for field in fields if number(row.get(field)) is None]
    if missing:
        raise ForecastInputError(f"{branch} : valeurs de départ manquantes : {', '.join(missing)}.")
    return row


def annual_start(direct, reass, new_year):
    """Roll December closing stocks into the next year's fixed openings."""
    if not new_year:
        return direct, reass
    d = direct.copy()
    r = reass.copy()
    d["upr_open"] = direct.upr_close
    d["case_open_current"] = 0.0
    d["case_open_prior"] = direct.case_close_current+direct.case_close_prior
    d["ibnr_open_current"] = 0.0
    d["ibnr_open_prior"] = direct.ibnr_close_current+direct.ibnr_close_prior
    d["pap_open"] = d["pap_close"] = direct.pap_close
    d["pane_open"] = d["pane_close"] = direct.pane_close
    r["ceded_upr_open"] = reass.ceded_upr_close
    r["recoverable_case_open_current"] = 0.0
    r["recoverable_case_open_prior"] = (
        reass.recoverable_case_close_current+reass.recoverable_case_close_prior)
    r["recoverable_ibnr_open_current"] = 0.0
    r["recoverable_ibnr_open_prior"] = (
        reass.recoverable_ibnr_close_current+reass.recoverable_ibnr_close_prior)
    for row, fields in [
        (d, ("gwp_ytd", "paid_current_ytd", "paid_prior_ytd",
             "recourse_current_ytd", "recourse_prior_ytd", "commission_ytd")),
        (r, ("ceded_premium_ytd", "recovered_paid_current_ytd",
             "recovered_paid_prior_ytd", "reass_commission_ytd")),
    ]:
        for field in fields:
            row[field] = 0.0
    return d, r


def profile(history, branch, year):
    inc, _, _ = calibrated_profile(history, branch, year)
    return inc


def calibrated_profile(history, branch, year):
    """Learn nonnegative year weights by walk-forward backtest when possible."""
    vectors = {}
    for y in range(year-5, year+1):
        h = history[(history.branch == branch) & (history.period.str[:4] == str(y))]
        h = h.sort_values("period")
        if len(h) != 12:
            continue
        if list(h.period.str[5:7]) != [f"{m:02d}" for m in range(1, 13)]:
            continue
        inc = np.diff(np.r_[0.0, h.gwp_ytd.to_numpy(float)])
        if not np.isfinite(inc).all() or np.any(inc < -0.01):
            raise ForecastInputError(f"{branch} : primes {y} négatives ou cumul décroissant.")
        vectors[y] = inc
    if year not in vectors:
        raise ForecastInputError(f"{branch} : 12 primes mensuelles N−1 requises.")
    contiguous = [year]
    while contiguous[0]-1 in vectors:
        contiguous.insert(0, contiguous[0]-1)
    if len(contiguous) < 3:
        return vectors[year], {year: 1.0}, None
    k = min(3, len(contiguous)-1)
    xfolds, yfolds = [], []
    for target_year in contiguous[k:]:
        predecessors = [vectors[target_year-lag] for lag in range(1, k+1)]
        xfolds.append(np.column_stack(predecessors))
        yfolds.append(vectors[target_year])
    x = np.vstack(xfolds)
    y = np.concatenate(yfolds)
    norm = max(1.0, float(np.max(np.abs(y))))
    x, y = x/norm, y/norm
    def objective(w):
        error = x @ w-y
        return float(error @ error)
    def gradient(w):
        return 2*x.T @ (x @ w-y)
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w)-1.0,
                    "jac": lambda w: np.ones_like(w)}]
    fit = minimize(objective, np.ones(k)/k, jac=gradient,
                   bounds=[(0.0, 1.0)]*k, constraints=constraints,
                   method="SLSQP", options={"ftol": 1e-12})
    if not fit.success:
        raise ForecastInputError(f"{branch} : calibration historique impossible.")
    weights = {year-lag: float(fit.x[lag-1]) for lag in range(1, k+1)}
    prediction = sum(vectors[y]*weight for y, weight in weights.items())
    error = float(np.mean(np.abs(x @ fit.x-y))*norm)
    return prediction, weights, error


def _as_actual(frame, kind, year):
    """Retain supplied closed months and calculate display fields from stocks."""
    d = frame[frame.period.str[:4] == str(year)].copy()
    if d.empty:
        return d
    d["period"] = d.period.map(lambda x: pd.Period(x).to_timestamp("M"))
    d = d.sort_values(["branch", "period"]).reset_index(drop=True)
    if kind == "direct":
        d["revenue"] = d.gwp_ytd-d.pap_open+d.pap_close-d.pane_open+d.pane_close
        d["earned_premium_ytd"] = d.revenue+d.upr_open-d.upr_close
        d["incurred_current_ytd"] = (
            d.paid_current_ytd-d.recourse_current_ytd+
            d.case_close_current+d.ibnr_close_current-
            d.case_open_current-d.ibnr_open_current)
        d["incurred_prior_ytd"] = (
            d.paid_prior_ytd-d.recourse_prior_ytd+
            d.case_close_prior+d.ibnr_close_prior-
            d.case_open_prior-d.ibnr_open_prior)
        d["sp_exercice"] = d.incurred_current_ytd/d.earned_premium_ytd.replace(0, np.nan)
        d["sp_global"] = (d.incurred_current_ytd+d.incurred_prior_ytd)/d.earned_premium_ytd.replace(0, np.nan)
        d["commission_rate_written"] = d.commission_ytd/d.gwp_ytd.replace(0, np.nan)
        pairs = [
            ("gwp_ytd", "gwp_increment"),
            ("earned_premium_ytd", "earned_premium_increment"),
            ("commission_ytd", "commission_increment"),
            ("incurred_current_ytd", "incurred_current_increment"),
            ("incurred_prior_ytd", "incurred_prior_increment"),
        ]
    else:
        d["ceded_earned_premium_ytd"] = d.ceded_premium_ytd+d.ceded_upr_open-d.ceded_upr_close
        d["recovered_incurred_current_ytd"] = (
            d.recovered_paid_current_ytd+d.recoverable_case_close_current+
            d.recoverable_ibnr_close_current-d.recoverable_case_open_current-
            d.recoverable_ibnr_open_current)
        d["recovered_incurred_prior_ytd"] = (
            d.recovered_paid_prior_ytd+d.recoverable_case_close_prior+
            d.recoverable_ibnr_close_prior-d.recoverable_case_open_prior-
            d.recoverable_ibnr_open_prior)
        pairs = [
            ("ceded_premium_ytd", "ceded_premium_increment"),
            ("ceded_earned_premium_ytd", "ceded_earned_premium_increment"),
            ("reass_commission_ytd", "reass_commission_increment"),
            ("recovered_incurred_current_ytd", "recovered_incurred_current_increment"),
            ("recovered_incurred_prior_ytd", "recovered_incurred_prior_increment"),
        ]
    for field, inc_field in pairs:
        d[inc_field] = d.groupby("branch")[field].diff().fillna(d[field])
    return d


def _recompute_increments(frame, fields):
    frame = frame.sort_values(["branch", "period"]).reset_index(drop=True)
    for field, inc_field in fields:
        frame[inc_field] = frame.groupby("branch")[field].diff().fillna(frame[field])
    return frame


def historical_sp_bounds(history_local, branch):
    if history_local is None or len(history_local) == 0:
        return None
    h = pd.DataFrame(history_local)
    fields = {
        "gwp_ytd", "upr_open", "upr_close", "paid_current_ytd",
        "paid_prior_ytd", "recourse_current_ytd", "recourse_prior_ytd",
        "case_close_current", "case_close_prior", "ibnr_close_current",
        "ibnr_close_prior", "case_open_current", "case_open_prior",
        "ibnr_open_current", "ibnr_open_prior",
    }
    if not fields.issubset(h.columns):
        return None
    h = h[h.branch == branch]
    if len(h) < 3:
        return None
    revenue = h.gwp_ytd-h.pap_open+h.pap_close-h.pane_open+h.pane_close
    earned = revenue+h.upr_open-h.upr_close
    charge = (
        h.paid_current_ytd+h.paid_prior_ytd-
        h.recourse_current_ytd-h.recourse_prior_ytd+
        h.case_close_current+h.case_close_prior+
        h.ibnr_close_current+h.ibnr_close_prior-
        h.case_open_current-h.case_open_prior-
        h.ibnr_open_current-h.ibnr_open_prior
    )
    ratios = (charge/earned.where(earned > 0)).replace(
        [np.inf, -np.inf], np.nan).dropna()
    if len(ratios) < 3:
        return None
    return max(0.0, float(ratios.min()*100)), float(ratios.max()*100)


def _validate_result(direct, reass, tol=0.01):
    for branch, group in direct.groupby("branch"):
        group = group.sort_values("period")
        for field in DIRECT_OPEN:
            if group[field].max()-group[field].min() > tol:
                raise ForecastInputError(f"{branch} : {field} varie pendant l'exercice.")
        for field in ("upr_open", "upr_close", "case_close_current",
                      "case_close_prior", "ibnr_close_current",
                      "ibnr_close_prior"):
            if group[field].min() < -tol:
                raise ForecastInputError(f"{branch} : {field} négatif.")
        for field in ("gwp_ytd", "paid_current_ytd", "paid_prior_ytd"):
            if (group[field].diff().dropna() < -tol).any():
                raise ForecastInputError(f"{branch} : {field} cumulé décroissant.")
        if (group.earned_premium_ytd.diff().dropna() < -tol).any():
            raise ForecastInputError(f"{branch} : primes acquises cumulées décroissantes.")
        cur = (group.paid_current_ytd-group.recourse_current_ytd+
               group.case_close_current+group.ibnr_close_current-
               group.case_open_current-group.ibnr_open_current)
        prior = (group.paid_prior_ytd-group.recourse_prior_ytd+
                 group.case_close_prior+group.ibnr_close_prior-
                 group.case_open_prior-group.ibnr_open_prior)
        if max((cur-group.incurred_current_ytd).abs().max(),
               (prior-group.incurred_prior_ytd).abs().max()) > tol:
            raise ForecastInputError(f"{branch} : identité de charge Direct rompue.")
    for branch, group in reass.groupby("branch"):
        group = group.sort_values("period")
        for field in REASS_OPEN:
            if group[field].max()-group[field].min() > tol:
                raise ForecastInputError(f"{branch} : {field} varie pendant l'exercice.")
        for field in ("ceded_upr_open", "ceded_upr_close",
                      "recoverable_case_close_current",
                      "recoverable_case_close_prior",
                      "recoverable_ibnr_close_current",
                      "recoverable_ibnr_close_prior"):
            if group[field].min() < -tol:
                raise ForecastInputError(f"{branch} : {field} négatif.")
        if (group.ceded_premium_ytd.diff().dropna() < -tol).any():
            raise ForecastInputError(f"{branch} : primes cédées cumulées décroissantes.")
        if (group.ceded_earned_premium_ytd.diff().dropna() < -tol).any():
            raise ForecastInputError(f"{branch} : primes acquises cédées décroissantes.")
        cur = (group.recovered_paid_current_ytd+
               group.recoverable_case_close_current+group.recoverable_ibnr_close_current-
               group.recoverable_case_open_current-group.recoverable_ibnr_open_current)
        prior = (group.recovered_paid_prior_ytd+
                 group.recoverable_case_close_prior+group.recoverable_ibnr_close_prior-
                 group.recoverable_case_open_prior-group.recoverable_ibnr_open_prior)
        if max((cur-group.recovered_incurred_current_ytd).abs().max(),
               (prior-group.recovered_incurred_prior_ytd).abs().max()) > tol:
            raise ForecastInputError(f"{branch} : identité de charge Réassurance rompue.")
    linked = direct.merge(reass, on=["period", "branch"], suffixes=("_direct", "_reass"))
    if (linked.ceded_premium_ytd-linked.gwp_ytd > tol).any():
        raise ForecastInputError("Primes cédées supérieures aux primes Direct.")
    if (linked.recovered_paid_current_ytd-linked.paid_current_ytd > tol).any():
        raise ForecastInputError("Paiements récupérés supérieurs aux paiements Direct.")


def run_optimized_forecast(
    history_premiums, annual_rates, actual_direct, actual_reass,
    annual_targets=None, rate_exceptions=None, locks=None,
    history_local=None, history_ifrs=None, projection_year=None,
):
    """Forecast the remaining 1-12 months in a calendar year.

    The most recent actual month, or the prior December when none are closed,
    supplies annual opening stocks. A missing stock blocks the affected branch.
    """
    if projection_year is None:
        raise ForecastInputError("Année de projection absente.")
    year = int(projection_year)
    history = pd.DataFrame(history_premiums).copy()
    ad = pd.DataFrame(actual_direct).copy()
    ar = pd.DataFrame(actual_reass).copy()
    for frame, label in [(history, "Primes N−1"), (ad, "Réalisés Direct"),
                         (ar, "Réalisés Réassurance")]:
        if not {"period", "branch"}.issubset(frame.columns):
            raise ForecastInputError(f"{label} : colonnes period/branch absentes.")
        frame["period"] = frame.period.map(month)
    actual_months = sorted(ad.loc[ad.period.str[:4] == str(year), "period"].unique())
    expected = [f"{year}-{m:02d}" for m in range(1, len(actual_months)+1)]
    if actual_months != expected:
        raise ForecastInputError("Les mois réalisés N doivent commencer en janvier et être consécutifs.")
    if actual_months and not set(actual_months).issubset(set(ar.period)):
        raise ForecastInputError("Mois réalisés Réassurance incomplets.")
    start_m = len(actual_months)+1
    if start_m > 12:
        raise ForecastInputError("L'année est entièrement réalisée.")
    future = [f"{year}-{m:02d}" for m in range(start_m, 13)]
    last = actual_months[-1] if actual_months else f"{year-1}-12"
    exceptions = (pd.DataFrame(rate_exceptions).copy() if rate_exceptions is not None
                  else pd.DataFrame(columns=["period", "branch"]))
    if not exceptions.empty:
        if not {"period", "branch"}.issubset(exceptions.columns):
            raise ForecastInputError("Exceptions : colonnes period/branch absentes.")
        exceptions = exceptions.dropna(subset=["period", "branch"])
        if not exceptions.empty:
            try:
                exceptions["period"] = exceptions.period.map(month)
            except (ValueError, TypeError) as exc:
                raise ForecastInputError("Exceptions : mois invalide.") from exc
            if exceptions.duplicated(["period", "branch"]).any():
                raise ForecastInputError("Exception en double sur un mois et une branche.")
            if not set(exceptions.period).issubset(set(future)):
                raise ForecastInputError("Une exception vise un mois réalisé ou hors horizon.")
            if not set(exceptions.branch).issubset(set(BRANCHES)):
                raise ForecastInputError("Une exception vise une branche inconnue.")
    rate_exceptions = exceptions
    rates = prepare_rates(annual_rates, history_local, history_ifrs)
    targets = pd.DataFrame(annual_targets).copy() if annual_targets is not None else pd.DataFrame(columns=["branch"])
    if not targets.empty:
        if "branch" not in targets or targets.branch.duplicated().any():
            raise ForecastInputError("Cibles : branche absente ou dupliquée.")
        targets = targets.set_index("branch")
    lockdf = pd.DataFrame(locks).copy() if locks is not None else pd.DataFrame(columns=["period", "branch", "field", "mode", "value"])
    if lockdf.empty:
        lockdf = pd.DataFrame(columns=["period", "branch", "field", "mode", "value"])
    if not lockdf.empty:
        if not {"period", "branch", "field", "mode", "value"}.issubset(lockdf.columns):
            raise ForecastInputError("Verrous : colonnes requises absentes.")
        lockdf["period"] = lockdf.period.map(month)
        if lockdf.duplicated(["period", "branch", "field"]).any():
            raise ForecastInputError("Verrou en double sur une cellule.")
        if not set(lockdf.period).issubset(set(future)):
            raise ForecastInputError("Un verrou vise un mois réalisé ou hors horizon.")
        if not set(lockdf.field).issubset(LOCK_FIELDS):
            raise ForecastInputError("Un verrou vise une ligne qui n'est pas pilotable.")
        if not set(lockdf.branch).issubset(set(BRANCHES)):
            raise ForecastInputError("Un verrou vise une branche inconnue.")
    diagnostics = []
    premiums = {}
    starts = {}
    for branch in BRANCHES:
        ds = start_row(ad, branch, last, DIRECT_OPEN+("gwp_ytd", "upr_close",
                       "paid_current_ytd", "paid_prior_ytd", "recourse_current_ytd",
                       "recourse_prior_ytd", "case_close_current", "case_close_prior",
                       "ibnr_close_current", "ibnr_close_prior", "commission_ytd"))
        rs = start_row(ar, branch, last, REASS_OPEN+("ceded_premium_ytd",
                       "ceded_upr_close", "recovered_paid_current_ytd",
                       "recovered_paid_prior_ytd", "recoverable_case_close_current",
                       "recoverable_case_close_prior", "recoverable_ibnr_close_current",
                       "recoverable_ibnr_close_prior", "reass_commission_ytd"))
        ds, rs = annual_start(ds, rs, not actual_months)
        starts[branch] = (ds, rs)
        prior_inc, weights, backtest_mae = calibrated_profile(history, branch, year-1)
        median = float(np.median(prior_inc))
        mad = float(np.median(np.abs(prior_inc-median)))
        if mad > 0:
            outliers = np.flatnonzero(np.abs(prior_inc-median) > 6*1.4826*mad)
            for pos in outliers:
                diagnostics.append({
                    "branch": branch, "period": f"{year-1}-{pos+1:02d}",
                    "severity": "Anomalie historique",
                    "message": "Incrément de primes atypique conservé dans la calibration.",
                })
        prior_to_date = prior_inc[:start_m-1].sum()
        base = float(ds.gwp_ytd) if actual_months else 0.0
        scale = base/prior_to_date if prior_to_date > 0 and actual_months else 1.0
        prior = prior_inc[start_m-1:]*scale
        t = targets.loc[branch] if branch in targets.index else pd.Series(dtype=float)
        end = number(t.get("gwp_end"))
        eq = []
        if end is not None:
            eq.append((np.ones(len(future)), end-base))
        for _, lock in lockdf[(lockdf.branch == branch) &
                              (lockdf.field == "gwp_ytd")].iterrows():
            pos = future.index(lock.period)
            value = number(lock["value"])
            if value is None:
                raise ForecastInputError(f"{branch} : verrou de prime sans valeur.")
            if lock["mode"] == "cumul":
                eq.append((np.r_[np.ones(pos+1), np.zeros(len(future)-pos-1)],
                           value-base))
            elif lock["mode"] == "increment":
                vector = np.zeros(len(future))
                vector[pos] = 1.0
                eq.append((vector, value))
            elif lock["mode"] == "taux":
                rate = value/100.0
                vector = np.zeros(len(future))
                vector[:pos] = -rate
                vector[pos] = 1.0
                eq.append((vector, rate*base))
            else:
                raise ForecastInputError(f"Mode de verrou inconnu : {lock['mode']}.")
        try:
            increments = qp(prior, eq, smooth=True)
        except ForecastInputError as exc:
            raise ForecastInputError(f"{branch} : primes : {exc}") from exc
        premiums[branch] = base+np.cumsum(increments)
        if backtest_mae is None:
            diagnostics.append({"branch": branch, "period": str(year),
                                "severity": "Calibration limitée",
                                "message": "Moins de trois exercices complets : pas de pondération interannuelle ni backtest fiable."})
        else:
            diagnostics.append({
                "branch": branch, "period": str(year),
                "severity": "Backtest",
                "message": f"Poids {weights} ; MAE mensuelle rétrospective {backtest_mae:,.0f}.",
            })

    # Gross claims are affine in earned premium when rates are fixed. Portfolio
    # December targets therefore remain linear constraints in the same QP.
    charge = {}
    for branch in BRANCHES:
        ds, _ = starts[branch]
        charge[branch] = []
        for i, per in enumerate(future):
            rt = effective_rates(rates, rate_exceptions, branch, per)
            gwp = premiums[branch][i]
            revenue = (gwp-float(ds.pap_open)+float(ds.pap_close)-
                       float(ds.pane_open)+float(ds.pane_close))
            earned = revenue+float(ds.upr_open)-gwp*rt["rec_direct"]
            if earned < -0.01:
                raise ForecastInputError(f"{branch} {per} : prime acquise négative.")
            current = earned*rt["sp_current"]
            prior = earned*(rt["sp_global"]-rt["sp_current"])
            for field in ("incurred_current_ytd", "incurred_prior_ytd"):
                found = lockdf[(lockdf.branch == branch) &
                               (lockdf.period == per) & (lockdf.field == field)]
                if found.empty:
                    continue
                if i:
                    previous = charge[branch][-1][0 if field.endswith("current_ytd") else 1]
                elif actual_months:
                    previous = (
                        float(ds.paid_current_ytd)-float(ds.recourse_current_ytd)+
                        float(ds.case_close_current)+float(ds.ibnr_close_current)-
                        float(ds.case_open_current)-float(ds.ibnr_open_current)
                        if field.endswith("current_ytd") else
                        float(ds.paid_prior_ytd)-float(ds.recourse_prior_ytd)+
                        float(ds.case_close_prior)+float(ds.ibnr_close_prior)-
                        float(ds.case_open_prior)-float(ds.ibnr_open_prior)
                    )
                else:
                    previous = 0.0
                amount = locked_value(found.iloc[-1], previous)
                if field.endswith("current_ytd"):
                    current = amount
                else:
                    prior = amount
            charge[branch].append([current, prior, earned])
    global_t = targets.loc["CONSOLIDATION"] if "CONSOLIDATION" in targets.index else pd.Series(dtype=float)
    gross_target = number(global_t.get("sp_global"))
    net_target = number(global_t.get("sp_net"))
    if gross_target is not None or net_target is not None:
        per = future[-1]
        fixed_december = set(lockdf[
            (lockdf.period == per) & (lockdf.field == "incurred_current_ytd")
        ].branch)
        adjustable = [b for b in BRANCHES
                      if b not in ("Automobile", "Santé") and b not in fixed_december]
        if not adjustable:
            raise ForecastInputError("CPC décembre : aucune branche libre pour le rééquilibrage.")
        baseline = np.array([charge[b][-1][0] for b in adjustable])
        earned_total = sum(charge[b][-1][2] for b in BRANCHES)
        gross_total = sum(sum(charge[b][-1][:2]) for b in BRANCHES)
        ceded_earned = 0.0
        recovered = 0.0
        for branch in BRANCHES:
            rt = effective_rates(rates, rate_exceptions, branch, per)
            ds, rs = starts[branch]
            ceded = premiums[branch][-1]*rt["cession"]
            ceded_earned += ceded+float(rs.ceded_upr_open)-ceded*rt["rec_reass"]
            recovered += charge[branch][-1][0]*rt["recovery_current"]+charge[branch][-1][1]*rt["recovery_prior"]
        eq = []
        if gross_target is not None:
            eq.append((np.ones(len(adjustable)),
                       baseline.sum()+earned_total*gross_target/100-gross_total))
        if net_target is not None:
            coeff = np.array([1-effective_rates(rates, rate_exceptions, b, per)["recovery_current"]
                              for b in adjustable])
            eq.append((coeff, coeff@baseline+(earned_total-ceded_earned)*net_target/100-(gross_total-recovered)))
        lower, upper = [], []
        for branch, base_charge in zip(adjustable, baseline):
            branch_target = targets.loc[branch] if branch in targets.index else pd.Series(dtype=float)
            low = number(branch_target.get("sp_min"))
            high = number(branch_target.get("sp_max"))
            if low is None or high is None:
                historical = historical_sp_bounds(history_local, branch)
                if historical is not None:
                    low = historical[0] if low is None else low
                    high = historical[1] if high is None else high
            prior = charge[branch][-1][1]
            earned = charge[branch][-1][2]
            if low is None and high is None:
                diagnostics.append({
                    "branch": branch, "period": per,
                    "severity": "Tolérance absente",
                    "message": "Aucune borne S/P N−1 fiable ; ajouter sp_min/sp_max si nécessaire.",
                })
            lower.append(max(0.0, low*earned/100-prior) if low is not None else 0.0)
            upper.append(high*earned/100-prior if high is not None else np.inf)
        if any(lo > hi for lo, hi in zip(lower, upper)):
            raise ForecastInputError("Bornes S/P des branches incompatibles.")
        try:
            adjusted = qp(baseline, eq, lower=lower, upper=upper)
        except ForecastInputError as exc:
            raise ForecastInputError(f"CPC décembre : {exc}") from exc
        for branch, amount in zip(adjustable, adjusted):
            charge[branch][-1][0] = float(amount)
        diagnostics.append({"branch": "CONSOLIDATION", "period": per,
                            "severity": "Rééquilibrage",
                            "message": f"Charges de {len(adjustable)} branche(s) libres ajustées ; Automobile et Santé conservées."})

    direct_rows, reass_rows, applied = [], [], []
    for branch in BRANCHES:
        ds, rs = starts[branch]
        prevd = ds.to_dict()
        prevr = rs.to_dict()
        for i, per in enumerate(future):
            rt = effective_rates(rates, rate_exceptions, branch, per)
            gwp = float(premiums[branch][i])
            current, prior, earned = charge[branch][i]
            paid_cur = current*rt["settlement_current"]
            start_gwp = float(ds.gwp_ytd)
            end_gwp = float(premiums[branch][-1])
            progress = ((gwp-start_gwp)/(end_gwp-start_gwp)
                        if end_gwp > start_gwp else (i+1)/len(future))
            prior_open_reserve = float(ds.case_open_prior)+float(ds.ibnr_open_prior)
            paid_prior = (float(ds.paid_prior_ytd)+
                          prior_open_reserve*rt["settlement_prior"]*progress)
            for field in ("paid_current_ytd", "paid_prior_ytd"):
                found = lockdf[(lockdf.branch == branch) &
                               (lockdf.period == per) & (lockdf.field == field)]
                if not found.empty:
                    amount = locked_value(found.iloc[-1], float(prevd.get(field, 0)))
                    if field == "paid_current_ytd":
                        paid_cur = amount
                    else:
                        paid_prior = amount
            rec_cur = paid_cur*rt["recourse_current"]
            rec_prior = paid_prior*rt["recourse_prior"]
            reserve_cur = (float(ds.case_open_current)+float(ds.ibnr_open_current)+
                           current-paid_cur+rec_cur)
            reserve_prior = (float(ds.case_open_prior)+float(ds.ibnr_open_prior)+
                             prior-paid_prior+rec_prior)
            if min(reserve_cur, reserve_prior) < -0.01:
                raise ForecastInputError(f"{branch} {per} : provision Direct négative.")
            d = {
                "period": pd.Period(per).to_timestamp("M"), "branch": branch,
                **{f: float(ds[f]) for f in DIRECT_OPEN},
                "gwp_ytd": gwp, "upr_close": gwp*rt["rec_direct"],
                "earned_premium_ytd": earned,
                "commission_ytd": gwp*rt["commission"],
                "paid_current_ytd": paid_cur, "paid_prior_ytd": paid_prior,
                "recourse_current_ytd": rec_cur, "recourse_prior_ytd": rec_prior,
                "incurred_current_ytd": current, "incurred_prior_ytd": prior,
                "ibnr_close_current": reserve_cur*rt["ibnr_share_current"],
                "ibnr_close_prior": reserve_prior*rt["ibnr_share_prior"],
                "case_close_current": reserve_cur*(1-rt["ibnr_share_current"]),
                "case_close_prior": reserve_prior*(1-rt["ibnr_share_prior"]),
                "sp_exercice": current/earned if earned else np.nan,
                "sp_global": (current+prior)/earned if earned else np.nan,
                "commission_rate_written": rt["commission"],
            }
            d["revenue"] = (gwp-d["pap_open"]+d["pap_close"]-
                            d["pane_open"]+d["pane_close"])
            direct_rows.append(d)
            ceded = gwp*rt["cession"]
            recovered_cur = current*rt["recovery_current"]
            recovered_prior = prior*rt["recovery_prior"]
            recovered_paid_cur = paid_cur*rt["recovery_current"]
            recovered_paid_prior = paid_prior*rt["recovery_prior"]
            reserve_re_cur = (float(rs.recoverable_case_open_current)+
                              float(rs.recoverable_ibnr_open_current)+
                              recovered_cur-recovered_paid_cur)
            reserve_re_prior = (float(rs.recoverable_case_open_prior)+
                                float(rs.recoverable_ibnr_open_prior)+
                                recovered_prior-recovered_paid_prior)
            if min(reserve_re_cur, reserve_re_prior) < -0.01:
                raise ForecastInputError(f"{branch} {per} : provision récupérable négative.")
            r = {
                "period": d["period"], "branch": branch,
                **{f: float(rs[f]) for f in REASS_OPEN},
                "ceded_premium_ytd": ceded,
                "ceded_upr_close": ceded*rt["rec_reass"],
                "ceded_earned_premium_ytd": ceded+float(rs.ceded_upr_open)-ceded*rt["rec_reass"],
                "reass_commission_ytd": ceded*rt["reass_commission"],
                "recovered_paid_current_ytd": recovered_paid_cur,
                "recovered_paid_prior_ytd": recovered_paid_prior,
                "recovered_incurred_current_ytd": recovered_cur,
                "recovered_incurred_prior_ytd": recovered_prior,
                "recoverable_ibnr_close_current": reserve_re_cur*rt["ibnr_share_current"],
                "recoverable_ibnr_close_prior": reserve_re_prior*rt["ibnr_share_prior"],
                "recoverable_case_close_current": reserve_re_cur*(1-rt["ibnr_share_current"]),
                "recoverable_case_close_prior": reserve_re_prior*(1-rt["ibnr_share_prior"]),
                "cession_rate": rt["cession"], "recovery_rate": rt["recovery_current"],
                "rec_cession_rate": rt["rec_reass"],
                "reass_commission_rate": rt["reass_commission"],
            }
            reass_rows.append(r)
            applied.append({"period": per, "branch": branch,
                            **{k: v if k.endswith("_factor") else v*100
                               for k, v in rt.items()}})
            prevd, prevr = d, r
    actual_d = _as_actual(ad, "direct", year)
    actual_r = _as_actual(ar, "reass", year)
    direct = pd.concat(
        ([actual_d] if not actual_d.empty else [])+[pd.DataFrame(direct_rows)],
        ignore_index=True)
    reass = pd.concat(
        ([actual_r] if not actual_r.empty else [])+[pd.DataFrame(reass_rows)],
        ignore_index=True)
    direct = _recompute_increments(direct, [
        ("gwp_ytd", "gwp_increment"),
        ("earned_premium_ytd", "earned_premium_increment"),
        ("commission_ytd", "commission_increment"),
        ("incurred_current_ytd", "incurred_current_increment"),
        ("incurred_prior_ytd", "incurred_prior_increment"),
    ])
    reass = _recompute_increments(reass, [
        ("ceded_premium_ytd", "ceded_premium_increment"),
        ("ceded_earned_premium_ytd", "ceded_earned_premium_increment"),
        ("reass_commission_ytd", "reass_commission_increment"),
        ("recovered_incurred_current_ytd", "recovered_incurred_current_increment"),
        ("recovered_incurred_prior_ytd", "recovered_incurred_prior_increment"),
    ])
    _validate_result(direct, reass)
    direct_ifrs, reass_ifrs = transform_ifrs(
        direct, reass, rates, rate_exceptions, history_local, history_ifrs,
        targets, diagnostics)
    return ForecastResult(
        direct, reass, direct_ifrs, reass_ifrs,
        _summary(direct, reass), _summary(direct_ifrs, reass_ifrs),
        pd.DataFrame(diagnostics, columns=["branch", "period", "severity", "message"]),
        pd.DataFrame(applied),
    )


def transform_ifrs(direct, reass, base_rates, exceptions, history_local,
                   history_ifrs, targets, diagnostics):
    """Apply IFRS differences to Local, preserving the same underlying flows."""
    di = direct.copy()
    ri = reass.copy()
    for branch in BRANCHES:
        ids = list(di.index[di.branch == branch])
        rids = list(ri.index[ri.branch == branch])
        if len(ids) != len(rids):
            raise ForecastInputError(f"{branch} : périodes Local Direct/Réassurance distinctes.")
        annual = effective_rates(base_rates, None, branch, month(di.at[ids[0], "period"]))
        open_factor = annual["ifrs_ibnr_factor"]
        rec_factor = annual["ifrs_rec_factor"]
        for ix, ir in zip(ids, rids):
            d = di.loc[ix]
            r = ri.loc[ir]
            per = month(d.period)
            rt = effective_rates(base_rates, exceptions, branch, per)
            for suffix in ("current", "prior"):
                di.at[ix, f"ibnr_open_{suffix}"] = d[f"ibnr_open_{suffix}"]*open_factor
                di.at[ix, f"ibnr_close_{suffix}"] = d[f"ibnr_close_{suffix}"]*rt["ifrs_ibnr_factor"]
            di.at[ix, "incurred_current_ytd"] = (
                d.paid_current_ytd-d.recourse_current_ytd+d.case_close_current+
                di.at[ix, "ibnr_close_current"]-d.case_open_current-
                di.at[ix, "ibnr_open_current"])
            di.at[ix, "incurred_prior_ytd"] = (
                d.paid_prior_ytd-d.recourse_prior_ytd+d.case_close_prior+
                di.at[ix, "ibnr_close_prior"]-d.case_open_prior-
                di.at[ix, "ibnr_open_prior"])
            monthly = pd.DataFrame(exceptions) if exceptions is not None else pd.DataFrame()
            monthly = (monthly[(monthly.branch == branch) &
                               (monthly.period.astype(str) == per)]
                       if not monthly.empty else monthly)
            annual_row = targets.loc[branch] if branch in targets.index else pd.Series(dtype=float)
            for target_field, suffix in (
                ("sp_ifrs_current", "current"),
                ("sp_ifrs_global", "prior"),
            ):
                monthly_value = number(monthly.iloc[-1].get(target_field)) if not monthly.empty else None
                annual_value = (number(annual_row.get(target_field))
                                if pd.Timestamp(d.period).month == 12 else None)
                if monthly_value is not None and annual_value is not None and abs(monthly_value-annual_value) > 1e-8:
                    raise ForecastInputError(
                        f"{branch} {per} : cibles IFRS mensuelle et annuelle contradictoires.")
                value = monthly_value if monthly_value is not None else annual_value
                if value is None:
                    continue
                earned = float(d.earned_premium_ytd)
                cur = float(di.at[ix, "incurred_current_ytd"])
                prior = float(di.at[ix, "incurred_prior_ytd"])
                requested = earned*value/100
                delta = requested-(cur if suffix == "current" else cur+prior)
                key = f"ibnr_close_{suffix}"
                theoretical = float(di.at[ix, key])
                next_ibnr = theoretical+delta
                if next_ibnr < -0.01:
                    raise ForecastInputError(
                        f"{branch} {per} : S/P IFRS demanderait un IBNR négatif.")
                di.at[ix, key] = max(0.0, next_ibnr)
                di.at[ix, f"incurred_{suffix}_ytd"] += delta
                if abs(delta) > max(0.01, abs(theoretical)*0.25):
                    diagnostics.append({
                        "branch": branch, "period": per,
                        "severity": "Alerte IFRS",
                        "message": f"{key} ajusté de {delta:,.0f} pour la cible S/P IFRS.",
                    })
            di.at[ix, "dac_open"] = d.upr_open*rec_factor*rt["commission"]
            di.at[ix, "dac_close"] = d.upr_close*rt["ifrs_rec_factor"]*rt["commission"]
            di.at[ix, "dac_variation"] = di.at[ix, "dac_open"]-di.at[ix, "dac_close"]
            di.at[ix, "rec100_open"] = d.upr_open*rec_factor
            di.at[ix, "rec100_close"] = d.upr_close*rt["ifrs_rec_factor"]
            ri.at[ir, "ceded_upr_open"] = r.ceded_upr_open*rec_factor
            ri.at[ir, "ceded_upr_close"] = r.ceded_upr_close*rt["ifrs_rec_factor"]
            ri.at[ir, "rec100_open"] = ri.at[ir, "ceded_upr_open"]
            ri.at[ir, "rec100_close"] = ri.at[ir, "ceded_upr_close"]
            ri.at[ir, "ceded_earned_premium_ytd"] = (
                r.ceded_premium_ytd+ri.at[ir, "ceded_upr_open"]-
                ri.at[ir, "ceded_upr_close"])
            ri.at[ir, "dac_open"] = ri.at[ir, "ceded_upr_open"]*rt["reass_commission"]
            ri.at[ir, "dac_close"] = ri.at[ir, "ceded_upr_close"]*rt["reass_commission"]
            ri.at[ir, "dac_variation"] = ri.at[ir, "dac_open"]-ri.at[ir, "dac_close"]
            di.at[ix, "sp_exercice"] = (
                di.at[ix, "incurred_current_ytd"]/d.earned_premium_ytd
                if d.earned_premium_ytd else np.nan)
            di.at[ix, "sp_global"] = (
                (di.at[ix, "incurred_current_ytd"]+di.at[ix, "incurred_prior_ytd"])/
                d.earned_premium_ytd if d.earned_premium_ytd else np.nan)
    di = _recompute_increments(di, [
        ("incurred_current_ytd", "incurred_current_increment"),
        ("incurred_prior_ytd", "incurred_prior_increment"),
        ("dac_variation", "dac_increment"),
    ])
    ri = _recompute_increments(ri, [
        ("ceded_earned_premium_ytd", "ceded_earned_premium_increment"),
        ("dac_variation", "dac_increment"),
    ])
    _validate_result(di, ri)
    return di, ri
