# Run as Administrator only on the trusted Wi-Fi network used by this laptop and phone.
$ErrorActionPreference = 'Stop'
$ruleName = 'Louw Forum Phone WiFi'
$laptopIp = '192.168.68.112'
$phoneIp = '192.168.68.106'
$current = Get-NetIPAddress -InterfaceAlias WiFi -AddressFamily IPv4 -IPAddress $laptopIp -ErrorAction SilentlyContinue
if (-not $current) { throw 'Laptop Wi-Fi address changed. Update this script before adding a rule.' }
$existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
if ($existing) { Remove-NetFirewallRule -DisplayName $ruleName }
New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow -Protocol TCP `
  -LocalPort 5000 -LocalAddress $laptopIp -RemoteAddress $phoneIp `
  -InterfaceAlias WiFi -Profile Public | Out-Null
Write-Host "Phone-only forum firewall rule installed for $phoneIp -> ${laptopIp}:5000"
Write-Host 'Press Enter to close.'
Read-Host
