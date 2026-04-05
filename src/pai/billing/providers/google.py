"""Google Cloud billing provider.

Reads billing data from BigQuery via the google-cloud-bigquery library.

Required env vars:
  GOOGLE_BILLING_PROJECT_ID   — GCP project that owns the billing export dataset
  GOOGLE_BILLING_DATASET_ID   — BigQuery dataset name (e.g. "gcloud_billing_export")

The billing table (gcp_billing_export_v1_*) is discovered automatically by
listing tables in the dataset and matching the standard v1 export prefix.
No table name needs to be configured manually.

Cost is read directly from the BigQuery export — no per-token pricing needed.
"""

from __future__ import annotations

import os
from datetime import datetime

from .base import BillingProvider, UsageRecord

_BILLING_TABLE_PREFIX = "gcp_billing_export_v1_"


class GoogleProvider(BillingProvider):
    name = "google"

    def is_available(self) -> tuple[bool, str]:
        if not os.environ.get("GOOGLE_BILLING_PROJECT_ID"):
            return False, "GOOGLE_BILLING_PROJECT_ID not set"
        if not os.environ.get("GOOGLE_BILLING_DATASET_ID"):
            return False, "GOOGLE_BILLING_DATASET_ID not set"
        try:
            import google.cloud.bigquery  # noqa: F401
        except ImportError:
            return False, "google-cloud-bigquery not installed (pip install google-cloud-bigquery db-dtypes)"
        return True, ""

    def fetch(self, start: datetime, end: datetime) -> list[UsageRecord]:
        from google.cloud import bigquery

        project_id = os.environ["GOOGLE_BILLING_PROJECT_ID"]
        dataset_id = os.environ["GOOGLE_BILLING_DATASET_ID"]

        client = bigquery.Client(project=project_id)

        table_id = _discover_billing_table(client, project_id, dataset_id)
        if not table_id:
            return []

        query = f"""
        SELECT
            sku.description                                  AS model,
            FORMAT_TIMESTAMP('%Y-%m', usage_start_time)      AS month,
            SUM(cost)
              + SUM((SELECT IFNULL(SUM(c.amount), 0) FROM UNNEST(credits) c))
                                                             AS net_cost
        FROM `{table_id}`
        WHERE service.description IN ('Generative Language API', 'Vertex AI', 'Cloud AI Platform')
          AND usage_start_time >= @start_date
          AND usage_start_time <= @end_date
        GROUP BY 1, 2
        HAVING net_cost != 0
        ORDER BY month DESC, net_cost DESC
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("start_date", "TIMESTAMP", start),
                bigquery.ScalarQueryParameter("end_date",   "TIMESTAMP", end),
            ]
        )

        try:
            results = client.query(query, job_config=job_config).result()
        except Exception:
            return []

        return [
            UsageRecord(
                provider="Google",
                model=row.model,
                month=row.month,
                input_tokens=0,
                output_tokens=0,
                cost=float(row.net_cost or 0.0),
            )
            for row in results
        ]


# ── Discovery ─────────────────────────────────────────────────────────────────

def _discover_billing_table(client, project_id: str, dataset_id: str) -> str | None:
    """Find the gcp_billing_export_v1_* table in the dataset. Returns full table ref or None."""
    try:
        tables = list(client.list_tables(f"{project_id}.{dataset_id}"))
    except Exception:
        return None

    for table in tables:
        if table.table_id.startswith(_BILLING_TABLE_PREFIX):
            return f"{project_id}.{dataset_id}.{table.table_id}"

    return None
