output "public_ip" {
  description = "Public IP address of the Power BI VM."
  value       = azurerm_public_ip.demo.ip_address
}

output "resource_group_name" {
  description = "Resource group that contains the demo VM."
  value       = azurerm_resource_group.demo.name
}

output "vm_name" {
  description = "Name of the Windows virtual machine."
  value       = azurerm_windows_virtual_machine.demo.name
}

output "admin_username" {
  description = "Local Windows account used for RDP."
  value       = var.admin_username
  sensitive   = true
}
