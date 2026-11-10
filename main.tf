locals {
  common_tags = {
    environment = "dev"
    project     = "pangolin-field-data-api"
    managed_by  = "terraform"
    owner       = "josh"
  }
}

resource "azurerm_resource_group" "demo" {
  name     = var.resource_group_name
  location = var.location
  tags     = local.common_tags
}

resource "azurerm_user_assigned_identity" "api" {
  count               = var.deploy_platform ? 1 : 0
  name                = "id-pangolin-field-api"
  location            = azurerm_resource_group.demo.location
  resource_group_name = azurerm_resource_group.demo.name
  tags                = local.common_tags
}

resource "azurerm_storage_account" "samples" {
  name                            = var.storage_account_name
  resource_group_name             = azurerm_resource_group.demo.name
  location                        = azurerm_resource_group.demo.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  https_traffic_only_enabled      = true
  shared_access_key_enabled       = false
  default_to_oauth_authentication = true
  allow_nested_items_to_be_public = false
  tags                            = local.common_tags
}

resource "azurerm_storage_container" "samples" {
  name                  = "samples"
  storage_account_id    = azurerm_storage_account.samples.id
  container_access_type = "private"
}

data "azurerm_client_config" "current" {}

resource "azurerm_role_assignment" "local_blob_data_writer" {
  scope                = azurerm_storage_account.samples.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = data.azurerm_client_config.current.object_id
  principal_type       = "User"
}

resource "azurerm_role_assignment" "blob_data_writer" {
  count                = var.deploy_platform ? 1 : 0
  scope                = azurerm_storage_account.samples.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.api[0].principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_container_registry" "api" {
  count                         = var.deploy_platform ? 1 : 0
  name                          = var.container_registry_name
  resource_group_name           = azurerm_resource_group.demo.name
  location                      = azurerm_resource_group.demo.location
  sku                           = "Basic"
  admin_enabled                 = false
  anonymous_pull_enabled        = false
  public_network_access_enabled = true
  tags                          = local.common_tags
}

resource "azurerm_role_assignment" "acr_pull" {
  count                = var.deploy_platform ? 1 : 0
  scope                = azurerm_container_registry.api[0].id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.api[0].principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_log_analytics_workspace" "demo" {
  count               = var.deploy_platform ? 1 : 0
  name                = "law-pangolin-field-api"
  location            = azurerm_resource_group.demo.location
  resource_group_name = azurerm_resource_group.demo.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  daily_quota_gb      = 1
  tags                = local.common_tags
}

resource "azurerm_container_app_environment" "demo" {
  count                      = var.deploy_platform ? 1 : 0
  name                       = "cae-pangolin-field-api"
  location                   = azurerm_resource_group.demo.location
  resource_group_name        = azurerm_resource_group.demo.name
  logs_destination           = "log-analytics"
  log_analytics_workspace_id = azurerm_log_analytics_workspace.demo[0].id
  tags                       = local.common_tags
}

resource "azurerm_container_app" "api" {
  count                        = var.deploy_api ? 1 : 0
  name                         = "app-pangolin-field-api"
  container_app_environment_id = azurerm_container_app_environment.demo[0].id
  resource_group_name          = azurerm_resource_group.demo.name
  revision_mode                = "Single"
  tags                         = local.common_tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.api[0].id]
  }

  registry {
    server   = azurerm_container_registry.api[0].login_server
    identity = azurerm_user_assigned_identity.api[0].id
  }

  template {
    min_replicas = 0
    max_replicas = 1

    container {
      name   = "field-data-api"
      image  = var.container_image
      cpu    = 0.25
      memory = "0.5Gi"

      env {
        name  = "AZURE_STORAGE_ACCOUNT_URL"
        value = azurerm_storage_account.samples.primary_blob_endpoint
      }

      env {
        name  = "BLOB_CONTAINER_NAME"
        value = azurerm_storage_container.samples.name
      }

      env {
        name  = "AZURE_CLIENT_ID"
        value = azurerm_user_assigned_identity.api[0].client_id
      }

      env {
        name  = "MAX_UPLOAD_BYTES"
        value = "104857600"
      }

      env {
        name  = "ENTRA_EXTERNAL_ID_ISSUER"
        value = var.entra_external_id_issuer
      }

      env {
        name  = "ENTRA_EXTERNAL_ID_JWKS_URL"
        value = var.entra_external_id_jwks_url
      }

      env {
        name  = "ENTRA_API_AUDIENCE"
        value = var.entra_api_audience
      }

      env {
        name  = "ENTRA_API_SCOPE"
        value = var.entra_api_scope
      }
    }
  }

  ingress {
    external_enabled = false
    target_port      = 8000
    transport        = "http"

    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  depends_on = [
    azurerm_role_assignment.acr_pull,
    azurerm_role_assignment.blob_data_writer,
  ]
}
