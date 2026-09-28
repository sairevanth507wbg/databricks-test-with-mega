# RPF Landing Dashboard

This is a dash app that contains a landing page and an overview dashboard used as an entry point for the country-specific Re-imagining Public Finance (RPF) dashboard.

## Development

First `git clone` this repo.

Get connection details for the SQL Warehouse compute resource which is used for providing the database connection: https://docs.databricks.com/en/integrations/compute-details.html
Contact the maintainers of this repo for databricks client ID and secret.

Create `.env` from `.env.example` and the obtained information:

```bash
cp .env.example .env
# edit .env with the obtained information
```


Then to setup and verify the app works locally:

```bash
pip install -r requirements.txt
dotenv run -- python app.py
open http://127.0.0.1:8050/
```
You should see the data app.


## Deployment

Ensure you have an RStudio Connect account, if not [request here](https://worldbankgroup.service-now.com/wbg?id=ticket&table=sc_req_item&sys_id=fbb93028476502d09169d03fe16d4309). Upon account provisioning, you will be provided the internal and external server addresses. Generate API key(s) on the target server's UI.

Check which python version is supported by the server with:

```bash
rsconnect content search --server [server URL] --api-key "$CONNECT_API_KEY" | jq -c '.[] | {}' | sort | uniq
```

As of writing both the internal and external server supports 3.8.14 so that's the version we are going to use for building & deploying the dash app. If you are using `pyenv` this repo's python version has configured to use 3.8.14. If the target server uses a different version, feel free to switch using `pyenv local 3.x.x`.


Add your RStudio Connect API key (one-time action):

```bash
rsconnect add --server https://w0lxdrconn01.worldbank.org --api-key "$CONNECT_API_KEY" --name staging
```

To deploy:

```bash
rsconnect deploy dash --name staging ./
```
