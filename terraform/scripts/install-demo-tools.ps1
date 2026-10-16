# Installed as SYSTEM by the Azure Custom Script Extension.
# Download URLs are injected as environment variables by Terraform.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Root = 'C:\SQLInterfaceDemo'
New-Item -ItemType Directory -Force -Path $Root | Out-Null
Start-Transcript -Path (Join-Path $Root 'install.log') -Force

function Get-File([string]$Url, [string]$Destination) {
    Write-Output "Downloading $Url"
    $lastError = $null
    foreach ($attempt in 1..3) {
        try {
            Invoke-WebRequest -Uri $Url -OutFile $Destination -UseBasicParsing
            return
        } catch {
            $lastError = $_
            Write-Output "Download attempt $attempt failed: $($_.Exception.Message)"
            Start-Sleep -Seconds (10 * $attempt)
        }
    }
    throw $lastError
}

function Assert-Exit([int]$Code, [string]$Step) {
    if ($Code -ne 0 -and $Code -ne 3010) {
        throw "$Step failed with exit code $Code"
    }
}

if (-not $env:ODBC_URL -or -not $env:CONNECTOR_URL -or -not $env:SCHEMA_URL -or -not $env:ADMIN_USER) {
    throw 'ODBC_URL, CONNECTOR_URL, SCHEMA_URL, and ADMIN_USER must be set.'
}

Write-Output 'Installing Microsoft Visual C++ Redistributable'
$vcRedist = Join-Path $env:TEMP 'vc_redist.x64.exe'
Get-File 'https://aka.ms/vs/17/release/vc_redist.x64.exe' $vcRedist
$vc = Start-Process -FilePath $vcRedist -ArgumentList '/install','/quiet','/norestart' -Wait -PassThru
Assert-Exit $vc.ExitCode 'VC++ redistributable'

Write-Output 'Installing MongoDB ODBC driver'
$odbc = Join-Path $env:TEMP 'mongoodbc.msi'
Get-File $env:ODBC_URL $odbc
$odbcLog = Join-Path $Root 'odbc-install.log'
$msi = Start-Process -FilePath 'msiexec.exe' -ArgumentList @('/i', $odbc, '/qn', '/norestart', '/l*v', $odbcLog) -Wait -PassThru
Assert-Exit $msi.ExitCode 'ODBC driver'

$driverKey = Get-ItemProperty 'HKLM:\SOFTWARE\ODBC\ODBCINST.INI\ODBC Drivers'
$installed = @($driverKey.PSObject.Properties | Where-Object { $_.Name -match 'MongoDB' -and $_.Value -eq 'Installed' })
if ($installed.Count -eq 0) {
    throw 'MongoDB ODBC driver did not register. See C:\SQLInterfaceDemo\odbc-install.log'
}
Write-Output "ODBC driver registered: $($installed[0].Name)"

Write-Output 'Installing schema builder and Power BI connector'
Get-File $env:SCHEMA_URL (Join-Path $Root 'mongodb-schema-manager.exe')
$connectorDir = Join-Path $Root 'connectors'
New-Item -ItemType Directory -Force -Path $connectorDir | Out-Null
$connector = Join-Path $connectorDir 'MongoDBAtlasODBC.pqx'
Get-File $env:CONNECTOR_URL $connector
Unblock-File -Path $connector

$destinations = @(
    "C:\Users\$($env:ADMIN_USER)\Documents\Power BI Desktop\Custom Connectors",
    "C:\Users\$($env:ADMIN_USER)\Documents\Microsoft Power BI Desktop\Custom Connectors",
    'C:\Users\Public\Documents\Power BI Desktop\Custom Connectors',
    'C:\Users\Public\Documents\Microsoft Power BI Desktop\Custom Connectors'
)
foreach ($destination in $destinations) {
    New-Item -ItemType Directory -Force -Path $destination | Out-Null
    Copy-Item $connector (Join-Path $destination 'MongoDBAtlasODBC.pqx') -Force
    Unblock-File -Path (Join-Path $destination 'MongoDBAtlasODBC.pqx')
}

# Thumbprint published by the MongoDB Power BI connector so Power BI can load it.
New-Item -Path 'HKLM:\SOFTWARE\Policies\Microsoft\Power BI Desktop' -Force | Out-Null
New-ItemProperty -Path 'HKLM:\SOFTWARE\Policies\Microsoft\Power BI Desktop' -Name 'TrustedCertificateThumbprints' -PropertyType MultiString -Value @('8E255070BD89A7249A5B2EC5CF22BF6D84BDF80F') -Force | Out-Null

$copyScript = Join-Path $Root 'copy-connector.ps1'
@'
$source = "C:\SQLInterfaceDemo\connectors\MongoDBAtlasODBC.pqx"
$docs = [Environment]::GetFolderPath("MyDocuments")
foreach ($relative in @("Power BI Desktop\Custom Connectors", "Microsoft Power BI Desktop\Custom Connectors")) {
    $target = Join-Path $docs $relative
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    Copy-Item $source (Join-Path $target "MongoDBAtlasODBC.pqx") -Force
    Unblock-File (Join-Path $target "MongoDBAtlasODBC.pqx")
}
'@ | Set-Content -Path $copyScript -Encoding ASCII
try {
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -File $copyScript"
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $principal = New-ScheduledTaskPrincipal -GroupId 'S-1-5-32-545' -RunLevel Limited
    Register-ScheduledTask -TaskName 'SQLInterfaceDemoConnector' -Action $action -Trigger $trigger -Principal $principal -Force | Out-Null
} catch {
    Write-Output "Could not register the logon task that copies the connector: $($_.Exception.Message)"
}

Write-Output 'Installing Power BI Desktop'
$choco = 'C:\ProgramData\chocolatey\bin\choco.exe'
if (-not (Test-Path $choco)) {
    Set-ExecutionPolicy Bypass -Scope Process -Force
    Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
}
& $choco install powerbi -y --no-progress --limit-output
if ($LASTEXITCODE -ne 0) {
    Write-Output 'Retrying Power BI install without checksum verification'
    & $choco install powerbi -y --no-progress --limit-output --ignore-checksums
    Assert-Exit $LASTEXITCODE 'Power BI Desktop'
}

$powerBi = 'C:\Program Files\Microsoft Power BI Desktop\bin\PBIDesktop.exe'
if (-not (Test-Path $powerBi)) {
    $store = Get-ChildItem 'C:\Program Files\WindowsApps\Microsoft.MicrosoftPowerBIDesktop*\bin\PBIDesktop.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($store) { $powerBi = $store.FullName }
}
if (-not (Test-Path $powerBi)) {
    throw 'Power BI Desktop was not found after installation.'
}
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut('C:\Users\Public\Desktop\Power BI Desktop.lnk')
$shortcut.TargetPath = $powerBi
$shortcut.Save()

Set-Content -Path (Join-Path $Root 'install-complete.txt') -Value (Get-Date -Format o) -Encoding ASCII
Write-Output "Install complete. Power BI: $powerBi"
Stop-Transcript
