import numpy as np, plotly.graph_objects as go
from dash import html, dcc, register_page

register_page(__name__, path="/analysis")

# 가짜 히트맵 데이터
z = np.random.randn(20, 20) * 15 + 50
fig = go.Figure(go.Heatmap(z=z, colorscale="RdYlBu_r"))
fig.update_layout(margin=dict(l=0, r=0, t=20, b=20))

layout = html.Div([
    html.H3("2-D Heatmap demo"),
    dcc.Graph(figure=fig, style={"height": "70vh"})
])