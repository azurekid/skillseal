# Install the standalone skillseal for the current Windows user.
# No Python and no admin rights needed. Puts skillseal.exe in %LOCALAPPDATA%\Programs\skillseal
# and adds that folder to your user PATH.
#
#   Online:   irm https://raw.githubusercontent.com/azurekid/skillseal/main/install.ps1 | iex
#   Offline:  .\install.ps1 -ZipPath .\skillseal-windows-x64.zip
#   Version:  & ([scriptblock]::Create((irm https://raw.githubusercontent.com/azurekid/skillseal/main/install.ps1))) -Version v0.2.0
param(
    [string]$Version = "latest",
    [string]$ZipPath = "",
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA "Programs\skillseal")
)

# Runs in a child scope so `irm | iex` does not change preferences in your session.
& {
    $ErrorActionPreference = "Stop"
    $ProgressPreference = "SilentlyContinue"
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

    $repo = "azurekid/skillseal"
    $asset = "skillseal-windows-x64.zip"
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ("skillseal-" + [guid]::NewGuid())
    New-Item -ItemType Directory -Path $tmp | Out-Null

    try {
        if ($ZipPath) {
            $zip = (Resolve-Path $ZipPath).Path
            Write-Host "Using local file $zip (check its SHA256 yourself: Get-FileHash $ZipPath)"
        } else {
            $base = if ($Version -eq "latest") { "https://github.com/$repo/releases/latest/download" } else { "https://github.com/$repo/releases/download/$Version" }
            $zip = Join-Path $tmp $asset
            Write-Host "Downloading $base/$asset"
            Invoke-WebRequest -UseBasicParsing -Uri "$base/$asset" -OutFile $zip
            Invoke-WebRequest -UseBasicParsing -Uri "$base/SHA256SUMS.txt" -OutFile (Join-Path $tmp "SHA256SUMS.txt")
            $line = Get-Content (Join-Path $tmp "SHA256SUMS.txt") | Where-Object { $_ -match ("\s\*?" + [regex]::Escape($asset) + "$") } | Select-Object -First 1
            if (-not $line) { throw "No checksum for $asset in SHA256SUMS.txt" }
            $expected = ($line -split "\s+")[0].ToLowerInvariant()
            $actual = (Get-FileHash -Algorithm SHA256 -Path $zip).Hash.ToLowerInvariant()
            if ($actual -ne $expected) { throw "Checksum mismatch for ${asset}: expected $expected, got $actual" }
            Write-Host "Checksum OK ($actual)"
        }

        $unpacked = Join-Path $tmp "unpacked"
        Expand-Archive -Path $zip -DestinationPath $unpacked -Force
        $source = Join-Path $unpacked "skillseal"
        if (-not (Test-Path (Join-Path $source "skillseal.exe"))) { throw "$zip does not contain skillseal\skillseal.exe" }

        if (Test-Path $InstallDir) {
            try { Remove-Item -Recurse -Force $InstallDir }
            catch { throw "Cannot replace $InstallDir. Close your AI agents (they run skillseal.exe) and try again." }
        }
        New-Item -ItemType Directory -Force -Path (Split-Path $InstallDir) | Out-Null
        Move-Item -Path $source -Destination $InstallDir
        Get-ChildItem -Recurse -File $InstallDir | Unblock-File

        $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
        $parts = @($userPath -split ";" | Where-Object { $_ })
        if ($parts -notcontains $InstallDir) {
            [Environment]::SetEnvironmentVariable("Path", (($parts + $InstallDir) -join ";"), "User")
            Write-Host "Added $InstallDir to your user PATH. Open a new terminal to use it."
        }
        if (($env:Path -split ";") -notcontains $InstallDir) { $env:Path = "$env:Path;$InstallDir" }

        & (Join-Path $InstallDir "skillseal.exe") --version
        if (-not $?) { throw "skillseal.exe did not start. Your device may block unsigned programs (Smart App Control, AppLocker or WDAC)." }
        Write-Host "Installed: $(Join-Path $InstallDir 'skillseal.exe')"
    } finally {
        Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    }
}
