import os
import pandas as pd
from databricks import sql
from databricks.sdk.core import Config, oauth_service_principal
from posit.connect.external.databricks import (
    databricks_config,
    sql_credentials,
    ConnectStrategy,
)


SERVER_HOSTNAME = os.getenv("DATABRICKS_SERVER_HOSTNAME")

CATALOG = os.getenv("CATALOG", "prd_mega")
BOOST_SCHEMA = os.getenv("BOOST_SCHEMA", "boost")
INDICATOR_SCHEMA = os.getenv("INDICATOR_SCHEMA", "indicator")
BOOST = f"{CATALOG}.{BOOST_SCHEMA}"
INDICATOR = f"{CATALOG}.{INDICATOR_SCHEMA}"

CLIENT_ID = os.getenv("DATABRICKS_CLIENT_ID")
CLIENT_SECRET = os.getenv("DATABRICKS_CLIENT_SECRET")
TOKEN = os.getenv("DATABRICKS_TOKEN")


def credentials_provider():
    print("Initializing credential provider...")
    config = Config(
        host = f"https://{SERVER_HOSTNAME}",
        client_id     = CLIENT_ID,
        client_secret = CLIENT_SECRET)
    return oauth_service_principal(config)


def connect_credentials_provider():
    # No explicit credentials: use Posit Connect's Databricks OAuth integration,
    # which exchanges the content session token for the service principal's
    # credentials via OAuth token federation. Only works when running on Connect.
    cfg = databricks_config(
        host = f"https://{SERVER_HOSTNAME}",
        posit_connect_strategy = ConnectStrategy(),
    )
    return sql_credentials(cfg)


def execute_query(query):
    """
    Fetches data from the Databricks database and returns it as a pandas dataframe

    Returns
    -------
    df : pandas dataframe
        basic query of data from Databricks as a pandas dataframe
    """
    http_path = os.getenv("DATABRICKS_HTTP_PATH")
    if not SERVER_HOSTNAME or not http_path:
        raise EnvironmentError(
            "Missing Databricks connection settings — "
            f"DATABRICKS_SERVER_HOSTNAME={SERVER_HOSTNAME!r}, "
            f"DATABRICKS_HTTP_PATH={http_path!r}"
        )

    connect_kwargs = dict(
        server_hostname = SERVER_HOSTNAME,
        http_path = http_path,
    )
    if CLIENT_ID and CLIENT_SECRET:
        connect_kwargs["credentials_provider"] = credentials_provider
    elif TOKEN:
        connect_kwargs["access_token"] = TOKEN
    else:
        connect_kwargs["credentials_provider"] = connect_credentials_provider()

    with sql.connect(**connect_kwargs) as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        df = cursor.fetchall_arrow().to_pandas()

    return df


def get_available_data():
    return execute_query(f"SELECT * FROM {BOOST}.data_availability")


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

