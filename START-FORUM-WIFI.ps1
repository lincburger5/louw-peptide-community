# Start the local forum for the one phone allowed by SETUP-PHONE-WIFI-FIREWALL.ps1.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$laptopIp = '192.168.68.112'
$phoneIp = '192.168.68.106'
$activeIp = Get-NetIPAddress -InterfaceAlias WiFi -AddressFamily IPv4 -IPAddress $laptopIp -ErrorAction SilentlyContinue
if (-not $activeIp) { throw 'Laptop Wi-Fi address changed. Update the phone firewall rule first.' }
$rule = Get-NetFirewallRule -DisplayName 'Louw Forum Phone WiFi' -ErrorAction SilentlyContinue
if (-not $rule -or $rule.Enabled -ne 'True') { throw 'Phone-only firewall rule is missing or disabled.' }
$address = $rule | Get-NetFirewallAddressFilter
if ($address.LocalAddress -ne $laptopIp -or $address.RemoteAddress -ne $phoneIp) {
  throw 'Phone-only firewall rule does not match the expected addresses.'
}
$env:FORUM_HOST = $laptopIp
$env:FORUM_TRUSTED_HOSTS = "localhost,127.0.0.1,$laptopIp"
$python = if (Test-Path '.venv\Scripts\python.exe') { '.venv\Scripts\python.exe' } else { 'python' }
Write-Host "Forum Wi-Fi address: http://${laptopIp}:5000/"
Write-Host 'Keep this window open while using the forum on your phone.'
& $python app.py run
