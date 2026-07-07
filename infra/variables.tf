variable "project_id" {
  description = "The Google Cloud Project ID"
  type        = string
}

variable "region" {
  description = "The Google Cloud Region"
  type        = string
  default     = "europe-west2"
}

variable "streamlit_service_name" {
  description = "Name for the Cloud Run service hosting Streamlit"
  type        = string
  default     = "lucid-lineage-ui"
}
