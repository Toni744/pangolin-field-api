output "resource_group_name" {
  description = "Resource group containing the demo resources."
  value       = var.deploy_platform ? azurerm_resource_group.demo[0].name : null
}

output "container_registry_login_server" {
  description = "ACR login server for building and pushing the API image."
  value       = var.deploy_platform ? azurerm_container_registry.api[0].login_server : null
}

output "storage_account_name" {
  description = "Storage account holding private sample objects."
  value       = var.deploy_platform ? azurerm_storage_account.samples[0].name : null
}

output "container_app_fqdn" {
  description = "Internal Container App FQDN; ingress is intentionally not public."
  value       = var.deploy_api ? azurerm_container_app.api[0].latest_revision_fqdn : null
}
