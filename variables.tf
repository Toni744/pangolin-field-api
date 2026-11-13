variable "subscription_id" {
  description = "Azure subscription used by Terraform."
  type        = string
}

variable "location" {
  description = "Azure region for the demo resources. Confirm availability before deployment."
  type        = string
  default     = "canadacentral"
}

variable "resource_group_name" {
  description = "Resource group for the demo."
  type        = string
  default     = "rg-pangolin-field-api-dev"
}

variable "storage_account_name" {
  description = "Globally unique, lowercase alphanumeric Azure Storage account name."
  type        = string
  default     = ""

  validation {
    condition = !var.deploy_platform || can(regex(
      "^[a-z0-9]{3,24}$",
      var.storage_account_name
    ))
    error_message = "When deploy_platform is enabled, the Storage account name must be 3-24 lowercase letters or digits."
  }
}

variable "container_registry_name" {
  description = "Globally unique Azure Container Registry name; letters and digits only."
  type        = string
  default     = ""

  validation {
    condition = !var.deploy_platform || can(regex(
      "^[A-Za-z0-9]{5,50}$",
      var.container_registry_name
    ))
    error_message = "When deploy_platform is true, the registry name must be 5-50 letters or digits."
  }
}

variable "container_image" {
  description = "Fully qualified image reference in ACR; required when deploy_api is true."
  type        = string
  default     = ""

  validation {
    condition = !var.deploy_api || (
      can(regex("@sha256:[0-9a-f]{64}$", var.container_image)) ||
      can(regex(":[A-Za-z0-9_.-]+$", var.container_image))
    )
    error_message = "When deploy_api is true, use an image reference with a tag or sha256 digest."
  }
}

variable "deploy_api" {
  description = "Deprecated Container Apps deployment switch; this legacy API path is disabled."
  type        = bool
  default     = false

  validation {
    condition     = !var.deploy_api
    error_message = "The legacy Container Apps API path is retired; deploy with infra/terraform/aks and Helm."
  }
}

variable "deploy_platform" {
  description = "Deprecated Container Apps foundation switch; use the supported AKS configuration instead."
  type        = bool
  default     = false

  validation {
    condition     = !var.deploy_platform
    error_message = "The legacy Container Apps stack is retired; use infra/terraform/aks."
  }
}

variable "entra_external_id_issuer" {
  description = "Exact issuer value from the External ID tenant's OpenID Connect metadata."
  type        = string
  default     = ""

  validation {
    condition = !var.deploy_api || (
      length(trimspace(var.entra_external_id_issuer)) > 0 &&
      startswith(var.entra_external_id_issuer, "https://")
    )
    error_message = "When deploy_api is true, provide the exact HTTPS External ID issuer."
  }
}

variable "entra_external_id_jwks_url" {
  description = "JWKS URI from the External ID tenant's OpenID Connect metadata."
  type        = string
  default     = ""

  validation {
    condition = !var.deploy_api || (
      length(trimspace(var.entra_external_id_jwks_url)) > 0 &&
      startswith(var.entra_external_id_jwks_url, "https://")
    )
    error_message = "When deploy_api is true, provide the HTTPS JWKS URI from External ID metadata."
  }
}

variable "entra_api_audience" {
  description = "Expected audience claim for access tokens issued to this API."
  type        = string
  default     = ""

  validation {
    condition     = !var.deploy_api || length(trimspace(var.entra_api_audience)) > 0
    error_message = "When deploy_api is true, provide the expected access-token audience."
  }
}

variable "entra_api_scope" {
  description = "Delegated API scope required to upload samples."
  type        = string
  default     = "samples.write"

  validation {
    condition     = !var.deploy_api || length(trimspace(var.entra_api_scope)) > 0
    error_message = "When deploy_api is true, provide the delegated API scope required for uploads."
  }
}
