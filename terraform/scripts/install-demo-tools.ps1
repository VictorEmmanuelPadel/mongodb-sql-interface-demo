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

function Ensure-UserProfile([string]$User) {
    $sid = (New-Object System.Security.Principal.NTAccount($User)).Translate(
        [System.Security.Principal.SecurityIdentifier]).Value
    $profileKey = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\$sid"
    if (Test-Path $profileKey) {
        $existing = (Get-ItemProperty $profileKey).ProfileImagePath
        if ($existing -and (Test-Path $existing)) {
            return $existing
        }
    }
    if (-not ('UserEnvProfile' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Text;
public static class UserEnvProfile {
    [DllImport("userenv.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern int CreateProfile(string sid, string userName, StringBuilder profilePath, uint capacity);
}
'@
    }
    $path = New-Object System.Text.StringBuilder 260
    $result = [UserEnvProfile]::CreateProfile($sid, $User, $path, [uint32]$path.Capacity)
    if ($result -ne 0) {
        throw "Could not create the Windows profile for $User. Error 0x$($result.ToString('X8'))"
    }
    return $path.ToString()
}

if (-not $env:SCHEMA_URL -or -not $env:ADMIN_USER) {
    throw 'SCHEMA_URL and ADMIN_USER must be set.'
}

Write-Output 'Installing Microsoft Visual C++ Redistributable'
$vcRedist = Join-Path $env:TEMP 'vc_redist.x64.exe'
Get-File 'https://aka.ms/vc14/vc_redist.x64.exe' $vcRedist
$vc = Start-Process -FilePath $vcRedist -ArgumentList '/install','/quiet','/norestart' -Wait -PassThru
Assert-Exit $vc.ExitCode 'VC++ redistributable'

Write-Output 'Installing MongoDB ODBC driver'
$odbc = Join-Path $env:TEMP 'mongoodbc.msi'
Get-File 'https://downloads.mongodb.org/mongosql-odbc-driver/windows/3.0.0/release/mongoodbc-3.0.0.msi' $odbc
$odbcLog = Join-Path $Root 'odbc-install.log'
$msi = Start-Process -FilePath 'msiexec.exe' -ArgumentList @('/i', $odbc, '/qn', '/norestart', '/l*v', $odbcLog) -Wait -PassThru
Assert-Exit $msi.ExitCode 'ODBC driver'

$driverKey = Get-ItemProperty 'HKLM:\SOFTWARE\ODBC\ODBCINST.INI\ODBC Drivers'
$installed = @($driverKey.PSObject.Properties | Where-Object { $_.Name -match 'MongoDB' -and $_.Value -eq 'Installed' })
if ($installed.Count -eq 0) {
    throw 'MongoDB ODBC driver did not register. See C:\SQLInterfaceDemo\odbc-install.log'
}
Write-Output "ODBC driver registered: $($installed[0].Name)"

Write-Output 'Installing Power BI Desktop'
$powerBiSetup = Join-Path $env:TEMP 'PBIDesktopSetup_x64.exe'
Get-File 'https://download.microsoft.com/download/8/8/0/880bca75-79dd-466a-927d-1abf1f5454b0/PBIDesktopSetup_x64.exe' $powerBiSetup
$powerBiInstall = Start-Process -FilePath $powerBiSetup -ArgumentList '-quiet','-norestart','ACCEPT_EULA=1' -Wait -PassThru
Assert-Exit $powerBiInstall.ExitCode 'Power BI Desktop'

$powerBi = 'C:\Program Files\Microsoft Power BI Desktop\bin\PBIDesktop.exe'
if (-not (Test-Path $powerBi)) {
    throw 'Power BI Desktop was not found after installation.'
}

# Thumbprint published by the MongoDB Power BI connector so Power BI can load it.
New-Item -Path 'HKLM:\SOFTWARE\Policies\Microsoft\Power BI Desktop' -Force | Out-Null
New-ItemProperty -Path 'HKLM:\SOFTWARE\Policies\Microsoft\Power BI Desktop' -Name 'TrustedCertificateThumbprints' -PropertyType MultiString -Value @('8E255070BD89A7249A5B2EC5CF22BF6D84BDF80F') -Force | Out-Null

# The silent Power BI install runs as SYSTEM, before this account has signed in,
# so it does not create the per-user Custom Connectors folder.
Write-Output "Creating the Windows profile for $($env:ADMIN_USER)"
$profilePath = Ensure-UserProfile $env:ADMIN_USER
$connectorDir = Join-Path $profilePath 'Documents\Power BI Desktop\Custom Connectors'
New-Item -ItemType Directory -Force -Path $connectorDir | Out-Null
Write-Output 'Installing the MongoDB Power BI connector'
$connector = Join-Path $connectorDir 'MongoDBAtlasODBC.pqx'
Get-File 'https://downloads.mongodb.org/mongo-powerbi-connector/MongoDBAtlasODBC-1.2.2.pqx' $connector
Unblock-File -Path $connector

Write-Output 'Installing the schema builder'
Get-File $env:SCHEMA_URL (Join-Path $Root 'mongodb-schema-manager.exe')
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut('C:\Users\Public\Desktop\Power BI Desktop.lnk')
$shortcut.TargetPath = $powerBi
$shortcut.Save()

Set-Content -Path (Join-Path $Root 'install-complete.txt') -Value (Get-Date -Format o) -Encoding ASCII
Write-Output "Install complete. Power BI: $powerBi"
Stop-Transcript
