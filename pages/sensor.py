from dash import html, dcc, register_page
import dash_bootstrap_components as dbc
import pandas as pd

register_page(__name__, path="/sensor")

dummy = pd.DataFrame({
    "concrete_id": ["C001", "C002"],
    "name": ["거푸집A", "슬래브B"],
    "shape": ["rect", "cylinder"]
})

layout = html.Div([
    html.H3("콘크리트 DB (목록)"),
    dbc.Button("+ 추가", color="success", className="mb-2"),
    dbc.Table.from_dataframe(dummy, striped=True, bordered=True, hover=True)
])