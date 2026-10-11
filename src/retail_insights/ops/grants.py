"""Give the Databricks App's service principal read access to the retail schema.

Every Databricks App runs as its own service principal. Binding a SQL warehouse
as an app resource lets the app *use* the warehouse, but Unity Catalog still
decides which tables it may read. This script grants exactly what the agent
needs (USE CATALOG, USE SCHEMA, SELECT on the schema) and nothing more.

Run after `databricks bundle deploy` (the CD workflow does this for you):
    uv run retail-grant-app --app-name retail-insights-dev --catalog workspace \\
        --schema retail_dev
"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--app-name", required=True)
    p.add_argument("--catalog", required=True)
    p.add_argument("--schema", required=True)
    p.add_argument("--warehouse-id", default="")
    p.add_argument(
        "--warehouse-name",
        default="Serverless Starter Warehouse",
        help="used to find the warehouse when --warehouse-id is not given",
    )
    args = p.parse_args(argv)

    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service.sql import StatementState

    ws = WorkspaceClient()
    # Development mode may prefix resource names, so fall back to a suffix match.
    app = next((a for a in ws.apps.list() if a.name == args.app_name), None) or next(
        (a for a in ws.apps.list() if a.name.endswith(args.app_name)), None
    )
    if app is None:
        sys.exit(f"app {args.app_name!r} not found; run `databricks bundle deploy` first")
    principal = app.service_principal_client_id
    if not principal:
        sys.exit(f"app {args.app_name} has no service principal yet; deploy it first")

    warehouse_id = args.warehouse_id or next(
        (w.id for w in ws.warehouses.list() if w.name == args.warehouse_name), None
    )
    if not warehouse_id:
        sys.exit(f"no warehouse id given and none named {args.warehouse_name!r}")

    statements = [
        # The ETL setup task creates this too; doing it here lets grants run before the first ETL run.
        f"CREATE SCHEMA IF NOT EXISTS `{args.catalog}`.`{args.schema}`",
        f"GRANT USE CATALOG ON CATALOG `{args.catalog}` TO `{principal}`",
        f"GRANT USE SCHEMA ON SCHEMA `{args.catalog}`.`{args.schema}` TO `{principal}`",
        f"GRANT SELECT ON SCHEMA `{args.catalog}`.`{args.schema}` TO `{principal}`",
    ]
    for sql in statements:
        r = ws.statement_execution.execute_statement(
            statement=sql, warehouse_id=warehouse_id, wait_timeout="30s"
        )
        if r.status.state != StatementState.SUCCEEDED:
            msg = r.status.error.message if r.status.error else r.status.state
            sys.exit(f"failed: {sql}\n{msg}")
        print(f"ok: {sql}")


if __name__ == "__main__":
    main()
