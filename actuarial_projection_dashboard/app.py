from __future__ import annotations
import tempfile
from pathlib import Path
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import gradio as gr

from model import (
    BRANCHES, empty_direct_start, empty_reass_start, empty_direct_targets, empty_reass_targets,
    default_assumptions, run_projection, make_legacy_direct_block, make_legacy_reass_block,
    DIRECT_START_COLUMNS, REASS_START_COLUMNS, DIRECT_TARGET_COLUMNS, REASS_TARGET_COLUMNS, ASSUMPTION_COLUMNS,
)
from workbook_adapter import parse_legacy_workbook
from exporter import export_projection

APP_DIR = Path(__file__).parent


def _clean_for_display(df):
    d=pd.DataFrame(df).copy()
    if "period" in d.columns:
        d["period"]=pd.to_datetime(d["period"]).dt.strftime("%Y-%m")
    return d


def import_workbook(file_path):
    if not file_path:
        return ("Aucun fichier sélectionné.", pd.DataFrame(), pd.DataFrame(), empty_direct_start(), empty_reass_start(), default_assumptions(), "2026-12", pd.DataFrame(), pd.DataFrame())
    try:
        hd, hr, sd, sr, ah, start_period, messages = parse_legacy_workbook(file_path)
        status="\n\n".join([f"- {m}" for m in messages])
        return status, hd, hr, sd, sr, ah, start_period, _clean_for_display(hd.tail(32)), _clean_for_display(hr.tail(32))
    except Exception as e:
        return f"Erreur d'import: {e}", pd.DataFrame(), pd.DataFrame(), empty_direct_start(), empty_reass_start(), default_assumptions(), "2026-12", pd.DataFrame(), pd.DataFrame()


def _build_plot(summary):
    s=pd.DataFrame(summary).copy()
    fig=go.Figure()
    if s.empty:
        fig.update_layout(title="Aucune projection")
        return fig
    s["period"]=pd.to_datetime(s["period"])
    fig.add_trace(go.Bar(x=s["period"],y=s["net_earned_premium"],name="Primes acquises nettes"))
    fig.add_trace(go.Bar(x=s["period"],y=s["net_incurred_claims"],name="Sinistres encourus nets"))
    fig.add_trace(go.Scatter(x=s["period"],y=s["technical_result_before_general_expenses"],name="Résultat technique avant FG",mode="lines+markers",yaxis="y2"))
    fig.update_layout(
        barmode="group", margin=dict(l=30,r=30,t=55,b=30),
        yaxis=dict(title="F CFA"), yaxis2=dict(title="Résultat",overlaying="y",side="right"),
        legend=dict(orientation="h",y=1.10), hovermode="x unified",
    )
    return fig


def calculate(start_direct, start_reass, target_direct, target_reass, assumptions, start_period, n_periods, target_policy, hist_d, hist_r):
    try:
        n=int(n_periods)
        if n<1 or n>120:
            raise ValueError("Le nombre de périodes doit être compris entre 1 et 120.")
        pd.Period(str(start_period),freq="M")
        d,r,s,diag,params=run_projection(
            pd.DataFrame(start_direct),pd.DataFrame(start_reass),pd.DataFrame(target_direct),pd.DataFrame(target_reass),pd.DataFrame(assumptions),
            str(start_period),n,pd.DataFrame(hist_d) if hist_d is not None else None,pd.DataFrame(hist_r) if hist_r is not None else None,target_policy
        )
        db=make_legacy_direct_block(d); rb=make_legacy_reass_block(r)
        out=Path(tempfile.gettempdir())/"projection_actuarielle.xlsx"
        export_projection(out,{
            "start_direct":pd.DataFrame(start_direct),"start_reass":pd.DataFrame(start_reass),
            "target_direct":pd.DataFrame(target_direct),"target_reass":pd.DataFrame(target_reass),"assumptions":pd.DataFrame(assumptions)
        },d,r,s,diag,params,db,rb)
        status=f"Projection calculée sur {n} période(s). {len(diag)} diagnostic(s). Les ouvertures ont été verrouillées à chaque période."
        return status,_clean_for_display(s),_clean_for_display(d),_clean_for_display(r),diag,params,_build_plot(s),str(out),d,r,s,diag,params,db,rb
    except Exception as e:
        empty=pd.DataFrame(); return f"Erreur de calcul: {e}",empty,empty,empty,empty,empty,_build_plot(empty),None,empty,empty,empty,empty,empty,empty,empty


def build_app():
    with gr.Blocks(title="Moteur de projection actuarielle") as demo:
        gr.Markdown("""
# Moteur de projection actuarielle — Direct & Réassurance
Projection mensuelle par branche avec **ouvertures toujours verrouillées**, objectifs d'atterrissage, ratios techniques et optimisation sous contraintes. Les frais généraux et produits financiers sont volontairement hors périmètre de ce MVP.
        """)
        hist_d=gr.State(pd.DataFrame()); hist_r=gr.State(pd.DataFrame())
        state_d=gr.State(pd.DataFrame()); state_r=gr.State(pd.DataFrame()); state_s=gr.State(pd.DataFrame()); state_diag=gr.State(pd.DataFrame()); state_params=gr.State(pd.DataFrame()); state_db=gr.State(pd.DataFrame()); state_rb=gr.State(pd.DataFrame())

        with gr.Tab("1. Données & ouverture"):
            gr.Markdown("**Règle structurante :** l'ouverture de chaque période vient de la clôture précédente. Elle n'est jamais modifiée par l'optimiseur.")
            with gr.Row():
                wb_file=gr.File(label="Importer le classeur actuel (.xlsx)",file_types=[".xlsx"],type="filepath")
                import_btn=gr.Button("Analyser et charger le classeur",variant="primary")
            import_status=gr.Markdown()
            with gr.Row():
                start_period=gr.Textbox(value="2026-12",label="Dernier mois observé (YYYY-MM)")
                n_periods=gr.Number(value=4,precision=0,label="Nombre de périodes à estimer")
                target_policy=gr.Radio(["Cible (recommandé)","Strict / Fixé si compatible"],value="Cible (recommandé)",label="Traitement du bloc d'atterrissage")
            with gr.Accordion("Historique détecté",open=False):
                hist_d_view=gr.Dataframe(label="Historique Direct détecté",interactive=False)
                hist_r_view=gr.Dataframe(label="Historique Réass détecté",interactive=False)
            gr.Markdown("### Bloc de départ — Direct Local")
            start_direct=gr.Dataframe(value=empty_direct_start(),headers=DIRECT_START_COLUMNS,type="pandas",interactive=True,label="Valeurs observées / saisies")
            gr.Markdown("### Bloc de départ — Reass Local")
            start_reass=gr.Dataframe(value=empty_reass_start(),headers=REASS_START_COLUMNS,type="pandas",interactive=True,label="Valeurs observées / saisies")

        with gr.Tab("2. Atterrissage & hypothèses"):
            gr.Markdown("Les cellules laissées vides dans le bloc final sont estimées. **Les ouvertures ne sont pas saisies ici** : elles sont générées à partir de la clôture précédente.")
            target_direct=gr.Dataframe(value=empty_direct_targets(),headers=DIRECT_TARGET_COLUMNS,type="pandas",interactive=True,label="Bloc final Direct — valeurs souhaitées")
            target_reass=gr.Dataframe(value=empty_reass_targets(),headers=REASS_TARGET_COLUMNS,type="pandas",interactive=True,label="Bloc final Réassurance — valeurs souhaitées")
            gr.Markdown("### Hypothèses par branche\nPour les taux, `0.55` et `55` sont tous deux compris comme 55 %. Le **taux REC** est une cible de `REC clôture / primes émises` à l’horizon : il guide le moteur sans imposer cette formule à chaque mois. Modes : **Estimé**, **Cible**, **Fixé**.")
            assumptions=gr.Dataframe(value=default_assumptions(),headers=ASSUMPTION_COLUMNS,type="pandas",interactive=True,label="Hypothèses et modes")

        with gr.Tab("3. Projection"):
            calc_btn=gr.Button("Calculer / optimiser",variant="primary")
            calc_status=gr.Markdown()
            chart=gr.Plot(label="Synthèse")
            summary=gr.Dataframe(label="Synthèse technique",interactive=False)
            with gr.Accordion("Projection Direct détaillée",open=False):
                direct_out=gr.Dataframe(interactive=False)
            with gr.Accordion("Projection Réassurance détaillée",open=False):
                reass_out=gr.Dataframe(interactive=False)
            with gr.Accordion("Paramètres effectivement calibrés",open=False):
                params_out=gr.Dataframe(interactive=False)
            with gr.Accordion("Diagnostics / incompatibilités",open=True):
                diag_out=gr.Dataframe(interactive=False)
            export_file=gr.File(label="Exporter le résultat Excel")

        import_btn.click(import_workbook,inputs=[wb_file],outputs=[import_status,hist_d,hist_r,start_direct,start_reass,assumptions,start_period,hist_d_view,hist_r_view])
        calc_btn.click(calculate,inputs=[start_direct,start_reass,target_direct,target_reass,assumptions,start_period,n_periods,target_policy,hist_d,hist_r],outputs=[calc_status,summary,direct_out,reass_out,diag_out,params_out,chart,export_file,state_d,state_r,state_s,state_diag,state_params,state_db,state_rb])
    return demo


if __name__ == "__main__":
    app=build_app()
    app.launch(server_name="127.0.0.1",server_port=7860,inbrowser=True)
