Write-Host "Creating capabilities update script..."

$newCapabilities = @(
    @{
        Id = "azure_resources.inventory_vnet"
        Name = "Inventory Virtual Networks"
        ToolName = "inventory_virtual_networks"
        Category = "azure_resources"
        Description = "Discovers Azure Virtual Network (VNet) configurations including address spaces, subnets, network security groups, and routing through the Azure Resource Graph API."
        Risk = "read_only"
        Status = "enabled"
        RequiresApproval = $false
        ExecutionEnabled = $true
        InputSchemaType = "object"
        InputProperties = @(@{Property = "subscription_id"; Type = "string"}, @{Property = "resource_group"; Type = "string"})
        RequiredFields = @()
        Limitations = @("Reads only Azure resource metadata; no sensitive secrets.", "Requires authenticated Azure profile with Reader role.")
    },
    @{
        Id = "azure_resources.inventory_storage"
        Name = "Inventory Storage Accounts"
        ToolName = "inventory_storage_accounts"
        Category = "azure_resources"
        Description = "Lists Azure storage accounts with type (Blob, File, Queue, Table), SKU tier, redundancy level, and networking rules configuration."
        Risk = "read_only"
        Status = "enabled"
        RequiresApproval = $false
        ExecutionEnabled = $true
        InputSchemaType = "object"
        InputProperties = @(@{Property = "subscription_id"; Type = "string"})
        RequiredFields = @()
        Limitations = @("Storage account names and keys are not exposed.", "Requires authenticated profile with storage read access.")
    }
)

Write-Host "Created $($newCapabilities.Count) initial capabilities"

$newCapabilities[0] | ConvertTo-Json -Depth 10
