"""Builds a RetailAgent from environment variables.

Inside Databricks Apps these come from app.yaml (`valueFrom` binds the SQL
warehouse and serving endpoint declared as app resources in resources/apps.yml).
Locally, export them yourself; auth comes from your Databricks CLI profile.
"""

from __future__ import annotations

import os

from retail_insights.agent.core import RetailAgent
from retail_insights.agent.executor import DatabricksSqlExecutor
from retail_insights.agent.llm import DatabricksChatClient
from retail_insights.agent.tools import Toolbox


def resolve_schema() -> str:
    """RETAIL_SCHEMA wins. Otherwise derive from the app name, which the bundle
    sets to retail-insights-<target>, so each target reads its own schema."""
    if os.environ.get("RETAIL_SCHEMA"):
        return os.environ["RETAIL_SCHEMA"]
    app = os.environ.get("DATABRICKS_APP_NAME", "")
    for target in ("dev", "staging", "prod"):
        if app.endswith(f"retail-insights-{target}"):
            return f"retail_{target}"
    return "retail_dev"


def build_agent_from_env() -> RetailAgent:
    warehouse = os.environ.get("DATABRICKS_WAREHOUSE_ID")
    endpoint = os.environ.get("SERVING_ENDPOINT", "databricks-meta-llama-3-3-70b-instruct")
    if not warehouse:
        raise RuntimeError("DATABRICKS_WAREHOUSE_ID is not set")
    catalog = os.environ.get("RETAIL_CATALOG", "workspace")
    schema = resolve_schema()
    executor = DatabricksSqlExecutor(warehouse, catalog, schema)
    return RetailAgent(DatabricksChatClient(endpoint), Toolbox(executor, catalog, schema))
