import dash
import dash_bootstrap_components as dbc
from dash import dcc, html, dash_table
from dash.dependencies import Input, Output
from queries import get_expenditure, get_available_data
from plot import make_expenditure_plot

app = dash.Dash(
    __name__,
    suppress_callback_exceptions=True,
    use_pages=True,
)

SIDEBAR_STYLE = {
    "position": "fixed",
    "top": 0,
    "left": 0,
    "bottom": 0,
    "width": "16rem",
    "padding": "2rem 1rem",
}

CONTENT_STYLE = {
    "marginLeft": "18rem",
    "marginRight": "2rem",
    "padding": "2rem 1rem",
}

def get_relative_path(page_name):
    return dash.page_registry[f'pages.{page_name}']['relative_path']

sidebar = html.Div(
    [
        dbc.Row([
            html.Img(
                src=app.get_asset_url('rpf_logo.png'),
                style={'height': '168'}
            ),
        ]),

        html.Hr(),
        dbc.Nav(
            [
                dbc.NavLink("Overview", href=get_relative_path('home'), active="exact"),
                dbc.NavLink("Thematic Studies", href=get_relative_path('thematic'), active="exact"),
                dbc.NavLink("Data Availability", href=get_relative_path('availability'), active="exact", id="avail-nav"),
            ],
            vertical=True,
            pills=True,
        ),
    ],
    style=SIDEBAR_STYLE,
)

content = html.Div(dash.page_container,
    id="page-content", style=CONTENT_STYLE
)

dummy_div = html.Div(id="div-for-redirect")

app.layout = html.Div([dcc.Location(id='url', refresh=False),
                       sidebar,
                       content,
                       dummy_div])

@app.callback(
    Output('div-for-redirect', 'children'),
    Input('url', 'pathname')
)
def redirect_default(url_pathname):
    known_paths = list(p['relative_path'] for p in dash.page_registry.values())
    if url_pathname not in known_paths:
        return dcc.Location(pathname=get_relative_path('home'), id="redirect-me")
    else:
        return ""


@app.callback(
    Output('thematic-content', 'children'),
    Input('thematic-tabs', 'active_tab'),
    running=[
        (
            Output("thematic-spinner", "style"),
            {"display": "block"},
            {"display": "none"},
        ),
        (
            Output("thematic-content", "style"),
            {"display": "none"},
            {"display": "block"},
        ),
    ],
)
def render_thematic_content(tab):
    category = 'Education' if tab == 'tab-education' else 'Health'
    expenditure = get_expenditure()
    return html.Div([
        dcc.Graph(id='thematic-plot', figure=make_expenditure_plot(expenditure, category))
    ])

@app.callback(
    Output('availability-content', 'children'),
    Input('avail-nav', 'active'),
    running=[
        (
            Output("availability-spinner", "style"),
            {"display": "block"},
            {"display": "none"},
        ),
        (
            Output("availability-content", "style"),
            {"display": "none"},
            {"display": "block"},
        ),
    ],
)
def render_availability_content(active):
    df = get_available_data()
    df.columns = df.columns.str.replace('_', ' ').str.title()

    table = dash_table.DataTable(
        df.to_dict('records'),
        [{"name": i, "id": i} for i in df.columns],
        filter_action="native",
        sort_action="native",
        page_size=200,
        style_table={'overflowX': 'auto'},  # Scrollable table
        style_cell={'textAlign': 'left'},
        style_header={
            'fontWeight': 'bold',
            'whiteSpace': 'normal',
            'height': 'auto',
        },
        style_data_conditional=[
            {
                'if': {'row_index': 'odd'},
                'backgroundColor': '#2c3034',
            },
        ],
    )

    return table


if __name__ == '__main__':
    app.run_server(debug=True)

