# IAM bindings for zero-trust execution
# Maps the simulated "SC_Cleared" clearance to actual Google Cloud IAM roles

# Custom role for the Lucid Lineage Agent
resource "google_project_iam_custom_role" "lucid_lineage_agent_role" {
  role_id     = "LucidLineageAgent"
  title       = "Lucid Lineage Compliance Agent"
  description = "Grants necessary permissions for the agent to access Neo4j and Vertex AI."
  permissions = [
    "aiplatform.endpoints.predict",
    "compute.instances.get",
    "run.services.invoke",
  ]
}

# Service Account for the Agent to run as
resource "google_service_account" "agent_sa" {
  account_id   = "lucid-lineage-agent-sa"
  display_name = "Lucid Lineage Agent Service Account"
}

# Bind the custom role to the Agent's Service Account
resource "google_project_iam_binding" "agent_role_binding" {
  project = var.project_id
  role    = google_project_iam_custom_role.lucid_lineage_agent_role.id
  members = [
    "serviceAccount:${google_service_account.agent_sa.email}"
  ]
}

# Security Analyst Group binding (Simulating SC_Cleared human-in-the-loop)
resource "google_project_iam_binding" "analyst_viewer_binding" {
  project = var.project_id
  role    = "roles/viewer"
  members = [
    "group:security-analysts@example.com"
  ]
}
