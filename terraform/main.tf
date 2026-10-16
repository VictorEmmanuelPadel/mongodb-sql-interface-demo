locals {
  bootstrap = <<-EOT
    $env:SCHEMA_URL = '${var.schema_manager_windows_url}'
    $env:ADMIN_USER = '${var.admin_username}'
    ${file("${path.module}/scripts/install-demo-tools.ps1")}
  EOT
}

resource "azurerm_resource_group" "demo" {
  name     = var.resource_group_name
  location = var.location

  tags = {
    project = "sql-interface-demo"
  }
}

resource "azurerm_virtual_network" "demo" {
  name                = "${var.name_prefix}-vnet"
  resource_group_name = azurerm_resource_group.demo.name
  location            = azurerm_resource_group.demo.location
  address_space       = ["10.40.0.0/16"]
}

resource "azurerm_subnet" "demo" {
  name                 = "${var.name_prefix}-subnet"
  resource_group_name  = azurerm_resource_group.demo.name
  virtual_network_name = azurerm_virtual_network.demo.name
  address_prefixes     = ["10.40.1.0/24"]
}

resource "azurerm_network_security_group" "demo" {
  name                = "${var.name_prefix}-nsg"
  resource_group_name = azurerm_resource_group.demo.name
  location            = azurerm_resource_group.demo.location

  security_rule {
    name                       = "RDP"
    priority                   = 1000
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "3389"
    source_address_prefix      = var.rdp_source_cidr
    destination_address_prefix = "*"
  }
}

resource "azurerm_public_ip" "demo" {
  name                = "${var.name_prefix}-pip"
  resource_group_name = azurerm_resource_group.demo.name
  location            = azurerm_resource_group.demo.location
  allocation_method   = "Static"
  sku                 = "Standard"
}

resource "azurerm_network_interface" "demo" {
  name                = "${var.name_prefix}-nic"
  resource_group_name = azurerm_resource_group.demo.name
  location            = azurerm_resource_group.demo.location

  ip_configuration {
    name                          = "primary"
    subnet_id                     = azurerm_subnet.demo.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.demo.id
  }
}

resource "azurerm_network_interface_security_group_association" "demo" {
  network_interface_id      = azurerm_network_interface.demo.id
  network_security_group_id = azurerm_network_security_group.demo.id
}

resource "azurerm_windows_virtual_machine" "demo" {
  name                = "${var.name_prefix}-vm"
  computer_name       = "sqldemo"
  resource_group_name = azurerm_resource_group.demo.name
  location            = azurerm_resource_group.demo.location
  size                = var.vm_size
  admin_username      = var.admin_username
  admin_password      = var.admin_password
  secure_boot_enabled = true
  vtpm_enabled        = true

  # Decoded on the VM as C:\AzureData\CustomData.bin and run by the extension below.
  custom_data = base64encode(local.bootstrap)

  network_interface_ids = [azurerm_network_interface.demo.id]

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "StandardSSD_LRS"
    disk_size_gb         = 128
  }

  source_image_reference {
    publisher = "MicrosoftWindowsDesktop"
    offer     = "windows-11"
    sku       = var.windows_sku
    version   = "latest"
  }

  patch_mode                = "Manual"
  automatic_updates_enabled = false
  provision_vm_agent        = true

  depends_on = [azurerm_network_interface_security_group_association.demo]
}

resource "azurerm_virtual_machine_extension" "install" {
  name                 = "install-sql-demo-tools"
  virtual_machine_id   = azurerm_windows_virtual_machine.demo.id
  publisher            = "Microsoft.Compute"
  type                 = "CustomScriptExtension"
  type_handler_version = "1.10"

  settings = jsonencode({
    commandToExecute = "powershell.exe -NoProfile -ExecutionPolicy Bypass -Command \"New-Item -ItemType Directory -Force -Path C:\\SQLInterfaceDemo | Out-Null; Copy-Item -Force C:\\AzureData\\CustomData.bin C:\\SQLInterfaceDemo\\install.ps1; powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\\SQLInterfaceDemo\\install.ps1\""
  })

  timeouts {
    create = "90m"
    update = "90m"
    delete = "30m"
  }
}
