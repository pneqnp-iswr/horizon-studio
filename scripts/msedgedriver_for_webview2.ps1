<#
.SYNOPSIS
  Prints the path of an msedgedriver.exe that matches the installed WebView2 runtime.

.DESCRIPTION
  tauri-driver drives the Horizon Studio window on Windows through msedgedriver, which only works with
  a WebView2 runtime of the same major version. The runner's preinstalled driver follows Edge, not
  WebView2, so this uses it only when the major versions agree and otherwise downloads the driver for
  the exact runtime version from Microsoft. Diagnostics go to the host; the only output is the path.
#>
param([Parameter(Mandatory = $true)][string]$Destination)
$ErrorActionPreference = 'Stop'

$client = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
$keys = @("HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\$client",
          "HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\$client",
          "HKCU:\Software\Microsoft\EdgeUpdate\Clients\$client")
$runtime = $null
foreach ($key in $keys) {
  $value = (Get-ItemProperty -Path $key -Name pv -ErrorAction SilentlyContinue).pv
  if ($value -and $value -ne '0.0.0.0') { $runtime = $value; break }
}
if (-not $runtime) { throw 'No WebView2 runtime is installed' }
Write-Host "WebView2 runtime $runtime"
$major = $runtime.Split('.')[0]

function Get-DriverVersion([string]$path) {
  $text = & $path --version 2>$null
  if ($text -match '(\d+\.\d+\.\d+\.\d+)') { return $Matches[1] }
  return $null
}

$preinstalled = if ($env:EDGEWEBDRIVER) { Join-Path $env:EDGEWEBDRIVER 'msedgedriver.exe' } else { $null }
if ($preinstalled -and (Test-Path $preinstalled)) {
  $version = Get-DriverVersion $preinstalled
  Write-Host "Preinstalled msedgedriver $version"
  if ($version -and $version.Split('.')[0] -eq $major) { return (Resolve-Path $preinstalled).Path }
}

New-Item -ItemType Directory -Force -Path $Destination | Out-Null
$archive = Join-Path $Destination 'edgedriver_win64.zip'
$sources = @("https://msedgedriver.microsoft.com/$runtime/edgedriver_win64.zip",
             "https://msedgedriver.azureedge.net/$runtime/edgedriver_win64.zip")
$downloaded = $false
foreach ($url in $sources) {
  try {
    Invoke-WebRequest -Uri $url -OutFile $archive -UseBasicParsing
    $downloaded = $true
    Write-Host "Downloaded $url"
    break
  } catch {
    Write-Host "Could not download ${url}: $_"
  }
}
if (-not $downloaded) { throw "No msedgedriver for WebView2 $runtime" }
Expand-Archive -Path $archive -DestinationPath $Destination -Force
$driver = Join-Path $Destination 'msedgedriver.exe'
$version = Get-DriverVersion $driver
Write-Host "Using msedgedriver $version"
if (-not $version -or $version.Split('.')[0] -ne $major) { throw "msedgedriver $version does not match WebView2 $runtime" }
return (Resolve-Path $driver).Path
