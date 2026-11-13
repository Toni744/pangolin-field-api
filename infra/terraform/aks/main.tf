locals {
  common_tags = {
    environment = "dev"
    project     = "pangolin-field-data"
    managed_by  = "terraform"
  }
  enabled = var.deploy_platform ? 1 : 0
}

resource "azurerm_resource_group" "platform" {
  count    = local.enabled
  name     = var.resource_group_name
  location = var.location
  tags     = local.common_tags
}

resource "azurerm_virtual_network" "platform" {
  count               = local.enabled
  name                = "vnet-pangolin-aks"
  address_space       = ["10.42.0.0/16"]
  location            = azurerm_resource_group.platform[0].location
  resource_group_name = azurerm_resource_group.platform[0].name
  tags                = local.common_tags
}

resource "azurerm_subnet" "aks" {
  count                = local.enabled
  name                 = "snet-aks"
  resource_group_name  = azurerm_resource_group.platform[0].name
  virtual_network_name = azurerm_virtual_network.platform[0].name
  address_prefixes     = ["10.42.0.0/22"]
  service_endpoints    = ["Microsoft.Storage"]
}

resource "azurerm_storage_account" "data" {
  count                           = local.enabled
  name                            = var.storage_account_name
  resource_group_name             = azurerm_resource_group.platform[0].name
  location                        = azurerm_resource_group.platform[0].location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  https_traffic_only_enabled      = true
  shared_access_key_enabled       = false
  default_to_oauth_authentication = true
  allow_nested_items_to_be_public = false
  public_network_access_enabled   = true

  network_rules {
    default_action             = "Deny"
    bypass                     = ["AzureServices"]
    virtual_network_subnet_ids = [azurerm_subnet.aks[0].id]
  }

  tags = local.common_tags
}

resource "azurerm_storage_container" "samples" {
  count                 = local.enabled
  name                  = "samples"
  storage_account_id    = azurerm_storage_account.data[0].id
  container_access_type = "private"
}

resource "azurerm_storage_queue" "sample_jobs" {
  count              = local.enabled
  name               = "sample-jobs"
  storage_account_id = azurerm_storage_account.data[0].id
}

resource "azurerm_storage_queue" "sample_jobs_poison" {
  count              = local.enabled
  name               = "sample-jobs-poison"
  storage_account_id = azurerm_storage_account.data[0].id
}

resource "azurerm_container_registry" "platform" {
  count                         = local.enabled
  name                          = var.container_registry_name
  resource_group_name           = azurerm_resource_group.platform[0].name
  location                      = azurerm_resource_group.platform[0].location
  sku                           = "Basic"
  admin_enabled                 = false
  anonymous_pull_enabled        = false
  public_network_access_enabled = true
  role_assignment_mode          = "LegacyRegistryPermissions"
  tags                          = local.common_tags
}

resource "azurerm_log_analytics_workspace" "platform" {
  count               = local.enabled
  name                = "law-pangolin-aks-dev"
  location            = azurerm_resource_group.platform[0].location
  resource_group_name = azurerm_resource_group.platform[0].name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  daily_quota_gb      = 1
  tags                = local.common_tags
}

resource "azurerm_user_assigned_identity" "api" {
  count               = local.enabled
  name                = "id-pangolin-api"
  location            = azurerm_resource_group.platform[0].location
  resource_group_name = azurerm_resource_group.platform[0].name
  tags                = local.common_tags
}

resource "azurerm_user_assigned_identity" "worker" {
  count               = local.enabled
  name                = "id-pangolin-worker"
  location            = azurerm_resource_group.platform[0].location
  resource_group_name = azurerm_resource_group.platform[0].name
  tags                = local.common_tags
}

resource "azurerm_user_assigned_identity" "batch" {
  count               = local.enabled
  name                = "id-pangolin-batch"
  location            = azurerm_resource_group.platform[0].location
  resource_group_name = azurerm_resource_group.platform[0].name
  tags                = local.common_tags
}

resource "azurerm_user_assigned_identity" "github" {
  count               = local.enabled
  name                = "id-pangolin-github-deploy"
  location            = azurerm_resource_group.platform[0].location
  resource_group_name = azurerm_resource_group.platform[0].name
  tags                = local.common_tags
}

resource "azurerm_kubernetes_cluster" "platform" {
  count                             = local.enabled
  name                              = "aks-pangolin-dev"
  location                          = azurerm_resource_group.platform[0].location
  resource_group_name               = azurerm_resource_group.platform[0].name
  dns_prefix                        = "pangolin-aks-dev"
  kubernetes_version                = var.kubernetes_version
  role_based_access_control_enabled = true
  local_account_disabled            = true
  oidc_issuer_enabled               = true
  workload_identity_enabled         = true
  azure_policy_enabled              = true

  api_server_access_profile {
    authorized_ip_ranges = var.api_server_authorized_ip_ranges
  }

  default_node_pool {
    name                        = "system"
    vm_size                     = var.system_node_vm_size
    node_count                  = 2
    auto_scaling_enabled        = true
    min_count                   = 2
    max_count                   = 3
    os_disk_size_gb             = 64
    vnet_subnet_id              = azurerm_subnet.aks[0].id
    temporary_name_for_rotation = "syspooltmp"
    upgrade_settings {
      max_surge = "33%"
    }
  }

  identity {
    type = "SystemAssigned"
  }

  azure_active_directory_role_based_access_control {
    admin_group_object_ids = var.aks_admin_group_object_ids
    azure_rbac_enabled     = true
  }

  network_profile {
    network_plugin      = "azure"
    network_plugin_mode = "overlay"
    network_policy      = "azure"
    pod_cidr            = "10.244.0.0/16"
    service_cidr        = "10.0.0.0/16"
    dns_service_ip      = "10.0.0.10"
    load_balancer_sku   = "standard"
    outbound_type       = "loadBalancer"
  }

  oms_agent {
    log_analytics_workspace_id      = azurerm_log_analytics_workspace.platform[0].id
    msi_auth_for_monitoring_enabled = true
  }

  tags = local.common_tags

  lifecycle {
    ignore_changes = [
      default_node_pool[0].node_count,
    ]
  }
}

resource "azurerm_kubernetes_cluster_node_pool" "gpu" {
  count                 = var.enable_gpu_node_pool ? 1 : 0
  name                  = "gpu"
  kubernetes_cluster_id = azurerm_kubernetes_cluster.platform[0].id
  vm_size               = var.gpu_node_vm_size
  mode                  = "User"
  auto_scaling_enabled  = true
  node_count            = 0
  min_count             = 0
  max_count             = 1
  os_disk_size_gb       = 128
  vnet_subnet_id        = azurerm_subnet.aks[0].id
  gpu_driver            = "Install"
  node_labels           = { accelerator = "nvidia" }
  node_taints           = ["sku=gpu:NoSchedule"]
  tags                  = local.common_tags
}

resource "azurerm_federated_identity_credential" "api" {
  count                     = local.enabled
  name                      = "fic-pangolin-api"
  user_assigned_identity_id = azurerm_user_assigned_identity.api[0].id
  issuer                    = azurerm_kubernetes_cluster.platform[0].oidc_issuer_url
  subject                   = "system:serviceaccount:pangolin:pangolin-api"
  audience                  = ["api://AzureADTokenExchange"]
}

resource "azurerm_federated_identity_credential" "worker" {
  count                     = local.enabled
  name                      = "fic-pangolin-worker"
  user_assigned_identity_id = azurerm_user_assigned_identity.worker[0].id
  issuer                    = azurerm_kubernetes_cluster.platform[0].oidc_issuer_url
  subject                   = "system:serviceaccount:pangolin:pangolin-worker"
  audience                  = ["api://AzureADTokenExchange"]
}

resource "azurerm_federated_identity_credential" "batch" {
  count                     = local.enabled
  name                      = "fic-pangolin-batch"
  user_assigned_identity_id = azurerm_user_assigned_identity.batch[0].id
  issuer                    = azurerm_kubernetes_cluster.platform[0].oidc_issuer_url
  subject                   = "system:serviceaccount:pangolin:pangolin-batch"
  audience                  = ["api://AzureADTokenExchange"]
}

resource "azurerm_federated_identity_credential" "github" {
  count                     = local.enabled
  name                      = "fic-pangolin-github-deploy"
  user_assigned_identity_id = azurerm_user_assigned_identity.github[0].id
  issuer                    = "https://token.actions.githubusercontent.com"
  subject                   = "repo:${var.github_repository}:environment:${var.github_environment}"
  audience                  = ["api://AzureADTokenExchange"]
}

resource "azurerm_role_assignment" "api_blob" {
  count                = local.enabled
  scope                = azurerm_storage_container.samples[0].id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.api[0].principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_role_assignment" "api_queue_sender" {
  count                = local.enabled
  scope                = azurerm_storage_queue.sample_jobs[0].id
  role_definition_name = "Storage Queue Data Message Sender"
  principal_id         = azurerm_user_assigned_identity.api[0].principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_role_assignment" "api_queue_reader" {
  count                = local.enabled
  scope                = azurerm_storage_queue.sample_jobs[0].id
  role_definition_name = "Storage Queue Data Reader"
  principal_id         = azurerm_user_assigned_identity.api[0].principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_role_assignment" "worker_blob" {
  count                = local.enabled
  scope                = azurerm_storage_container.samples[0].id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.worker[0].principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_role_assignment" "batch_blob" {
  count                = local.enabled
  scope                = azurerm_storage_container.samples[0].id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.batch[0].principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_role_assignment" "worker_queue_processor" {
  count                = local.enabled
  scope                = azurerm_storage_queue.sample_jobs[0].id
  role_definition_name = "Storage Queue Data Message Processor"
  principal_id         = azurerm_user_assigned_identity.worker[0].principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_role_assignment" "worker_queue_dead_letter_sender" {
  count                = local.enabled
  scope                = azurerm_storage_queue.sample_jobs_poison[0].id
  role_definition_name = "Storage Queue Data Message Sender"
  principal_id         = azurerm_user_assigned_identity.worker[0].principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_role_assignment" "acr_pull" {
  count                = local.enabled
  scope                = azurerm_container_registry.platform[0].id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_kubernetes_cluster.platform[0].kubelet_identity[0].object_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_role_assignment" "github_acr_push" {
  count                = local.enabled
  scope                = azurerm_container_registry.platform[0].id
  role_definition_name = "AcrPush"
  principal_id         = azurerm_user_assigned_identity.github[0].principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_role_assignment" "github_cluster_user" {
  count                = local.enabled
  scope                = azurerm_kubernetes_cluster.platform[0].id
  role_definition_name = "Azure Kubernetes Service Cluster User Role"
  principal_id         = azurerm_user_assigned_identity.github[0].principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_role_assignment" "github_cluster_writer" {
  count                = local.enabled
  scope                = azurerm_kubernetes_cluster.platform[0].id
  role_definition_name = "Azure Kubernetes Service RBAC Writer"
  principal_id         = azurerm_user_assigned_identity.github[0].principal_id
  principal_type       = "ServicePrincipal"
}
