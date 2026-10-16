variable "subscription_id" {
  description = "Azure subscription that will host the demo VM."
  type        = string
}

variable "location" {
  description = "Azure region for the resource group and VM."
  type        = string
}

variable "vm_size" {
  description = "Azure VM size. The demo uses Standard_D4s_v5."
  type        = string
}

variable "windows_sku" {
  description = "Windows 11 Pro SKU from the MicrosoftWindowsDesktop offer."
  type        = string
}

variable "admin_username" {
  description = "Local Windows administrator for RDP."
  type        = string
  sensitive   = true
}

variable "admin_password" {
  description = "Local Windows administrator password."
  type        = string
  sensitive   = true
}

variable "rdp_source_cidr" {
  description = "CIDR allowed to open Remote Desktop to the VM."
  type        = string
}

variable "resource_group_name" {
  description = "Resource group created for the demo."
  type        = string
}

variable "name_prefix" {
  description = "Prefix for Azure resource names inside the resource group."
  type        = string
}

variable "schema_manager_windows_url" {
  description = "Direct download URL for the Windows schema builder executable."
  type        = string
}
