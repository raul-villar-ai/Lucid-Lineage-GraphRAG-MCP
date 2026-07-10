terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = "europe-west2" # UK South (London) - Aligning with Sovereign boundaries
}

# Provision the Vertex AI Agent Endpoint
resource "google_vertex_ai_endpoint" "lucid_lineage_endpoint" {
  name         = "lucid-lineage-compliance-agent"
  display_name = "Lucid Lineage Sovereign Engine"
  location     = "europe-west2"
  description  = "Managed API endpoint for the Lucid Lineage LangChain compliance agent."

  labels = {
    environment = "sandbox"
    security    = "sc-cleared-boundary"
  }
}

# (Mock) Provision Neo4j Aura Enterprise Graph Database
# Note: Requires official Neo4j provider in a full deployment
resource "google_compute_instance" "neo4j_graph_host" {
  name         = "lucid-lineage-neo4j-core"
  machine_type = "e2-standard-4"
  zone         = "europe-west2-a"

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2204-lts"
    }
  }

  network_interface {
    network = "default"
    # Keeping air-gapped / no public IP for sovereignty
  }
}

# Provision Cloud Run service for Streamlit UI
resource "google_cloud_run_v2_service" "streamlit_ui" {
  name     = var.streamlit_service_name
  location = var.region

  template {
    containers {
      image = "gcr.io/${var.project_id}/lucid-lineage-ui:latest"
      
      env {
        name  = "NEO4J_URI"
        value = "neo4j+s://internal-neo4j-cluster.local" # Internal routing
      }
      
      # Inject the Service Account for zero-trust IAM
    }
    service_account = google_service_account.agent_sa.email
  }
}