"""Plotly charts in the brand palette."""
import pandas as pd
import plotly.graph_objects as go

from .theme import C

FONT = dict(family="Inter, sans-serif", size=12, color=C["text"])


def _layout(fig, h=280, **kw):
    fig.update_layout(height=h, margin=kw.pop("margin", dict(l=8, r=8, t=8, b=8)), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", font=FONT, showlegend=kw.pop("showlegend", False), **kw)
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=C["border"])
    fig.update_yaxes(showgrid=False, zeroline=False, linecolor=C["border"])
    return fig


CONFIG = {"displayModeBar": False}


def donut_actions(df):
    order = ["Auto-resolve", "Ask for info", "Escalate"]
    vc = df["action"].value_counts().reindex(order).fillna(0)
    fig = go.Figure(go.Pie(labels=order, values=vc.values, hole=.68, sort=False,
                           marker=dict(colors=[C["green"], C["purple"], C["red"]], line=dict(color="#fff", width=2)),
                           textinfo="none", hovertemplate="%{label}: %{value}<extra></extra>"))
    fig.add_annotation(text=f"<b>{len(df)}</b><br><span style='font-size:11px;color:{C['muted']}'>tickets</span>",
                       showarrow=False, font=dict(size=22, family="Inter"))
    return _layout(fig, 260, showlegend=True, legend=dict(orientation="h", y=-0.08, x=0.5, xanchor="center"))


def bar_teams(df):
    esc = df[df["action"] == "Escalate"]["escalation_team"].value_counts().sort_values()
    fig = go.Figure(go.Bar(x=esc.values, y=esc.index, orientation="h", marker_color=C["blue"],
                           text=esc.values, textposition="outside", cliponaxis=False,
                           hovertemplate="%{y}: %{x}<extra></extra>"))
    fig.update_traces(marker=dict(cornerradius=6))
    fig.update_xaxes(visible=False)
    return _layout(fig, 260, bargap=.35)


def heat_cat_risk(df):
    risks = ["Low", "Medium", "High", "Critical"]
    t = pd.crosstab(df["category"], df["risk"]).reindex(columns=risks, fill_value=0)
    t = t.loc[t.sum(axis=1).sort_values().index]
    fig = go.Figure(go.Heatmap(z=t.values, x=risks, y=[c.replace("_", " ") for c in t.index], text=t.values,
                               texttemplate="%{text}", colorscale=[[0, "#F5F8FD"], [0.25, "#CFE3FF"], [1, C["navy"]]],
                               showscale=False, xgap=3, ygap=3, hovertemplate="%{y} · %{x}: %{z}<extra></extra>"))
    return _layout(fig, 300)


def line_daily(df, incidents):
    d = pd.to_datetime(df["created_at"]).dt.normalize().value_counts().sort_index()
    idx = pd.date_range(d.index.min(), d.index.max())
    d = d.reindex(idx, fill_value=0)
    fig = go.Figure(go.Scatter(x=d.index, y=d.values, mode="lines", line=dict(color=C["blue"], width=2.5, shape="linear"),
                               fill="tozeroy", fillcolor="rgba(51,149,255,.10)",
                               hovertemplate="%{x|%d %b}: %{y} tickets<extra></extra>"))
    if len(incidents):
        days = pd.to_datetime(incidents["window_start"]).dt.normalize()
        fig.add_trace(go.Scatter(x=days, y=d.reindex(days).values, mode="markers",
                                 marker=dict(color=C["red"], size=11, line=dict(color="#fff", width=2)),
                                 text=incidents["incident_id"], hovertemplate="%{text} · %{x|%d %b}<extra></extra>"))
    fig.update_xaxes(tickformat="%d %b")
    return _layout(fig, 260)


def gauge(value, title):
    color = C["green"] if value >= 95 else C["amber"] if value >= 85 else C["red"]
    fig = go.Figure(go.Indicator(mode="gauge+number", value=value, number=dict(suffix="%", font=dict(size=26, family="Inter")),
                                 title=dict(text=title, font=dict(size=13, color=C["muted"])),
                                 gauge=dict(axis=dict(range=[0, 100], visible=False), bar=dict(color=color, thickness=.8),
                                            bgcolor="#EEF2F8", borderwidth=0)))
    return _layout(fig, 190, margin=dict(l=18, r=18, t=40, b=0))


def mini_gauge(value, threshold=85):
    color = C["red"] if value < threshold else C["green"]
    fig = go.Figure(go.Indicator(mode="gauge+number", value=value, number=dict(suffix="%", font=dict(size=20, family="Inter")),
                                 gauge=dict(axis=dict(range=[50, 100], visible=False), bar=dict(color=color, thickness=.8),
                                            bgcolor="#EEF2F8", borderwidth=0,
                                            threshold=dict(line=dict(color=C["navy"], width=2), thickness=.9,
                                                           value=threshold))))
    return _layout(fig, 120, margin=dict(l=10, r=10, t=10, b=0))


def confusion(conf: pd.DataFrame):
    fig = go.Figure(go.Heatmap(z=conf.values, x=list(conf.columns), y=list(conf.index), text=conf.values,
                               texttemplate="%{text}", showscale=False, xgap=3, ygap=3,
                               colorscale=[[0, "#F5F8FD"], [0.05, "#CFE3FF"], [1, C["blue_dark"]]],
                               hovertemplate="expected %{y} · got %{x}: %{z}<extra></extra>"))
    fig.update_xaxes(title=dict(text="Agent", font=dict(size=11, color=C["muted"])), side="top")
    fig.update_yaxes(title=dict(text="Answer key", font=dict(size=11, color=C["muted"])), autorange="reversed")
    return _layout(fig, 260)
