# Reapplying the `handlePacket` status-cache fix

Firmware 0.3.0 on this grill has a bug in `init.js` (`handlePacket`) where
the status cache key is computed but never assigned:

```js
getStatusKey(pck.at(1));        // bug: return value discarded
```

should be:

```js
key = getStatusKey(pck.at(1));  // fix
```

Because of the bug, `lastStatus.sc_11`/`sc_12` never populate, so
`PB.GetState` (and therefore this Home Assistant integration) always sees
empty status/temperature strings, even though the grill and its UART link
to the WiFi module are healthy. Full root-cause writeup:
`trail/2026-07-31-firmware-status-cache-bug.md`.

This patch lives only in the device's filesystem. **It will be silently
overwritten by any future official OTA update from Dansons.** If the bug
reappears after an update, check `PB.GetFirmwareVersion` first — if the
version is still `0.3.0`, this exact patched file can likely be reapplied
as-is; if the version has changed, re-diff against a fresh pull of
`init.js` before assuming the same one-line fix still applies.

Files in this directory:

- `init_0.3.0_original.js` — the broken file as shipped, 11067 bytes,
  SHA256 `f81d29d46b88aa0e1fd49dbaacc62ab326ac327ab305461d6cb9d1c211785dbd`
- `init_0.3.0_patched.js` — the fixed file, 11073 bytes,
  SHA256 `48a1e241c1cb2077abdfe79a3bec9af96f3c72fb4d716a2a1f794f59204a4588`

## Prerequisites

- The grill's local IP (replace `10.10.10.10` below with the current one).
- PowerShell with network access to the grill.
- A local copy of `init_0.3.0_patched.js` from this directory (copy it to
  `$HOME\init_patched.js`, or adjust the path in the script below).

## Why chunked, verified writes are required

This device's RPC channel has a small frame-size limit (`max_frame_size:
4096` in `Config.Get`), and the ESP32 has very little free RAM. Writing
more than ~1200-1500 raw bytes in a single `FS.Put` call has been observed
to silently drop the connection **and lose the bytes for that chunk**,
even though the HTTP response for reads at larger sizes works fine. Do not
increase the chunk size below without re-validating on a throwaway test
file first (see the full investigation trail entry for the validation
process used to arrive at 1200 bytes).

## Procedure

```powershell
$grillIp = "10.10.10.10"

function Get-DeviceFile($filename) {
  $offset = 0
  $bytes = New-Object System.Collections.Generic.List[byte]
  while ($true) {
    $body = @{ filename = $filename; offset = $offset; len = 4000 } | ConvertTo-Json
    $resp = Invoke-WebRequest -UseBasicParsing -TimeoutSec 10 -Method Post -Uri "http://$grillIp/rpc/FS.Get" -Body $body -ContentType "application/json"
    $json = $resp.Content | ConvertFrom-Json
    $chunk = [Convert]::FromBase64String($json.data)
    $bytes.AddRange($chunk)
    $offset += $chunk.Length
    if ($json.left -eq 0) { break }
  }
  return $bytes.ToArray()
}

function Put-DeviceFileVerified($filename, $bytes) {
  $chunkSize = 1200
  $offset = 0
  $first = $true
  while ($offset -lt $bytes.Length) {
    $len = [Math]::Min($chunkSize, $bytes.Length - $offset)
    $chunk = $bytes[$offset..($offset + $len - 1)]
    $data = [Convert]::ToBase64String($chunk)
    $body = @{ filename = $filename; data = $data; append = -not $first } | ConvertTo-Json
    $resp = Invoke-WebRequest -UseBasicParsing -TimeoutSec 10 -Method Post -Uri "http://$grillIp/rpc/FS.Put" -Body $body -ContentType "application/json"
    $offset += $len
    $first = $false

    $listing = (Invoke-WebRequest -UseBasicParsing -TimeoutSec 10 "http://$grillIp/rpc/FS.ListExt").Content | ConvertFrom-Json
    $currentSize = ($listing | Where-Object { $_.name -eq $filename }).size
    Write-Host "offset $offset -> put:" $resp.Content "| actual size:" $currentSize "(expected $offset)"
    if ($currentSize -ne $offset) {
      throw "SIZE MISMATCH at offset $offset (got $currentSize) - STOPPING, do not continue"
    }
  }
}

# 1. Confirm firmware version before assuming this patch still applies
(Invoke-WebRequest -UseBasicParsing -TimeoutSec 10 "http://$grillIp/rpc/PB.GetFirmwareVersion").Content

# 2. Back up whatever is currently on the device before overwriting it
$currentBytes = Get-DeviceFile "init.js"
[System.IO.File]::WriteAllBytes("$HOME\init_before_reapply_$(Get-Date -Format yyyyMMdd_HHmmss).js", $currentBytes)
Write-Host "Current on-device init.js SHA256:" (Get-FileHash "$HOME\init_before_reapply_*.js" -Algorithm SHA256 | Select-Object -Last 1).Hash

# 3. Write the known-good patched file
$patchedBytes = [System.IO.File]::ReadAllBytes("$HOME\init_patched.js")
Put-DeviceFileVerified "init.js" $patchedBytes

# 4. Verify byte-for-byte before rebooting
$roundTrip = Get-DeviceFile "init.js"
[System.IO.File]::WriteAllBytes("$HOME\init_live_roundtrip.js", $roundTrip)
Write-Host "Live init.js SHA256:" (Get-FileHash "$HOME\init_live_roundtrip.js" -Algorithm SHA256).Hash
# Expect: 48A1E241C1CB2077ABDFE79A3BEC9AF96F3C72FB4D716A2A1F794F59204A4588

# 5. Only once the hash matches, reboot
(Invoke-WebRequest -UseBasicParsing -TimeoutSec 10 "http://$grillIp/rpc/Sys.Reboot").Content

# 6. Wait ~20-30s, then verify recovery
Start-Sleep -Seconds 25
(Invoke-WebRequest -UseBasicParsing -TimeoutSec 10 "http://$grillIp/rpc/RPC.Ping").Content
(Invoke-WebRequest -UseBasicParsing -TimeoutSec 10 "http://$grillIp/rpc/PB.GetFirmwareVersion").Content
Start-Sleep -Seconds 10
(Invoke-WebRequest -UseBasicParsing -TimeoutSec 10 "http://$grillIp/rpc/PB.GetState").Content
# Expect: sc_11 / sc_12 populated with real FE0B.../FE0C... hex, not empty strings
```

## Rollback

If anything looks wrong after reboot, push the pre-reapply backup written
in step 2 back the same way (`Put-DeviceFileVerified "init.js"
$currentBytes`, or read from the timestamped backup file) and reboot again.
