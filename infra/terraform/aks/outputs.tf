output "resource_group_name" {
  description = "Resource group containing the AKS platform."
  value       = var.deploy_platform ? azurerm_resource_group.platform[0].name : null
}

output "aks_name" {
  description = "AKS cluster name."
  value       = var.deploy_platform ? azurerm_kubernetes_cluster.platform[0].name : null
}

output "acr_login_server" {
  description = "ACR login server; admin credentials are disabled."
  value       = var.deploy_platform ? azurerm_container_registry.platform[0].login_server : null
}

output "storage_account_url" {
  description = "HTTPS Blob endpoint."
  value       = var.deploy_platform ? azurerm_storage_account.data[0].primary_blob_endpoint : null
}

output "storage_queue_url" {
  description = "HTTPS Queue endpoint."
  value       = var.deploy_platform ? azurerm_storage_account.data[0].primary_queue_endpoint : null
}

output "api_identity_client_id" {
  description = "Client ID for the API workload identity."
  value       = var.deploy_platform ? azurerm_user_assigned_identity.api[0].client_id : null
}

output "worker_identity_client_id" {
  description = "Client ID for the worker workload identity."
  value       = var.deploy_platform ? azurerm_user_assigned_identity.worker[0].client_id : null
}

output "github_deploy_identity_client_id" {
  description = "Client ID for GitHub Actions OIDC deployment."
  value       = var.deploy_platform ? azurerm_user_assigned_identity.github[0].client_id : null
}

output "github_cleanup_identity_client_id" {
  description = "Client ID for the resource-group-scoped cleanup identity."
  value       = var.deploy_platform && var.enable_scheduled_cleanup ? azurerm_user_assigned_identity.cleanup[0].client_id : null
}
