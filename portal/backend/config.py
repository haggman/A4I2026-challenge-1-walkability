"""Runtime settings, all overridable by environment variable."""
import os
from pathlib import Path

PROJECT_ID = os.environ.get("GCP_PROJECT", "qwiklabs-gcp-03-941c9ce79592")
GRID_DATASET = os.environ.get("GRID_DATASET", "a4i_grid")

# Grid geometry: cell (i, j) spans lat [i*CELL, (i+1)*CELL), lon [j*CELL, (j+1)*CELL).
CELL_DEG = 0.001

# Snapshot of the BigQuery tables, so the front end works without credentials
# and the demo doesn't depend on a live query. Refresh with:
#   python -m backend.data refresh
CACHE_DIR = Path(os.environ.get("PORTAL_CACHE_DIR", Path(__file__).resolve().parent.parent / "data"))

# Running on Cloud Run? Then use the service account. Locally, borrow the gcloud CLI's
# token, because application-default credentials are often a different account.
ON_CLOUD_RUN = "K_SERVICE" in os.environ
