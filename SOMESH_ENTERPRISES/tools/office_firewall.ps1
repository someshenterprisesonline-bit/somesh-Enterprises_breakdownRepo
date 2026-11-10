<#
  SOMESH ENTERPRISES - Windows Firewall for the Admin PC (run once, as Administrator).

  Allows the app's ports (default 8080 and 8443) from the LOCAL SUBNET only, on Private/Domain networks.
  The office Wi-Fi/Ethernet must be set to "Private" in Windows Settings > Network > Properties.

    powershell -ExecutionPolicy Bypass -File tools\office_firewall.ps1
    powershell -ExecutionPolicy Bypass -File tools\office_firewall.ps1 -BlockMySQLFromLan
    powershell -ExecutionPolicy Bypass -File tools\office_firewall.ps1 -Remove

  -BlockMySQLFromLan adds a rule that blocks other computers from MySQL (TCP 3306/33060). This app does not use MySQL;
  programs on this PC can still reach it through localhost.
#>
#Requires -RunAsAdministrator
param(
  [int[]]$Ports = @(8080, 8443),
  [switch]$BlockMySQLFromLan,
  [switch]$Remove
)
$Name = 'SOMESH ENTERPRISES (LAN)'
$MySqlName = 'SOMESH - block MySQL from LAN'
Get-NetFirewallRule -DisplayName $Name -ErrorAction SilentlyContinue | Remove-NetFirewallRule
if ($Remove) {
  Get-NetFirewallRule -DisplayName $MySqlName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
  Write-Host 'Removed the SOMESH firewall rules.'
  return
}
New-NetFirewallRule -DisplayName $Name -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Ports `
  -RemoteAddress LocalSubnet -Profile Private,Domain | Out-Null
Write-Host ("Allowed TCP " + ($Ports -join ', ') + " from the local subnet on Private/Domain networks.")
if ($BlockMySQLFromLan) {
  Get-NetFirewallRule -DisplayName $MySqlName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
  New-NetFirewallRule -DisplayName $MySqlName -Direction Inbound -Action Block -Protocol TCP -LocalPort 3306,33060 `
    -RemoteAddress Any -Profile Any | Out-Null
  Write-Host 'Blocked inbound MySQL (3306, 33060) from other computers.'
}
$profiles = Get-NetConnectionProfile | Select-Object InterfaceAlias, NetworkCategory
$profiles | Format-Table -AutoSize
if ($profiles | Where-Object NetworkCategory -eq 'Public') {
  Write-Warning 'A network is set to Public. Employees cannot connect through it until it is set to Private.'
}
