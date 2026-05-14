variable "project_id" {
  description = "GCP project id"
  type        = string
}

variable "region" {
  description = "GCP region. us-east4 (Ashburn, VA) is closest to Kalshi's AWS infrastructure."
  type        = string
  default     = "us-east4"
}

variable "zone" {
  description = "GCP zone within the region."
  type        = string
  default     = "us-east4-a"
}

variable "machine_type" {
  description = "Compute Engine machine type for the trading VM."
  type        = string
  default     = "c3-highcpu-8"
}
