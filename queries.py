"""Databricks access for the RPF landing dashboard.

Every query runs as the person looking at the page. Posit Connect mints a short
lived token for each viewer and sends it to us in a request header; we hand that
token to the Databricks OAuth integration, which swaps it for credentials scoped
to that user. If a viewer has no rights on a table, their query fails - that is
the point of viewer authentication rather than a shared service account.

Set DATABRICKS_CLIENT_ID/SECRET or DATABRICKS_TOKEN to bypass all of this when
running off Connect (a laptop, a CI job). On Connect, leave them unset.
"""

import os
from contextlib import contextmanager

import pandas as pd
from databricks import sql
from databricks.sdk.core import Config, oauth_service_principal
from flask import has_request_context, request
from posit.connect.external.databricks import (
    databricks_config,
    sql_credentials,
    ConnectStrategy,
)


# Connect sets this on every request it proxies through to us.
USER_SESSION_TOKEN_HEADER = "Posit-Connect-User-Session-Token"

SERVER_HOSTNAME = os.getenv("DATABRICKS_SERVER_HOSTNAME")
HTTP_PATH = os.getenv("DATABRICKS_HTTP_PATH")

CATALOG = os.getenv("CATALOG", "prd_mega")
BOOST_SCHEMA = os.getenv("BOOST_SCHEMA", "boost")
INDICATOR_SCHEMA = os.getenv("INDICATOR_SCHEMA", "indicator")
BOOST = f"{CATALOG}.{BOOST_SCHEMA}"
INDICATOR = f"{CATALOG}.{INDICATOR_SCHEMA}"

# The sample expenditure table sits in its own schema in QA. Default it to the
# boost schema so a single-schema deployment carries on working unchanged.
EXPENDITURE_SCHEMA = os.getenv("EXPENDITURE_SCHEMA", BOOST_SCHEMA)
EXPENDITURE = f"{CATALOG}.{EXPENDITURE_SCHEMA}"

CLIENT_ID = os.getenv("DATABRICKS_CLIENT_ID")
CLIENT_SECRET = os.getenv("DATABRICKS_CLIENT_SECRET")
TOKEN = os.getenv("DATABRICKS_TOKEN")


class ViewerNotSignedIn(RuntimeError):
    """No viewer token on the request, so we cannot authenticate as anyone."""


def viewer_token():
    """The token Connect minted for whoever is viewing the page, if any."""
    if not has_request_context():
        return None
    return request.headers.get(USER_SESSION_TOKEN_HEADER)


def service_principal_credentials():
    config = Config(
        host = f"https://{SERVER_HOSTNAME}",
        client_id     = CLIENT_ID,
        client_secret = CLIENT_SECRET)
    return oauth_service_principal(config)


def viewer_credentials():
    """Databricks credentials belonging to the current viewer.

    Built per request on purpose - the token is short lived and different for
    every user, so this must not be cached or reused across requests.
    """
    token = viewer_token()
    if not token:
        raise ViewerNotSignedIn(
            f"No {USER_SESSION_TOKEN_HEADER} header on this request. The "
            "Databricks integration uses Viewer authentication, so the "
            "dashboard has to be opened through Posit Connect by a signed-in "
            "user who has authorised the integration."
        )

    cfg = databricks_config(
        host = f"https://{SERVER_HOSTNAME}",
        posit_connect_strategy = ConnectStrategy(user_session_token = token),
    )
    # sql_credentials hands back a no-arg callable, which is the shape
    # databricks.sql.connect wants for credentials_provider.
    return sql_credentials(cfg)


@contextmanager
def connect():
    """Open one Databricks connection.

    Use this directly when a page needs several queries - each connection costs
    an OAuth exchange plus a warehouse handshake, so opening one and reusing it
    is noticeably faster than calling execute_query repeatedly.
    """
    if not SERVER_HOSTNAME or not HTTP_PATH:
        raise EnvironmentError(
            "Missing Databricks connection settings — "
            f"DATABRICKS_SERVER_HOSTNAME={SERVER_HOSTNAME!r}, "
            f"DATABRICKS_HTTP_PATH={HTTP_PATH!r}"
        )

    connect_kwargs = dict(
        server_hostname = SERVER_HOSTNAME,
        http_path = HTTP_PATH,
    )
    if CLIENT_ID and CLIENT_SECRET:
        connect_kwargs["credentials_provider"] = service_principal_credentials
    elif TOKEN:
        connect_kwargs["access_token"] = TOKEN
    else:
        connect_kwargs["credentials_provider"] = viewer_credentials()

    with sql.connect(**connect_kwargs) as conn:
        yield conn


def run(conn, query):
    """Run one query on an already open connection."""
    cursor = conn.cursor()
    cursor.execute(query)
    return cursor.fetchall_arrow().to_pandas()


def execute_query(query):
    """
    Fetches data from the Databricks database and returns it as a pandas dataframe

    Returns
    -------
    df : pandas dataframe
        basic query of data from Databricks as a pandas dataframe
    """
    with connect() as conn:
        return run(conn, query)


def get_available_data():
    return execute_query(f"SELECT * FROM {BOOST}.data_availability")


def get_expenditure():
    """Public expenditure by country, year and functional category."""
    return execute_query(f"""
        SELECT country_code, country_name, region, year, functional_category,
               expenditure_usd_millions, share_of_gdp_pct,
               share_of_total_expenditure_pct
        FROM {EXPENDITURE}.mega_sample_expenditure
    """)


def get_gdp():
    return execute_query(f"SELECT * FROM {INDICATOR}.gdp")

def get_country():
    return execute_query(f"SELECT * FROM {INDICATOR}.country")


def get_health_data(gdp, country):
    health_indicator = execute_query(f"SELECT * FROM {INDICATOR}.universal_health_coverage_index_gho")
    merged = pd.merge(gdp, health_indicator, on=['country_code', 'year'], how='inner')
    merged = merged[merged.gdp_per_capita_2017_ppp.notnull() & merged.universal_health_coverage_index.notnull()]
    df = pd.merge(merged, country, on=['country_code'], how='inner')
    df = df[df.income_level != 'INX']
    df['universal_health_coverage_index'] = df['universal_health_coverage_index']/100
    df['gdp_per_capita_2017_ppp'] = df['gdp_per_capita_2017_ppp'].astype(int)
    return df


def get_edu_data(gdp, country):
    edu_indicator = execute_query(f"SELECT * FROM {INDICATOR}.learning_poverty_rate")
    merged = pd.merge(gdp, edu_indicator, on=['country_code', 'year'], how='inner')
    merged = merged[merged.gdp_per_capita_2017_ppp.notnull() & merged.learning_poverty_rate.notnull()]
    df = pd.merge(merged, country, on=['country_code'], how='inner')
    df = df[df.income_level != 'INX']

    # drop unncessary precision
    df['learning_poverty_rate'] = df['learning_poverty_rate'].round(2)
    df['gdp_per_capita_2017_ppp'] = df['gdp_per_capita_2017_ppp'].astype(int)

    # some years have very few countries' data available, drop them
    country_counts = df.groupby('year')['country_code'].nunique()
    comparable_years = country_counts[country_counts >= 45].index
    df_filtered = df[df['year'].isin(comparable_years)]


    return df_filtered
