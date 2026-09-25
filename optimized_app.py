"""Primary Gradio workflow for the constrained forecast engine."""
from __future__ import annotations

from pathlib import Path
import tempfile

import gradio as gr
import pandas as pd
import plotly.graph_objects as go
from openpyxl import load_workbook

from model import BRANCHES
from exporter import export_optimized_forecast
from optimized_forecast import (
    RATE_FIELDS, ForecastInputError, run_optimized_forecast,
)
from workbook_adapter import (
    parse_legacy_workbook, _block_starts, _infer_year, _extract_sheet,
    DIRECT_ROWS, REASS_ROWS,
)


MONTHS = [
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet",
    "Août", "Septembre", "Octobre", "Novembre", "Décembre",
]
TARGET_FIELDS = ("gwp_end", "sp_ifrs_current", "sp_ifrs_global",
                 "sp_global", "sp_net", "sp_min", "sp_max")
EDIT_FIELDS = (
    "gwp_ytd", "incurred_current_ytd", "incurred_prior_ytd",
    "paid_current_ytd", "paid_prior_ytd",
)


def premiums_grid():
    return pd.DataFrame({"Mois": MONTHS, **{b: [None]*12 for b in BRANCHES}})


def rates_grid():
    return pd.DataFrame([{"branch": b, **{f: None for f in RATE_FIELDS}}
                         for b in BRANCHES])


def targets_grid():
    return pd.DataFrame([{"branch": b, **{f: None for f in TARGET_FIELDS}}
                         for b in [*BRANCHES, "CONSOLIDATION"]])


def blank_exceptions():
    return pd.DataFrame(columns=[
        "period", "branch", *RATE_FIELDS, "sp_ifrs_current", "sp_ifrs_global"])


def blank_locks():
    return pd.DataFrame(columns=["period", "branch", "field", "mode", "value"])


def load_actuals(path, projection_year, last_closed_month):
    if not path:
        raise gr.Error("Importez un classeur contenant Direct Local et Reass Local.")
    direct, reass, _, _, _, messages = parse_legacy_workbook(str(path))
    if direct.empty or reass.empty:
        raise gr.Error("Les blocs mensuels Direct Local et Reass Local sont requis.")
    dy = set(pd.to_datetime(direct.period).dt.year)
    ry = set(pd.to_datetime(reass.period).dt.year)
    if dy != ry:
        raise gr.Error(
            f"Calendrier incohérent : Direct {sorted(dy)}, Réassurance {sorted(ry)}.")
    year = int(projection_year)
    closed = int(last_closed_month)
    if closed:
        direct = direct[(direct.period.dt.year == year) &
                        (direct.period.dt.month <= closed)].copy()
        reass = reass[(reass.period.dt.year == year) &
                      (reass.period.dt.month <= closed)].copy()
        if direct.period.dt.month.nunique() != closed or reass.period.dt.month.nunique() != closed:
            raise gr.Error("Le classeur ne contient pas tous les mois réalisés indiqués.")
    else:
        direct = direct[(direct.period.dt.year == year-1) &
                        (direct.period.dt.month == 12)].copy()
        reass = reass[(reass.period.dt.year == year-1) &
                      (reass.period.dt.month == 12)].copy()
        if direct.empty or reass.empty:
            raise gr.Error("Sans réalisé N, la clôture de décembre N−1 est requise.")
    local = direct.merge(
        reass[["period", "branch", "ceded_upr_close"]],
        on=["period", "branch"], how="left")
    book = load_workbook(path, data_only=True, read_only=False)
    ifrs = pd.DataFrame()
    if "Direct" in book and "Reass" in book:
        wd, wr = book["Direct"], book["Reass"]
        direct_ifrs = _extract_sheet(
            wd, _block_starts(wd), _infer_year(wd, _block_starts(wd)),
            DIRECT_ROWS, "direct")
        reass_ifrs = _extract_sheet(
            wr, _block_starts(wr), _infer_year(wr, _block_starts(wr)),
            REASS_ROWS, "reass")
        if not direct_ifrs.empty and not reass_ifrs.empty:
            if closed:
                direct_ifrs = direct_ifrs[
                    (direct_ifrs.period.dt.year == year) &
                    (direct_ifrs.period.dt.month <= closed)]
                reass_ifrs = reass_ifrs[
                    (reass_ifrs.period.dt.year == year) &
                    (reass_ifrs.period.dt.month <= closed)]
            else:
                direct_ifrs = direct_ifrs[
                    (direct_ifrs.period.dt.year == year-1) &
                    (direct_ifrs.period.dt.month == 12)]
                reass_ifrs = reass_ifrs[
                    (reass_ifrs.period.dt.year == year-1) &
                    (reass_ifrs.period.dt.month == 12)]
            ifrs = direct_ifrs.merge(
                reass_ifrs[["period", "branch", "ceded_upr_close"]],
                on=["period", "branch"], how="left")
    suggested = suggest_rates(direct, reass, local, ifrs)
    return direct, reass, local, ifrs, suggested, "\n".join(messages)


def _ratio(numerator, denominator):
    a, b = number(numerator), number(denominator)
    return None if a is None or b is None or abs(b) < 1e-9 else 100*a/b


def number(value):
    try:
        x = float(str(value).replace("\u00a0", "").replace(" ", "").replace(",", "."))
        return x if pd.notna(x) else None
    except (TypeError, ValueError):
        return None


def suggest_rates(direct, reass, local, ifrs):
    rows = []
    for branch in BRANCHES:
        d = direct[direct.branch == branch].sort_values("period")
        r = reass[reass.branch == branch].sort_values("period")
        rec = {"branch": branch, **{f: None for f in RATE_FIELDS}}
        if d.empty or r.empty:
            rows.append(rec)
            continue
        x, z = d.iloc[-1], r.iloc[-1]
        earned = number(x.get("earned_premium_ytd"))
        if earned is None:
            revenue = (x.gwp_ytd-x.pap_open+x.pap_close-
                       x.pane_open+x.pane_close)
            earned = revenue+x.upr_open-x.upr_close
        charge_cur = (x.paid_current_ytd-x.recourse_current_ytd+
                      x.case_close_current+x.ibnr_close_current-
                      x.case_open_current-x.ibnr_open_current)
        charge_prior = (x.paid_prior_ytd-x.recourse_prior_ytd+
                        x.case_close_prior+x.ibnr_close_prior-
                        x.case_open_prior-x.ibnr_open_prior)
        recovered_cur = (z.recovered_paid_current_ytd+
                         z.recoverable_case_close_current+
                         z.recoverable_ibnr_close_current-
                         z.recoverable_case_open_current-
                         z.recoverable_ibnr_open_current)
        recovered_prior = (z.recovered_paid_prior_ytd+
                           z.recoverable_case_close_prior+
                           z.recoverable_ibnr_close_prior-
                           z.recoverable_case_open_prior-
                           z.recoverable_ibnr_open_prior)
        rec.update({
            "sp_current": _ratio(charge_cur, earned),
            "sp_global": _ratio(charge_cur+charge_prior, earned),
            "settlement_current": _ratio(x.paid_current_ytd, charge_cur),
            "settlement_prior": _ratio(
                x.paid_prior_ytd, x.case_open_prior+x.ibnr_open_prior),
            "ibnr_share_current": _ratio(
                x.ibnr_close_current, x.case_close_current+x.ibnr_close_current),
            "ibnr_share_prior": _ratio(
                x.ibnr_close_prior, x.case_close_prior+x.ibnr_close_prior),
            "recourse_current": _ratio(x.recourse_current_ytd, x.paid_current_ytd),
            "recourse_prior": _ratio(x.recourse_prior_ytd, x.paid_prior_ytd),
            "rec_direct": _ratio(x.upr_close, x.gwp_ytd),
            "commission": _ratio(x.commission_ytd, x.gwp_ytd),
            "cession": _ratio(z.ceded_premium_ytd, x.gwp_ytd),
            "recovery_current": _ratio(recovered_cur, charge_cur),
            "recovery_prior": _ratio(recovered_prior, charge_prior),
            "rec_reass": _ratio(z.ceded_upr_close, z.ceded_premium_ytd),
            "reass_commission": _ratio(z.reass_commission_ytd, z.ceded_premium_ytd),
        })
        lf = local[local.branch == branch].sort_values("period")
        iff = ifrs[ifrs.branch == branch].sort_values("period") if not ifrs.empty else pd.DataFrame()
        if not lf.empty and not iff.empty:
            pair = lf.merge(
                iff[["period", "ibnr_close_current", "ceded_upr_close"]],
                on="period", suffixes=("_local", "_ifrs"))
            if not pair.empty:
                ibnr = (pair.ibnr_close_current_ifrs/
                        pair.ibnr_close_current_local.replace(0, pd.NA)).dropna()
                rec100 = (pair.ceded_upr_close_ifrs/
                          pair.ceded_upr_close_local.replace(0, pd.NA)).dropna()
                rec["ifrs_ibnr_factor"] = float(ibnr.median()) if not ibnr.empty else None
                rec["ifrs_rec_factor"] = float(rec100.median()) if not rec100.empty else None
        rows.append(rec)
    return pd.DataFrame(rows)


def history_long(grid, year):
    df = pd.DataFrame(grid)
    rows = []
    for m in range(1, 13):
        for branch in BRANCHES:
            value = df.iloc[m-1][branch]
            if pd.notna(value) and str(value).strip():
                parsed = number(value)
                if parsed is None:
                    raise gr.Error(f"{branch} {MONTHS[m-1]} : prime non numérique.")
                rows.append({"period": f"{year}-{m:02d}", "branch": branch,
                             "gwp_ytd": parsed})
    return pd.DataFrame(rows, columns=["period", "branch", "gwp_ytd"])


def load_premium_history(path):
    if not path:
        return pd.DataFrame(columns=["period", "branch", "gwp_ytd"]), ""
    name = str(path).lower()
    data = pd.read_csv(path) if name.endswith(".csv") else pd.read_excel(path)
    needed = {"period", "branch", "gwp_ytd"}
    if not needed.issubset(data.columns):
        raise gr.Error("Historique additionnel : colonnes period, branch, gwp_ytd requises.")
    data = data[list(needed)].copy()
    data["period"] = data.period.map(lambda x: str(pd.Period(x, freq="M")))
    return data, f"{len(data)} observations historiques chargées."


def _display(df):
    return pd.DataFrame(df).round(3)


def calculate(year, premiums, extra_history, rates, targets, exceptions, locks,
              actual_direct, actual_reass, history_local, history_ifrs):
    try:
        h = pd.concat([pd.DataFrame(extra_history),
                       history_long(premiums, int(year)-1)], ignore_index=True)
        h = h.drop_duplicates(["period", "branch"], keep="last")
        result = run_optimized_forecast(
            h, pd.DataFrame(rates), pd.DataFrame(actual_direct),
            pd.DataFrame(actual_reass), pd.DataFrame(targets),
            pd.DataFrame(exceptions), pd.DataFrame(locks),
            history_local=pd.DataFrame(history_local),
            history_ifrs=pd.DataFrame(history_ifrs),
            projection_year=int(year),
        )
        with tempfile.NamedTemporaryFile(
            prefix="projection_optimisee_", suffix=".xlsx", delete=False
        ) as handle:
            output = Path(handle.name)
        export_optimized_forecast(output, result, {
            "history_premiums": h,
            "annual_targets": pd.DataFrame(targets),
            "locks": pd.DataFrame(locks),
        })
        return (
            f"Projection calculée. {len(result.diagnostics)} diagnostic(s).",
            result, _display(result.direct), _display(result.reass),
            _display(result.direct_ifrs), _display(result.reass_ifrs),
            _display(result.cpc_local), _display(result.cpc_ifrs),
            _display(result.diagnostics), str(output),
        )
    except (ForecastInputError, ValueError, KeyError) as exc:
        raise gr.Error(str(exc)) from exc


def chart(result, premium_grid, extra_history, actual_direct, targets,
          year, branch, field, basis):
    fig = go.Figure()
    if result is None:
        return fig
    h = pd.concat([pd.DataFrame(extra_history),
                   history_long(premium_grid, int(year)-1)], ignore_index=True)
    h = h.drop_duplicates(["period", "branch"], keep="last")
    if field == "gwp_ytd":
        for old_year, old in h[h.branch == branch].groupby(h.period.str[:4]):
            old = old.sort_values("period")
            fig.add_trace(go.Scatter(
                x=old.period.str[5:7].astype(int), y=old.gwp_ytd,
                name=f"{old_year} historique", mode="lines+markers"))
    df = {
        ("Direct", "Local"): result.direct,
        ("Direct", "IFRS"): result.direct_ifrs,
        ("Réassurance", "Local"): result.reass,
        ("Réassurance", "IFRS"): result.reass_ifrs,
    }[(("Réassurance" if field.startswith("ceded_") or
          field.startswith("recovered_") else "Direct"), basis)]
    if field not in df:
        return fig
    part = df[df.branch == branch].sort_values("period")
    actual = pd.DataFrame(actual_direct)
    closed = 0
    if not actual.empty and "period" in actual:
        closed = max(
            [int(str(pd.Period(p, freq="M"))[5:7])
             for p in actual.period if str(pd.Period(p, freq="M"))[:4] == str(int(year))],
            default=0)
    part = part.copy()
    part["m"] = part.period.dt.month
    for name, segment, dash in [
        (f"{year} réalisé", part[part.m <= closed], "solid"),
        (f"{year} projeté {basis}", part[part.m > closed], "dash"),
    ]:
        if not segment.empty:
            fig.add_trace(go.Scatter(x=segment.m, y=segment[field],
                                     name=name, mode="lines+markers",
                                     line={"dash": dash}))
    if field == "gwp_ytd":
        t = pd.DataFrame(targets)
        target = t[t.branch == branch]
        if not target.empty and pd.notna(target.iloc[0].get("gwp_end")):
            fig.add_trace(go.Scatter(
                x=[12], y=[float(target.iloc[0].gwp_end)],
                name="Cible décembre", mode="markers",
                marker={"symbol": "diamond", "size": 12}))
    fig.update_layout(template="plotly_white", title=f"{field} · {branch}",
                      xaxis_title="Mois", xaxis={"tickmode": "array",
                      "tickvals": list(range(1, 13)), "ticktext": MONTHS},
                      yaxis_title="F CFA",
                      hovermode="x unified")
    return fig


def build_app():
    with gr.Blocks(title="Projection technique assurance") as demo:
        gr.Markdown("# Projection technique assurance\nOptimisation mensuelle Direct, Réassurance et CPC. Les valeurs réalisées restent fixes.")
        result_state = gr.State(None)
        direct_state = gr.State(pd.DataFrame())
        reass_state = gr.State(pd.DataFrame())
        local_history_state = gr.State(pd.DataFrame())
        ifrs_history_state = gr.State(pd.DataFrame())
        extra_history_state = gr.State(pd.DataFrame(columns=["period", "branch", "gwp_ytd"]))
        with gr.Tab("1 · Données"):
            year = gr.Number(value=2027, precision=0, label="Année projetée")
            last_closed_month = gr.Slider(
                0, 11, value=0, step=1,
                label="Dernier mois N réalisé (0 = aucun ; 1 = janvier)")
            gr.Markdown("Renseignez les primes émises cumulées de N−1. Importez un classeur mensuel contenant Direct Local et Reass Local : les derniers mois N servent de réalisés ; si aucun mois N n'existe, décembre N−1 sert de départ.")
            premium = gr.Dataframe(value=premiums_grid(), type="pandas",
                                   interactive=True, label="Primes N−1 cumulées")
            extra_history_file = gr.File(
                label="Années additionnelles facultatives (CSV/XLSX : period, branch, gwp_ytd)",
                file_types=[".csv", ".xlsx"], type="filepath")
            load_history_button = gr.Button("Charger l'historique additionnel")
            history_info = gr.Markdown()
            actual_file = gr.File(label="Classeur des réalisés ou clôture N−1",
                                  file_types=[".xlsx"], type="filepath")
            import_button = gr.Button("Charger les réalisés")
            import_info = gr.Markdown()
        with gr.Tab("2 · Taux et cibles"):
            gr.Markdown("Taux en %, facteurs IFRS en multiples. Les cellules vides requises sont signalées. Un taux par branche s'applique à tous les mois futurs ; les exceptions sont facultatives.")
            annual_rates = gr.Dataframe(value=rates_grid(), type="pandas",
                                        interactive=True, label="Taux annuels par branche")
            target = gr.Dataframe(value=targets_grid(), type="pandas",
                                  interactive=True, label="Cibles annuelles et IFRS")
            exceptions = gr.Dataframe(value=blank_exceptions(), type="pandas",
                                      interactive=True, row_count=0,
                                      label="Exceptions mensuelles")
        with gr.Tab("3 · Corrections"):
            gr.Markdown("Ajoutez un verrou sur un mois futur. Modes : cumul, increment, taux. Les mois réalisés ne peuvent pas être modifiés.")
            locks = gr.Dataframe(value=blank_locks(), type="pandas",
                                 interactive=True, row_count=0,
                                 label="Points imposés")
            run = gr.Button("Optimiser les mois restants", variant="primary")
            status = gr.Markdown()
        with gr.Tab("4 · Résultats"):
            with gr.Row():
                branch = gr.Dropdown(BRANCHES, value=BRANCHES[0], label="Branche")
                field = gr.Dropdown(
                    ["gwp_ytd", "earned_premium_ytd", "incurred_current_ytd",
                     "incurred_prior_ytd", "case_close_current", "ibnr_close_current",
                     "ceded_premium_ytd", "recovered_incurred_current_ytd"],
                    value="gwp_ytd", label="Ligne")
                basis = gr.Radio(["Local", "IFRS"], value="Local", label="Référentiel")
            plot = gr.Plot(label="Historique et projection")
            with gr.Tabs():
                with gr.Tab("Direct Local"):
                    direct_out = gr.Dataframe(interactive=False)
                with gr.Tab("Reass Local"):
                    reass_out = gr.Dataframe(interactive=False)
                with gr.Tab("Direct IFRS"):
                    direct_ifrs_out = gr.Dataframe(interactive=False)
                with gr.Tab("Reass IFRS"):
                    reass_ifrs_out = gr.Dataframe(interactive=False)
                with gr.Tab("CPC Local"):
                    cpc_out = gr.Dataframe(interactive=False)
                with gr.Tab("CPC IFRS"):
                    cpc_ifrs_out = gr.Dataframe(interactive=False)
            controls = gr.Dataframe(interactive=False, label="Diagnostics")
            file_out = gr.File(label="Classeur optimisé")
        import_button.click(
            load_actuals, inputs=[actual_file, year, last_closed_month],
            outputs=[direct_state, reass_state, local_history_state,
                     ifrs_history_state, annual_rates, import_info])
        load_history_button.click(
            load_premium_history, inputs=[extra_history_file],
            outputs=[extra_history_state, history_info])
        event = run.click(
            calculate,
            inputs=[year, premium, extra_history_state, annual_rates,
                    target, exceptions, locks,
                    direct_state, reass_state, local_history_state,
                    ifrs_history_state],
            outputs=[status, result_state, direct_out, reass_out,
                     direct_ifrs_out, reass_ifrs_out, cpc_out, cpc_ifrs_out,
                     controls, file_out])
        chart_inputs = [result_state, premium, extra_history_state, direct_state,
                        target, year, branch, field, basis]
        event.success(chart, inputs=chart_inputs, outputs=[plot])
        for component in (branch, field, basis):
            component.change(chart, inputs=chart_inputs, outputs=[plot])
    return demo
