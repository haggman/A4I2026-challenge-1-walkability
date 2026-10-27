-- ============================================================================
-- Stage 5: Proposed Least-Privilege Read-Only Dataset Grants (DCL)
-- Project: qwiklabs-gcp-04-ec3596addc43
-- Target Schemas: a4i_core, a4i_semantic, a4i_ml
-- Service Accounts:
--   - heat-agent-sa@qwiklabs-gcp-04-ec3596addc43.iam.gserviceaccount.com
--   - toolbox-sa@qwiklabs-gcp-04-ec3596addc43.iam.gserviceaccount.com
--
-- NOTE: Do NOT run until the Platform lane has provisioned both service accounts
-- and the team approves executing the DCL.
-- ============================================================================

GRANT `roles/bigquery.dataViewer`
ON SCHEMA `qwiklabs-gcp-04-ec3596addc43.a4i_core`
TO
  "serviceAccount:heat-agent-sa@qwiklabs-gcp-04-ec3596addc43.iam.gserviceaccount.com",
  "serviceAccount:toolbox-sa@qwiklabs-gcp-04-ec3596addc43.iam.gserviceaccount.com";

GRANT `roles/bigquery.dataViewer`
ON SCHEMA `qwiklabs-gcp-04-ec3596addc43.a4i_semantic`
TO
  "serviceAccount:heat-agent-sa@qwiklabs-gcp-04-ec3596addc43.iam.gserviceaccount.com",
  "serviceAccount:toolbox-sa@qwiklabs-gcp-04-ec3596addc43.iam.gserviceaccount.com";

GRANT `roles/bigquery.dataViewer`
ON SCHEMA `qwiklabs-gcp-04-ec3596addc43.a4i_ml`
TO
  "serviceAccount:heat-agent-sa@qwiklabs-gcp-04-ec3596addc43.iam.gserviceaccount.com",
  "serviceAccount:toolbox-sa@qwiklabs-gcp-04-ec3596addc43.iam.gserviceaccount.com";
