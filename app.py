from __future__ import annotations
import os
import tempfile
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go
import gradio as gr

from model import (
    BRANCHES, DIRECT_START_COLUMNS, REASS_START_COLUMNS, HYP_COLUMNS,
    CIBLES_DIRECT_COLUMNS, CIBLES_REASS_COLUMNS,
    empty_direct_start, empty_reass_start, empty_cibles_direct, empty_cibles_reass,
    build_hyp_direct, build_hyp_reass, run_projection,
)
from workbook_adapter import parse_legacy_workbook
from exporter import export_projection


def _clean(df):
    d=pd.DataFrame(df).copy()
    if "period" in d.columns:
        try: d["period"]=pd.to_datetime(d["period"]).dt.strftime("%Y-%m")
        except Exception: pass
    return d


def import_workbook(file_path):
    if not file_path:
        return ("Aucun fichier sélectionné.",pd.DataFrame(),pd.DataFrame(),empty_direct_start(),empty_reass_start(),"2026-12",pd.DataFrame(),pd.DataFrame())
    try:
        hd,hr,sd,sr,start_period,messages=parse_legacy_workbook(file_path)
        status="\n\n".join(f"- {m}" for m in messages)
        return status,hd,hr,sd,sr,start_period,_clean(hd.tail(40)),_clean(hr.tail(40))
    except Exception as e:
        return f"Erreur d'import: {e}",pd.DataFrame(),pd.DataFrame(),empty_direct_start(),empty_reass_start(),"2026-12",pd.DataFrame(),pd.DataFrame()


def prepare_hypotheses(hist_d,hist_r,start_period,n_periods):
    try:
        n=int(n_periods)
        hd=build_hyp_direct(pd.DataFrame(hist_d),str(start_period),n)
        hr=build_hyp_reass(pd.DataFrame(hist_d),pd.DataFrame(hist_r),str(start_period),n)
        cd=empty_cibles_direct(str(start_period),n)
        cr=empty_cibles_reass(str(start_period),n)
        status=(f"Hypothèses préparées pour {n} période(s). Les valeurs Base % proviennent de l'historique quand il est exploitable. "
                "Dans Ajustement pts, +2 signifie +2 points de pourcentage. Les cellules de Cibles peuvent rester vides.")
        return status,hd,hr,cd,cr
    except Exception as e:
        return f"Erreur de préparation: {e}",pd.DataFrame(),pd.DataFrame(),pd.DataFrame(),pd.DataFrame()


def _plot(summary):
    s=pd.DataFrame(summary).copy(); fig=go.Figure()
    if s.empty: return fig
    s["period"]=pd.to_datetime(s["period"])
    fig.add_trace(go.Bar(x=s.period,y=s.net_earned_premium,name="Primes acquises nettes"))
    fig.add_trace(go.Bar(x=s.period,y=s.net_incurred_claims,name="Sinistres encourus nets"))
    fig.add_trace(go.Scatter(x=s.period,y=s.technical_result_before_general_expenses,name="Résultat technique avant FG",mode="lines+markers",yaxis="y2"))
    fig.update_layout(barmode="group",hovermode="x unified",legend=dict(orientation="h",y=1.1),yaxis2=dict(overlaying="y",side="right",title="Résultat"),margin=dict(l=30,r=30,t=55,b=30))
    return fig


def calculate(start_direct,start_reass,hyp_direct,hyp_reass,cibles_direct,cibles_reass,start_period,n_periods,hist_d,hist_r):
    try:
        n=int(n_periods)
        d,r,s,diag,apd,apr,hd,hr,cd,cr=run_projection(
            pd.DataFrame(start_direct),pd.DataFrame(start_reass),pd.DataFrame(hyp_direct),pd.DataFrame(hyp_reass),
            pd.DataFrame(cibles_direct),pd.DataFrame(cibles_reass),str(start_period),n,
            pd.DataFrame(hist_d),pd.DataFrame(hist_r)
        )
        out=Path(tempfile.gettempdir())/"projection_pourcentages.xlsx"
        export_projection(out,{"cibles_direct":cd,"cibles_reass":cr},d,r,s,diag,apd,apr)
        msg=(f"Projection calculée sur {n} période(s). Export: Hyp Direct, Hyp Reass, Cibles, Direct Local, Reass Local et CPC SAZ. "
             f"{len(diag)} diagnostic(s). Réassurance = taux de cession sur primes + taux de récupération sur sinistres.")
        return msg,_clean(s),_clean(d),_clean(r),apd,apr,diag,_plot(s),str(out)
    except Exception as e:
        empty=pd.DataFrame(); return f"Erreur de calcul: {e}",empty,empty,empty,empty,empty,empty,_plot(empty),None


def build_app():
    with gr.Blocks(title="Projection technique par pourcentages") as demo:
        gr.Markdown("""
# Projection technique — modèle par %
Le moteur reprend l'esprit des blocs **Progression par branche** de `pd.xlsx`, renommés **%**.

- **Progression** : valeur M = valeur M-1 × (1 + x%).
- **Commission Direct** = primes × taux de commission.
- **REC clôture** = primes × taux REC.
- **Réassurance** : primes cédées = primes Direct × **taux de cession** ; sinistres récupérés = sinistres Direct × **taux de récupération**.
- **% appliqué = Base historique + Ajustement manuel + Ajustement cible éventuel**.
- Ouvertures fixes sur l'exercice ; PAP/PANE fixes ; prime acquise cumulée non décroissante.
        """)
        hist_d=gr.State(pd.DataFrame()); hist_r=gr.State(pd.DataFrame())

        with gr.Tab("1. Historique & départ"):
            with gr.Row():
                file=gr.File(label="Importer pd.xlsx / historique",file_types=[".xlsx"],type="filepath")
                import_btn=gr.Button("Importer",variant="primary")
            import_status=gr.Markdown()
            with gr.Row():
                start_period=gr.Textbox(value="2026-12",label="Dernier mois observé (YYYY-MM)")
                n_periods=gr.Number(value=12,precision=0,label="Nombre de périodes à projeter")
                prep_btn=gr.Button("Préparer Hyp Direct / Hyp Reass",variant="secondary")
            with gr.Accordion("Historique détecté",open=False):
                hist_d_view=gr.Dataframe(interactive=False,label="Direct historique")
                hist_r_view=gr.Dataframe(interactive=False,label="Réass historique")
            gr.Markdown("### Bloc de départ Direct")
            start_direct=gr.Dataframe(value=empty_direct_start(),headers=DIRECT_START_COLUMNS,type="pandas",interactive=True)
            gr.Markdown("### Bloc de départ Réassurance\nLes ouvertures Réassurance peuvent être saisies si disponibles. Les flux futurs sont ensuite pilotés par les taux de cession/récupération.")
            start_reass=gr.Dataframe(value=empty_reass_start(),headers=REASS_START_COLUMNS,type="pandas",interactive=True)

        with gr.Tab("2. Hyp Direct"):
            gr.Markdown("`base_pct` et `adjustment_pts` sont exprimés en **points de %** : 5 = 5 %, +2 = +2 points. Le moteur calcule ensuite le % appliqué. Les lignes de janvier servent au reset YTD ; le bloc % visible dans Direct Local commence à février.")
            prep_status=gr.Markdown()
            hyp_direct=gr.Dataframe(value=pd.DataFrame(columns=HYP_COLUMNS+["source"]),type="pandas",interactive=True,label="Hyp Direct")

        with gr.Tab("3. Hyp Reass"):
            gr.Markdown("Trois drivers seulement par branche et par mois : **taux de cession des primes**, **taux de récupération des sinistres**, **taux de commission de réassurance**.")
            hyp_reass=gr.Dataframe(value=pd.DataFrame(columns=HYP_COLUMNS+["source"]),type="pandas",interactive=True,label="Hyp Reass")

        with gr.Tab("4. Cibles optionnelles"):
            gr.Markdown("Les cellules peuvent rester vides. Une cible de fin d'année peut générer un ajustement automatique `+/-Y` sur les % concernés. Une valeur de début d'année sert d'ancrage de janvier.")
            cibles_direct=gr.Dataframe(value=empty_cibles_direct("2026-12",12),headers=CIBLES_DIRECT_COLUMNS,type="pandas",interactive=True,label="Cibles Direct")
            cibles_reass=gr.Dataframe(value=empty_cibles_reass("2026-12",12),headers=CIBLES_REASS_COLUMNS,type="pandas",interactive=True,label="Cibles Réassurance")

        with gr.Tab("5. Projection & export"):
            calc_btn=gr.Button("Calculer la projection",variant="primary")
            calc_status=gr.Markdown()
            chart=gr.Plot()
            summary=gr.Dataframe(interactive=False,label="Synthèse CPC")
            with gr.Accordion("% Direct effectivement appliqués",open=False): applied_d=gr.Dataframe(interactive=False)
            with gr.Accordion("% Réass effectivement appliqués",open=False): applied_r=gr.Dataframe(interactive=False)
            with gr.Accordion("Projection Direct détaillée",open=False): direct_out=gr.Dataframe(interactive=False)
            with gr.Accordion("Projection Réass détaillée",open=False): reass_out=gr.Dataframe(interactive=False)
            with gr.Accordion("Diagnostics",open=True): diag=gr.Dataframe(interactive=False)
            export_file=gr.File(label="Exporter Excel")

        import_btn.click(import_workbook,inputs=[file],outputs=[import_status,hist_d,hist_r,start_direct,start_reass,start_period,hist_d_view,hist_r_view])
        prep_btn.click(prepare_hypotheses,inputs=[hist_d,hist_r,start_period,n_periods],outputs=[prep_status,hyp_direct,hyp_reass,cibles_direct,cibles_reass])
        calc_btn.click(calculate,inputs=[start_direct,start_reass,hyp_direct,hyp_reass,cibles_direct,cibles_reass,start_period,n_periods,hist_d,hist_r],outputs=[calc_status,summary,direct_out,reass_out,applied_d,applied_r,diag,chart,export_file])
    return demo


if __name__=="__main__":
    app=build_app(); port=int(os.environ.get("PORT","7860"))
    app.launch(server_name="0.0.0.0",server_port=port,show_error=True)
