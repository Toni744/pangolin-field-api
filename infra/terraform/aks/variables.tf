variable "subscription_id" {
  description = "Azure subscription used by the AKS platform."
  type        = string
}

variable "location" {
  description = "Azure region for the platform."
  type        = string
  default     = "canadacentral"
}

variable "resource_group_name" {
  description = "Resource group for the Pangolin AKS platform."
  type        = string
  default     = "rg-pangolin-aks-dev"
}

variable "deploy_platform" {
  description = "Create billable AKS, ACR, Storage, and Log Analytics resources."
  type        = bool
  default     = false
}

variable "enable_demo_cleanup" {
  description = "Create a resource-group-scoped GitHub OIDC identity for demo cleanup."
  type        = bool
  default     = false

  validation {
    condition     = !var.enable_demo_cleanup || var.deploy_platform
    error_message = "deploy_platform must be true when demo cleanup is enabled."
  }
}

variable "storage_account_name" {
  description = "Globally unique lowercase Storage account name."
  type        = string
  default     = ""

  validation {
    condition = !var.deploy_platform || can(regex(
      "^[a-z0-9]{3,24}$",
      var.storage_account_name
    ))
    error_message = "When deploy_platform is true, use a 3-24 character lowercase alphanumeric Storage name."
  }
}

variable "container_registry_name" {
  description = "Globally unique ACR name containing only letters and digits."
  type        = string
  default     = ""

  validation {
    condition = !var.deploy_platform || can(regex(
      "^[A-Za-z0-9]{5,50}$",
      var.container_registry_name
    ))
    error_message = "When deploy_platform is true, use a 5-50 character ACR name."
  }
}

variable "aks_admin_group_object_ids" {
  description = "Microsoft Entra security group object IDs granted AKS cluster-admin access."
  type        = list(string)
  default     = []

  validation {
    condition     = !var.deploy_platform || length(var.aks_admin_group_object_ids) > 0
    error_message = "Provide at least one Entra admin group when deploying the AKS cluster."
  }
}

variable "api_server_authorized_ip_ranges" {
  description = "Trusted public CIDR ranges allowed to reach the AKS API server."
  type        = list(string)
  default     = []

  validation {
    condition = !var.deploy_platform || (
      length(var.api_server_authorized_ip_ranges) > 0 &&
      alltrue([
        for cidr in var.api_server_authorized_ip_ranges : can(cidrhost(cidr, 0))
      ])
    )
    error_message = "Set one or more valid, trusted CIDR ranges before deploying AKS."
  }
}

variable "github_repository" {
  description = "GitHub owner/repository slug allowed to deploy through OIDC."
  type        = string
  default     = ""

  validation {
    condition = !var.deploy_platform || can(regex(
      "^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$",
      var.github_repository
    ))
    error_message = "Set github_repository to an owner/repository slug before deploying."
  }
}

variable "github_environment" {
  description = "GitHub environment name used in the OIDC subject and deployment approval gate."
  type        = string
  default     = "aks-deploy"
}

variable "system_node_vm_size" {
  description = "VM SKU for the autoscaling AKS system node pool."
  type        = string
  default     = "Standard_D2s_v5"
}

variable "kubernetes_version" {
  description = "Optional supported AKS Kubernetes version. Null selects the Azure-supported default."
  type        = string
  default     = null
  nullable    = true
}
