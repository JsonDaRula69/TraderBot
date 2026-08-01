<#
.SYNOPSIS
    TraderBot Installer for Windows — PowerShell edition
.DESCRIPTION
    Installs TraderBot on Windows: detects OS, installs Python 3.12, uv, git,
    clones the repo, sets up a venv, creates profiles, configures API credentials,
    and registers Windows Task Scheduler jobs for background services.
.PARAMETER Uninstall
    Uninstall all TraderBot scheduled tasks and remove configuration.
.PARAMETER Update
    Pull latest from GitHub and restart scheduled tasks.
.PARAMETER Help
    Show this help message.
.EXAMPLE
    .\Install-TraderBot.ps1
    Interactive installation with prompts for profiles, API keys, and agents.
.EXAMPLE
    .\Install-TraderBot.ps1 -Uninstall
    Remove all TraderBot scheduled tasks and service artifacts.
.EXAMPLE
    .\Install-TraderBot.ps1 -Update
    Pull latest from GitHub and restart scheduled tasks.
#>

[CmdletBinding()]
param(
    [switch]$Uninstall,
    [switch]$Update,
    [switch]$Help
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

# ─── Error Reporting Logging ─────────────────────────────────────────────────

$TRADERBOT_LOG_DIR = Join-Path $env:USERPROFILE ".traderbot\logs"
$TRADERBOT_INSTALL_LOG = Join-Path $TRADERBOT_LOG_DIR "install-$(Get-Date -Format 'yyyyMMdd-HHmmss').log"
New-Item -ItemType Directory -Path $TRADERBOT_LOG_DIR -Force | Out-Null

function Write-Log {
    param(
        [string]$Level = "INFO",
        [string]$Message
    )
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logLine = "[$timestamp] [$Level] $Message"
    Add-Content -Path $TRADERBOT_INSTALL_LOG -Value $logLine -Encoding UTF8
    if ($Level -eq "ERROR") {
        $host.ui.WriteErrorLine("[ERROR] $Message")
    } elseif ($Level -eq "WARN") {
        $host.ui.WriteErrorLine("[WARN]  $Message")
    } else {
        Write-Output $Message
    }
}

function Write-LogInfo {
    param([string]$Message)
    Write-Log -Level "INFO" -Message $Message
}

function Write-LogWarn {
    param([string]$Message)
    Write-Log -Level "WARN" -Message $Message
}

function Write-LogError {
    param([string]$Message)
    Write-Log -Level "ERROR" -Message $Message
}

Write-LogInfo "Installer started. Log: $TRADERBOT_INSTALL_LOG"

# ─── Constants ───────────────────────────────────────────────────────────────

$TRADERBOT_REPO = if ($env:TRADERBOT_REPO) { $env:TRADERBOT_REPO } else { "JsonDaRula69/TraderBot" }
$TRADERBOT_ORG  = if ($env:TRADERBOT_ORG)  { $env:TRADERBOT_ORG }  else { "JsonDaRula69" }
$INSTALL_DIR    = Join-Path $env:USERPROFILE "traderbot"
$CONFIG_DIR     = Join-Path $env:USERPROFILE ".traderbot"
$TASK_PREFIX    = "TraderBot"

# ─── Help ────────────────────────────────────────────────────────────────────

if ($Help) {
    @"
Usage: .\Install-TraderBot.ps1 [OPTIONS]

TraderBot Installer — installs and configures TraderBot agents on Windows

OPTIONS:
    -Uninstall     Uninstall all TraderBot scheduled tasks and remove config
    -Update        Pull latest from GitHub and restart scheduled tasks
    -Help          Show this help message

EXAMPLES:
    .\Install-TraderBot.ps1                 Interactive install
    .\Install-TraderBot.ps1 -Uninstall      Uninstall all tasks
    .\Install-TraderBot.ps1 -Update         Update and restart tasks
"@
    exit 0
}

# ─── Admin Check ─────────────────────────────────────────────────────────────

function Test-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Admin)) {
    Write-Host "Note: Not running as Administrator. Scheduled task registration may require elevation." -ForegroundColor Yellow
    Write-Host "  Re-run as Administrator if task registration fails." -ForegroundColor Yellow
    Write-Host ""
}

# ─── OS Detection ────────────────────────────────────────────────────────────

function Get-OSPlatform {
    if ($IsWindows) { return "windows" }
    if ($IsLinux)   { return "linux" }
    if ($IsMacOS)   { return "macos" }
    return "unsupported"
}

$OS_TYPE = Get-OSPlatform
if ($OS_TYPE -ne "windows") {
    Write-LogError "This installer is for Windows only. Use traderbot-installer.sh for Linux/macOS."
    exit 2
}

Write-Host "Detected: Windows $(Get-CimInstance Win32_OperatingSystem | Select-Object -ExpandProperty Caption)" -ForegroundColor Cyan

# ─── Helper Functions ────────────────────────────────────────────────────────

function Read-Choice {
    param(
        [string]$Prompt,
        [string[]]$ValidResponses = @("y", "n"),
        [string]$Default = "y"
    )
    while ($true) {
        $response = Read-Host -Prompt $Prompt
        if ([string]::IsNullOrEmpty($response)) {
            $response = $Default
        }
        if ($ValidResponses -contains $response.ToLower()[0]) {
            return $response.ToLower()[0]
        }
        Write-Host "  Invalid selection. Enter one of: $($ValidResponses -join '/')" -ForegroundColor Yellow
    }
}

function Read-Tier {
    param(
        [string]$Prompt,
        [int]$Min = 1,
        [int]$Max = 5,
        [int]$Default = 1
    )
    while ($true) {
        $choice = Read-Host -Prompt $Prompt
        if ([string]::IsNullOrEmpty($choice)) {
            return $Default
        }
        if ($choice -match '^\d+$' -and [int]$choice -ge $Min -and [int]$choice -le $Max) {
            return [int]$choice
        }
        Write-Host "  Invalid selection. Enter a number between $Min and $Max." -ForegroundColor Yellow
    }
}

function Read-SecureLine {
    param([string]$Prompt = "")
    $secure = Read-Host -Prompt $Prompt -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}

function Read-PEMKey {
    param([string]$Prompt = "Kalshi API secret (paste PEM including BEGIN/END markers)")
    Write-Host $Prompt
    $lines = @()
    while ($true) {
        $line = [Console]::ReadLine()
        $lines += $line
        if ($line -match '-----END') { break }
        if ([string]::IsNullOrEmpty($line) -and $lines.Count -eq 1) {
            return ""
        }
    }
    return ($lines -join "`n").TrimEnd("`n")
}

function Set-EnvInFile {
    param(
        [string]$EnvFile,
        [string]$Key,
        [string]$Value
    )
    $dir = Split-Path $EnvFile -Parent
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    if (-not (Test-Path $EnvFile)) {
        New-Item -ItemType File -Path $EnvFile -Force | Out-Null
    }

    $lines = if (Test-Path $EnvFile) { Get-Content $EnvFile } else { @() }
    $found = $false
    $newLines = @()
    foreach ($line in $lines) {
        if ($line -match "^$Key=") {
            $newLines += "$Key=$Value"
            $found = $true
        } else {
            $newLines += $line
        }
    }
    if (-not $found) {
        $newLines += "$Key=$Value"
    }
    $newLines | Set-Content $EnvFile -Encoding UTF8
}

function Set-KalshiKeyring {
    <#
    .SYNOPSIS
        Store Kalshi credentials in OS keyring (Windows Credential Locker) via
        the AuthManager Python API. Falls back to .env if keyring is unavailable.
    #>
    param(
        [string]$ApiKey,
        [string]$PemContent
    )
    $venvPython = Join-Path $INSTALL_DIR ".venv\Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        return "skipped"
    }

    $keyFile = Join-Path $env:TEMP "tb-kalshi-key-tmp.txt"
    $pemFile = Join-Path $env:TEMP "tb-kalshi-pem-tmp.txt"
    [IO.File]::WriteAllText($keyFile, $ApiKey)
    [IO.File]::WriteAllText($pemFile, $PemContent)

    try {
        $result = & $venvPython -c @"
import sys; sys.path.insert(0, r'$INSTALL_DIR')
from traderbot.auth import AuthManager
mgr = AuthManager()
with open(r'$keyFile') as f: api_key = f.read().strip()
with open(r'$pemFile') as f: pem = f.read()
k = mgr.set_credential('kalshi', 'api_key', api_key)
p = mgr.set_credential('kalshi', 'private_key_pem', pem)
src = 'keyring' if k == 'keyring' and p == 'keyring' else 'env'
print(src)
"@
        return $result.Trim()
    } finally {
        Remove-Item $keyFile, $pemFile -Force -ErrorAction SilentlyContinue
    }
}

function New-TaskWrapperScript {
    <#
    .SYNOPSIS
        Create a wrapper .ps1 script that injects environment variables before
        invoking traderbot. This passes the profile token and sandbox flag
        securely through the task definition rather than .env.
    #>
    param(
        [string]$AgentName,
        [string]$TaskType,
        [string]$ProfileToken,
        [bool]$EnableSandbox = $false
    )
    $tasksDir = Join-Path $INSTALL_DIR "tasks"
    New-Item -ItemType Directory -Path $tasksDir -Force | Out-Null
    $wrapperPath = Join-Path $tasksDir "traderbot-${TaskType}-${AgentName}.ps1"

    $venvTraderBot = Join-Path $INSTALL_DIR ".venv\Scripts\traderbot.exe"
    $actionArgs = switch ($TaskType) {
        "agent"     { "scan --continuous" }
        "heartbeat" { "scan --heartbeat" }
        "news"      { "news ingest" }
        default     { "scan --continuous" }
    }

    $wrapperContent = @"
# Auto-generated by TraderBot Installer — do not edit manually
`$env:TRADERBOT_PROFILE_TOKEN = '$ProfileToken'
if (`$env:ENABLE_SANDBOX -eq '') {
    `$env:ENABLE_SANDBOX = '$(&{ if ($EnableSandbox) { "1" } else { "" } })'
}
if (`$env:ENABLE_SANDBOX -ne '0') {
    & '$venvTraderBot' sandbox enter 2>`$null | Out-Null
}
& '$venvTraderBot' $actionArgs
exit `$LASTEXITCODE
"@
    [IO.File]::WriteAllText($wrapperPath, $wrapperContent)
    return $wrapperPath
}

function Add-ToUserPath {
    param([string]$Directory)
    $currentPath = [Environment]::GetEnvironmentVariable("PATH", "User")
    if ($currentPath -split ';' -notcontains $Directory) {
        [Environment]::SetEnvironmentVariable("PATH", "$currentPath;$Directory", "User")
        $env:PATH = "$env:PATH;$Directory"
        return $true
    }
    return $false
}

function Get-ScheduledTaskByPrefix {
    param([string]$Prefix)
    $tasks = Get-ScheduledTask -TaskPath "\TraderBot\" -ErrorAction SilentlyContinue
    if ($tasks) {
        return $tasks | Where-Object { $_.TaskName -like "$Prefix*" }
    }
    return @()
}

# ─── Dependency Detection ────────────────────────────────────────────────────

function Find-Git {
    $git = Get-Command git -ErrorAction SilentlyContinue
    if ($git) { return $git.Source }
    $possible = @(
        "$env:ProgramFiles\Git\bin\git.exe",
        "$env:ProgramFiles\Git\cmd\git.exe",
        "${env:ProgramFiles(x86)}\Git\bin\git.exe"
    )
    foreach ($p in $possible) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

function Test-Command {
    param([string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Read-Readme {
    param([string]$Path)
    if (Test-Path $Path) {
        return Get-Content $Path -Raw
    }
    return ""
}

# ─── Python Detection and Installation ───────────────────────────────────────

function Find-CompatiblePython {
    <#
    .SYNOPSIS
        Find a Python 3.12 interpreter. chroma-hnswlib has no wheels for 3.13+.
    #>
    $candidates = @()

    # Python Launcher (py.exe) — check for 3.12
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        $ver = & py -3.12 --version 2>$null
        if ($LASTEXITCODE -eq 0) {
            $candidates += "py -3.12"
        }
    }

    # Standard install locations
    $paths = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "C:\Python312\python.exe",
        "$env:ProgramFiles\Python312\python.exe",
        "$env:APPDATA\Python\Python312\python.exe"
    )
    foreach ($p in $paths) {
        if (Test-Path $p) {
            $candidates += $p
        }
    }

    # winget-installed Python 3.12
    $wingetList = winget list --id Python.Python.3.12 -q 2>$null
    if ($LASTEXITCODE -eq 0 -and $wingetList -match "Python.Python.3.12") {
        foreach ($base in @("$env:LOCALAPPDATA\Programs\Python\Python312", "C:\Program Files\Python312")) {
            $exe = Join-Path $base "python.exe"
            if ((Test-Path $exe) -and ($candidates -notcontains $exe)) {
                $candidates += $exe
            }
        }
    }

    # Any python3 in PATH
    $sysPython = Get-Command python3 -ErrorAction SilentlyContinue
    if ($sysPython) {
        $ver = & python3 --version 2>$null
        if ($ver -match "3\.12") {
            $candidates += $sysPython.Source
        }
    }

    # Any python in PATH
    $sysPython = Get-Command python -ErrorAction SilentlyContinue
    if ($sysPython) {
        $ver = & python --version 2>$null
        if ($ver -match "3\.12") {
            if ($candidates -notcontains $sysPython.Source) {
                $candidates += $sysPython.Source
            }
        }
    }

    if ($candidates.Count -gt 0) {
        return $candidates[0]
    }
    return $null
}

function Get-PythonVersion {
    param([string]$PythonBin)
    try {
        if ($PythonBin -eq "py -3.12") {
            $output = & py -3.12 --version 2>&1
        } else {
            $output = & $PythonBin --version 2>&1
        }
        return ($output -join " ").Trim()
    } catch {
        return "unknown"
    }
}

function Install-Python312 {
    <#
    .SYNOPSIS
        Install Python 3.12 using winget or direct download from python.org.
    #>
    Write-Host "Python 3.12 not found. Attempting installation..." -ForegroundColor Yellow

    # Try winget first
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Host "Trying winget install of Python 3.12..." -ForegroundColor Cyan
        winget install --id Python.Python.3.12 --silent --accept-source-agreements --accept-package-agreements
        if ($LASTEXITCODE -eq 0) {
            # Refresh environment
            $env:PATH = [Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" + [Environment]::GetEnvironmentVariable("PATH", "User")
            $found = Find-CompatiblePython
            if ($found) {
                Write-Host "Python 3.12 installed via winget: $found" -ForegroundColor Green
                return $found
            }
        }
        Write-Host "winget install did not succeed. Trying direct download..." -ForegroundColor Yellow
    }

    # Fall back to direct download from python.org
    $url = "https://www.python.org/ftp/python/3.12.9/python-3.12.9-amd64.exe"
    $tempDir = Join-Path $env:TEMP "traderbot-install"
    New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
    $installer = Join-Path $tempDir "python-3.12.9-amd64.exe"

    Write-Host "Downloading Python 3.12.9 from python.org..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri $url -OutFile $installer -UseBasicParsing

    Write-Host "Running Python installer (silent, adds to PATH)..." -ForegroundColor Cyan
    Start-Process -FilePath $installer -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_test=0" -Wait
    Remove-Item $tempDir -Recurse -Force -ErrorAction SilentlyContinue

    # Refresh PATH
    $env:PATH = [Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" + [Environment]::GetEnvironmentVariable("PATH", "User")

    $found = Find-CompatiblePython
    if ($found) {
        Write-Host "Python 3.12 installed: $found" -ForegroundColor Green
        return $found
    }

    Write-LogError "Python 3.12 installation failed. Install manually from https://www.python.org/downloads/ and re-run."
    exit 3
}

function Install-Git {
    if (Find-Git) { return }
    Write-Host "Git not found. Installing..." -ForegroundColor Yellow

    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        winget install --id Git.Git --silent --accept-source-agreements
        if ($LASTEXITCODE -eq 0) {
            $env:PATH = [Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" + [Environment]::GetEnvironmentVariable("PATH", "User")
            return
        }
    }

    Write-Host "Direct download from https://git-scm.com/download/win ..." -ForegroundColor Cyan
    $url = "https://github.com/git-for-windows/git/releases/download/v2.47.0.windows.2/Git-2.47.0.2-64-bit.exe"
    $tempDir = Join-Path $env:TEMP "traderbot-install"
    New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
    $installer = Join-Path $tempDir "git-installer.exe"
    Invoke-WebRequest -Uri $url -OutFile $installer -UseBasicParsing
    Start-Process -FilePath $installer -ArgumentList '/VERYSILENT /NORESTART /NOCANCEL /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS' -Wait
    Remove-Item $tempDir -Recurse -Force -ErrorAction SilentlyContinue
    $env:PATH = [Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" + [Environment]::GetEnvironmentVariable("PATH", "User")
}

# ─── uv Installation ─────────────────────────────────────────────────────────

function Install-Uv {
    if (Test-Command uv) { return }
    Write-Host "Installing uv (Python package manager)..." -ForegroundColor Cyan

    $installScript = "https://astral.sh/uv/install.ps1"
    $tempScript = Join-Path $env:TEMP "uv-install.ps1"
    Invoke-WebRequest -Uri $installScript -OutFile $tempScript -UseBasicParsing
    & $tempScript
    Remove-Item $tempScript -Force -ErrorAction SilentlyContinue

    # Ensure uv is in PATH
    $uvDir = Join-Path $env:USERPROFILE ".cargo\bin"
    $uvExe = Join-Path $uvDir "uv.exe"
    if (Test-Path $uvExe) {
        Add-ToUserPath $uvDir
    }
    if (Test-Command uv) {
        Write-Host "uv installed successfully." -ForegroundColor Green
    } else {
        Write-Host "Warning: uv installed but not found in PATH. Restart your shell." -ForegroundColor Yellow
    }
}

# ─── TraderBot Installation ──────────────────────────────────────────────────

function Install-TraderBot {
    if (Test-Path $INSTALL_DIR) {
        if (Test-Path (Join-Path $INSTALL_DIR ".git")) {
            Write-Host "TraderBot already installed at $INSTALL_DIR" -ForegroundColor Cyan
            $update = Read-Choice -Prompt "Update to latest? (y/n): " -ValidResponses @("y", "n")
            if ($update -eq "y") {
                Write-Host "Pulling latest from GitHub..." -ForegroundColor Cyan
                Push-Location $INSTALL_DIR
                try {
                    git pull origin main 2>$null
                    if ($LASTEXITCODE -ne 0) {
                        git pull origin master 2>$null
                        if ($LASTEXITCODE -ne 0) {
                            Write-LogError "git pull failed for both 'main' and 'master' branches."
                            exit 4
                        }
                    }
                } finally {
                    Pop-Location
                }
            } else {
                Write-Host "Skipping installation." -ForegroundColor Cyan
                return
            }
        } else {
            Write-Host "Directory exists but not a git repo. Backing up and re-cloning..." -ForegroundColor Yellow
            $backup = "${INSTALL_DIR}_backup_$(Get-Date -Format 'yyyyMMddHHmmss')"
            Move-Item $INSTALL_DIR $backup
            Write-Host "Backup saved to: $backup" -ForegroundColor Cyan
            Install-FromGit
        }
    } else {
        Install-FromGit
    }
}

function Install-FromGit {
    Write-Host "Cloning TraderBot from GitHub..." -ForegroundColor Cyan
    $repoUrl = "https://github.com/${TRADERBOT_REPO}.git"
    git clone $repoUrl $INSTALL_DIR
    if ($LASTEXITCODE -ne 0) {
        # Try ZIP fallback
        Write-Host "git clone failed. Trying ZIP download..." -ForegroundColor Yellow
        $zipUrl = "https://github.com/${TRADERBOT_REPO}/archive/refs/heads/main.zip"
        $tempDir = Join-Path $env:TEMP "traderbot-install"
        New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
        $zipFile = Join-Path $tempDir "traderbot.zip"
        Invoke-WebRequest -Uri $zipUrl -OutFile $zipFile -UseBasicParsing

        Expand-Archive -Path $zipFile -DestinationPath $tempDir -Force
        $extracted = Get-ChildItem $tempDir -Directory | Select-Object -First 1
        if (-not $extracted) {
            Write-LogError "Failed to extract TraderBot archive."
            exit 3
        }
        Move-Item $extracted.FullName $INSTALL_DIR
        Remove-Item $tempDir -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "Warning: Installed via ZIP (no .git). Auto-update will not work." -ForegroundColor Yellow
        Write-Host "  To enable updates, run: cd ~/traderbot; git init; git remote add origin $repoUrl; git fetch; git checkout main" -ForegroundColor Yellow
    }
}

function Install-Dependencies {
    Write-Host "Installing Python dependencies into venv..." -ForegroundColor Cyan

    $pythonBin = Find-CompatiblePython
    if (-not $pythonBin) {
        $pythonBin = Install-Python312
    }
    Write-Host "Using Python: $pythonBin ($(Get-PythonVersion $pythonBin))" -ForegroundColor Cyan

    Push-Location $INSTALL_DIR

    try {
        # Create venv
        if (-not (Test-Path ".venv")) {
            if ($pythonBin -eq "py -3.12") {
                & py -3.12 -m venv .venv
            } else {
                & $pythonBin -m venv .venv
            }
        }

        # Find venv python
        $venvPython = Join-Path $INSTALL_DIR ".venv\Scripts\python.exe"
        if (-not (Test-Path $venvPython)) {
            Write-LogError "venv Python not found at $venvPython"
            exit 3
        }

        # Install with uv if available, fall back to pip
        if (Test-Command uv) {
            uv pip install -e .
        } else {
            & $venvPython -m pip install --upgrade pip --quiet
            & $venvPython -m pip install -e . --quiet
            if ($LASTEXITCODE -ne 0) {
                Write-LogError "pip install failed."
                exit 3
            }
        }

        # Create symlink/copy to PATH
        $venvBin = Join-Path $INSTALL_DIR ".venv\Scripts"
        $traderbotExe = Join-Path $venvBin "traderbot.exe"
        if (Test-Path $traderbotExe) {
            $userBin = Join-Path $env:USERPROFILE ".local\bin"
            New-Item -ItemType Directory -Path $userBin -Force | Out-Null
            Copy-Item $traderbotExe (Join-Path $userBin "traderbot.exe") -Force
            Add-ToUserPath $userBin
        }

        # Verify
        $tbCmd = Join-Path $venvBin "traderbot.exe"
        if (Test-Path $tbCmd) {
            $version = & $tbCmd --version 2>$null
            Write-Host "TraderBot installed successfully: $($version -join ' ')" -ForegroundColor Green
        } else {
            Write-LogError "traderbot.exe not found at $tbCmd"
            Get-ChildItem $venvBin -Filter "*.exe" | ForEach-Object { Write-Host $_.Name }
            exit 3
        }
    } finally {
        Pop-Location
    }
}

# ─── API Credential Setup ────────────────────────────────────────────────────

function Setup-APICredentials {
    $tbCmd = Join-Path $INSTALL_DIR ".venv\Scripts\traderbot.exe"
    if (-not (Test-Path $tbCmd)) {
        Write-Host "TraderBot binary not found. Skipping API credential setup." -ForegroundColor Yellow
        return
    }

    if ($env:TRADERBOT_NON_INTERACTIVE -eq "1") {
        Write-Host "Non-interactive mode — skipping API credential prompts." -ForegroundColor Cyan
        Write-Host "Set credentials later with: traderbot auth set-key" -ForegroundColor Yellow
        return
    }

    Write-Host ""
    Write-Host "=== API Credentials ===" -ForegroundColor Cyan
    Write-Host "Kalshi credentials are required. Other services are optional."
    Write-Host ""

    $envFile = Join-Path $CONFIG_DIR ".env"
    New-Item -ItemType Directory -Path $CONFIG_DIR -Force | Out-Null
    if (-not (Test-Path $envFile)) {
        New-Item -ItemType File -Path $envFile -Force | Out-Null
    }

    # --- Kalshi (required) — stored in OS keyring (or .env fallback) ---
    Write-Host "--- Kalshi (required) ---" -ForegroundColor Cyan
    $kalshiKey = ""
    while ([string]::IsNullOrEmpty($kalshiKey)) {
        $kalshiKey = Read-Host -Prompt "Kalshi API key"
        if ([string]::IsNullOrEmpty($kalshiKey)) {
            Write-Host "  Kalshi API key is required. Enter it or press Ctrl+C to abort." -ForegroundColor Yellow
        }
    }

    Write-Host "Kalshi API secret (paste the full PEM key including BEGIN/END markers):"
    $kalshiSecret = Read-PEMKey
    if (-not [string]::IsNullOrEmpty($kalshiSecret)) {
        $keyringResult = Set-KalshiKeyring -ApiKey $kalshiKey -PemContent $kalshiSecret
        if ($keyringResult -eq "keyring") {
            Write-Host "Kalshi credentials stored in Windows Credential Locker." -ForegroundColor Green
        } elseif ($keyringResult -eq "env") {
            Write-Host "Keyring unavailable — Kalshi credentials stored in .env." -ForegroundColor Yellow
        } else {
            Write-Host "Keyring not available. Skipping .env storage — use traderbot auth set-kalshi." -ForegroundColor Yellow
        }
    } else {
        Set-EnvInFile $envFile "KALSHI_API_KEY" $kalshiKey
        Write-Host "API key stored in .env. Set PEM key later with: traderbot auth set-kalshi" -ForegroundColor Yellow
    }
    Write-Host ""

    Write-Host "Select Kalshi API tier:"
    Write-Host "  1) Basic     (20 read / 10 write req/sec)  — free, 200 read + 100 write tokens/sec"
    Write-Host "  2) Advanced  (30 read / 30 write req/sec)  — 300 read + 300 write tokens/sec"
    Write-Host "  3) Premier   (100 read / 100 write req/sec) — 1000 read + 1000 write tokens/sec"
    Write-Host "  4) Paragon   (200 read / 200 write req/sec) — 2000 read + 2000 write tokens/sec"
    Write-Host "  5) Prime     (400 read / 400 write req/sec) — 4000 read + 4000 write tokens/sec"
    $tier = Read-Tier -Prompt "Tier [1]: " -Default 1 -Max 5
    $readTokens = @(200, 300, 1000, 2000, 4000)[$tier - 1]
    $writeTokens = @(100, 300, 1000, 2000, 4000)[$tier - 1]
    Set-EnvInFile $envFile "KALSHI_READ_BUDGET_TOKENS" "$readTokens"
    Set-EnvInFile $envFile "KALSHI_WRITE_BUDGET_TOKENS" "$writeTokens"

    # --- API key table: name => (env_prefix, description, optional_flag) ---
    $apiKeys = @(
        @{Name="NewsAPI"; Env="NEWSAPI_API_KEY"; Desc="NewsAPI key (press Enter to skip)"; Opt=$true},
        @{Name="Voyage"; Env="VOYAGE_API_KEY"; Desc="Voyage API key (press Enter to skip)"; Opt=$true},
        @{Name="Twitter"; Env="TWITTER_API_KEY"; Desc="Twitter API key (press Enter to skip)"; Opt=$true},
        @{Name="OpenWeatherMap"; Env="OPENWEATHER_API_KEY"; Desc="OpenWeatherMap API key (press Enter to skip)"; Opt=$true},
        @{Name="CoinGecko"; Env="COINGECKO_API_KEY"; Desc="CoinGecko API key (press Enter to skip)"; Opt=$true},
        @{Name="FRED"; Env="FRED_API_KEY"; Desc="FRED API key (press Enter to skip)"; Opt=$true}
    )

    foreach ($api in $apiKeys) {
        Write-Host ""
        Write-Host "--- $($api.Name) (optional) ---" -ForegroundColor Cyan
        $key = Read-Host -Prompt $api.Desc
        if (-not [string]::IsNullOrEmpty($key)) {
            Set-EnvInFile $envFile $api.Env $key
            Write-Host "$($api.Name) key stored." -ForegroundColor Green
        } else {
            Write-Host "Skipped. Set later with: traderbot auth set-key" -ForegroundColor Yellow
        }
    }

    # --- Reddit (needs client ID + secret) ---
    Write-Host ""
    Write-Host "--- Reddit (optional) ---" -ForegroundColor Cyan
    $redditId = Read-Host -Prompt "Reddit client ID (press Enter to skip)"
    if (-not [string]::IsNullOrEmpty($redditId)) {
        Set-EnvInFile $envFile "REDDIT_CLIENT_ID" $redditId
        $redditSecret = Read-SecureLine -Prompt "Reddit client secret"
        if (-not [string]::IsNullOrEmpty($redditSecret)) {
            Set-EnvInFile $envFile "REDDIT_CLIENT_SECRET" $redditSecret
        }
        Write-Host "Reddit credentials stored." -ForegroundColor Green
    } else {
        Write-Host "Skipped. Set later with: traderbot auth set-key reddit client_id" -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "API credential setup complete." -ForegroundColor Green
    Write-Host "Credentials written to $envFile" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Note: Keep $envFile secure. It contains sensitive credentials." -ForegroundColor Yellow
}

# ─── Interactive Config ──────────────────────────────────────────────────────

function Invoke-MasterPasswordSetup {
    <#
    .SYNOPSIS
        Mandatory PBKDF2 master password creation before any profile is created.
        Calls traderbot auth setup-master-password interactively.
    #>
    if ($env:TRADERBOT_NON_INTERACTIVE -eq "1") {
        Write-Host "Non-interactive mode — skipping master password setup." -ForegroundColor Yellow
        Write-Host "Set later with: traderbot auth setup-master-password" -ForegroundColor Yellow
        return
    }

    $tbBin = Join-Path $INSTALL_DIR ".venv\Scripts\traderbot.exe"
    if (-not (Test-Path $tbBin)) {
        Write-Host "TraderBot binary not found. Skipping master password setup." -ForegroundColor Yellow
        return
    }

    Write-Host ""
    Write-Host "=== Master Password ===" -ForegroundColor Cyan
    Write-Host "A master password is required to gate trade/simulate commands."
    Write-Host "This uses PBKDF2 key derivation to secure your master key."
    Write-Host ""

    # Check if already set up
    $alreadySetup = & $tbBin auth check-master-password --json 2>$null | ConvertFrom-Json
    if ($alreadySetup -and $alreadySetup.configured) {
        Write-Host "Master password already configured." -ForegroundColor Green
        return
    }

    $setup = Read-Choice -Prompt "Set up a master password now? (y/n): "
    if ($setup -ne "y") {
        Write-Host "Skipping master password. WARNING: trade/simulate commands will be gated." -ForegroundColor Yellow
        Write-Host "Run later: traderbot auth setup-master-password" -ForegroundColor Yellow
        return
    }

    Write-Host "Running traderbot auth setup-master-password (interactive)..." -ForegroundColor Cyan
    & $tbBin auth setup-master-password
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Master password created. Session authenticated for 30 minutes." -ForegroundColor Green
    } else {
        Write-Host "Master password setup failed (exit code $LASTEXITCODE)." -ForegroundColor Yellow
        Write-Host "Run manually: traderbot auth setup-master-password" -ForegroundColor Yellow
    }
}

function Invoke-InteractiveConfig {
    if ($env:TRADERBOT_NON_INTERACTIVE -eq "1") {
        Write-Host "=== TraderBot Configuration (non-interactive) ===" -ForegroundColor Cyan
        $profileName = if ($env:TRADERBOT_PROFILE_NAME) { $env:TRADERBOT_PROFILE_NAME } else { "default" }
        $categories = "Economics,Politics,Weather,Sports,Science_and_Technology,Crypto,Commodities,Companies,Elections,Entertainment,Financials,Health,Mentions,Social"
        $tbBin = Join-Path $INSTALL_DIR ".venv\Scripts\traderbot.exe"
        if (Test-Path $tbBin) {
            & $tbBin profile create $profileName --mode paper --categories $categories 2>&1 | Out-Host
        }
        Write-Host "Profile '$profileName' created (paper mode, all categories)." -ForegroundColor Green
        Write-Host "Set API credentials later with: traderbot auth set-key" -ForegroundColor Yellow
        return
    }

    Write-Host ""
    Write-Host "=== TraderBot Configuration ===" -ForegroundColor Cyan
    Write-Host ""

    $createProfile = Read-Choice -Prompt "Create a trading profile? (y/n): "
    if ($createProfile -ne "y") {
        Write-Host "Skipping profile creation." -ForegroundColor Yellow
        return
    }

    $profileName = ""
    while ([string]::IsNullOrEmpty($profileName)) {
        $profileName = Read-Host -Prompt "Profile name"
        if ([string]::IsNullOrEmpty($profileName)) {
            Write-Host "Profile name cannot be empty." -ForegroundColor Yellow
        }
    }

    Write-Host "Select trading mode:"
    Write-Host "  1) paper  (recommended — no real money at risk)"
    Write-Host "  2) live   (real money — use with caution)"
    $modeChoice = Read-Host -Prompt "Choice [1]: "
    $mode = if ($modeChoice -eq "2") { "live" } else { "paper" }

    Write-Host "Select market categories:"
    $categories = @(
        @{Key="economics"; Label="Economics"},
        @{Key="politics"; Label="Politics"},
        @{Key="weather"; Label="Climate and Weather"},
        @{Key="sports"; Label="Sports"},
        @{Key="science_and_technology"; Label="Science and Technology"},
        @{Key="crypto"; Label="Crypto"},
        @{Key="commodities"; Label="Commodities"},
        @{Key="companies"; Label="Companies"},
        @{Key="elections"; Label="Elections"},
        @{Key="entertainment"; Label="Entertainment"},
        @{Key="financials"; Label="Financials"},
        @{Key="health"; Label="Health"},
        @{Key="mentions"; Label="Mentions"},
        @{Key="social"; Label="Social"}
    )

    for ($i = 0; $i -lt $categories.Count; $i++) {
        $num = $i + 1
        Write-Host "  $num) $($categories[$i].Label)"
    }
    Write-Host "   a) All categories"

    $catNums = Read-Host -Prompt "Choice [a]: "
    $selected = @()
    if ([string]::IsNullOrEmpty($catNums) -or $catNums -eq "a") {
        $selected = $categories.Key
    } else {
        $nums = $catNums -split '[,\s]+' | Where-Object { $_ -match '^\d+$' } | ForEach-Object { [int]$_ }
        foreach ($n in $nums) {
            if ($n -ge 1 -and $n -le $categories.Count) {
                $selected += $categories[$n - 1].Key
            }
        }
        if ($selected.Count -eq 0) {
            $selected = $categories.Key
        }
    }
    $categoryStr = $selected -join ","

    $tbBin = Join-Path $INSTALL_DIR ".venv\Scripts\traderbot.exe"
    if (Test-Path $tbBin) {
        & $tbBin profile create $profileName --mode $mode --categories $categoryStr 2>&1 | Out-Host
    }
    Write-Host "Profile '$profileName' created ($mode mode)." -ForegroundColor Green
}

# ─── Task Scheduler Registration ─────────────────────────────────────────────

function Register-TraderBotTask {
    param(
        [string]$AgentName,
        [string]$ProfileToken,
        [string]$Interval = "HOURLY",
        [string]$TaskType = "agent",
        [bool]$EnableSandbox = $false
    )
    $taskName = "${TASK_PREFIX}-${TaskType}-${AgentName}"
    $taskPath = "\TraderBot\"

    # Create wrapper script that injects environment variables at runtime
    $venvTraderBot = Join-Path $INSTALL_DIR ".venv\Scripts\traderbot.exe"
    if (-not (Test-Path $venvTraderBot)) {
        Write-Host "Warning: traderbot.exe not found at $venvTraderBot. Skipping task registration." -ForegroundColor Yellow
        return
    }

    $wrapperScript = New-TaskWrapperScript -AgentName $AgentName -TaskType $TaskType `
        -ProfileToken $ProfileToken -EnableSandbox $EnableSandbox

    $actionArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$wrapperScript`""
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $actionArgs -WorkingDirectory $INSTALL_DIR

    # Build trigger
    $trigger = switch ($Interval) {
        "HOURLY"      { New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Minutes 60) -At (Get-Date) -Once }
        "DAILY"       { New-ScheduledTaskTrigger -Daily -At "00:00" }
        "30MINUTES"   { New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Minutes 30) -At (Get-Date) -Once }
        "15MINUTES"   { New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Minutes 15) -At (Get-Date) -Once }
        "ATLOGON"     { New-ScheduledTaskTrigger -AtLogOn }
        "ATSTARTUP"   { New-ScheduledTaskTrigger -AtStartup }
        default       { New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Minutes 60) -At (Get-Date) -Once }
    }

    # Settings
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -RestartCount 5 `
        -RestartInterval (New-TimeSpan -Minutes 10) `
        -ExecutionTimeLimit (New-TimeSpan -Days 1) `
        -MultipleInstances IgnoreNew

    # Environment variable injected via wrapper script, not .env
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

    # Ensure task folder exists
    $taskFolder = Get-ScheduledTask -TaskPath $taskPath -ErrorAction SilentlyContinue
    if (-not $taskFolder) {
        $null = Register-ScheduledTask -TaskName "_placeholder" -TaskPath $taskPath -Action $action -Trigger $trigger -Principal $principal -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName "_placeholder" -TaskPath $taskPath -Confirm:$false -ErrorAction SilentlyContinue
    }

    try {
        Register-ScheduledTask -TaskName $taskName -TaskPath $taskPath `
            -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
            -Description "TraderBot $TaskType task for agent $AgentName" -Force

        Write-Host "  Scheduled task registered: $taskPath$taskName" -ForegroundColor Green
        if ($EnableSandbox) {
            Write-Host "    Sandbox: enabled (ENABLE_SANDBOX=1)" -ForegroundColor Cyan
        }
    } catch {
        Write-Host "  Warning: Task registration failed ($_). Try running as Administrator." -ForegroundColor Yellow
    }
}

function Register-NewsIngestTask {
    param([string]$Interval = "HOURLY")
    $taskName = "${TASK_PREFIX}-news-ingest"
    $taskPath = "\TraderBot\"

    $venvTraderBot = Join-Path $INSTALL_DIR ".venv\Scripts\traderbot.exe"
    if (-not (Test-Path $venvTraderBot)) {
        Write-Host "Warning: traderbot.exe not found. Skipping news ingest task." -ForegroundColor Yellow
        return
    }

    $action = New-ScheduledTaskAction -Execute $venvTraderBot `
        -Argument "news ingest" -WorkingDirectory $INSTALL_DIR

    $trigger = New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Hours 1) `
        -At (Get-Date) -Once

    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
        -MultipleInstances IgnoreNew

    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

    try {
        Register-ScheduledTask -TaskName $taskName -TaskPath $taskPath `
            -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
            -Description "TraderBot news ingest — hourly content ingestion" -Force
        Write-Host "  Scheduled task registered: $taskPath$taskName" -ForegroundColor Green
    } catch {
        Write-Host "  Warning: News ingest task registration failed ($_)." -ForegroundColor Yellow
    }
}

function Register-HeartbeatTask {
    param(
        [string]$AgentName,
        [string]$ProfileToken,
        [string]$Interval = "15MINUTES",
        [bool]$EnableSandbox = $false
    )
    $taskName = "${TASK_PREFIX}-heartbeat-${AgentName}"
    $taskPath = "\TraderBot\"

    $venvTraderBot = Join-Path $INSTALL_DIR ".venv\Scripts\traderbot.exe"
    if (-not (Test-Path $venvTraderBot)) {
        return
    }

    $wrapperScript = New-TaskWrapperScript -AgentName $AgentName -TaskType "heartbeat" `
        -ProfileToken $ProfileToken -EnableSandbox $EnableSandbox

    $action = New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$wrapperScript`"" -WorkingDirectory $INSTALL_DIR

    $trigger = New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Minutes 15) `
        -At (Get-Date) -Once

    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
        -MultipleInstances IgnoreNew

    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

    try {
        Register-ScheduledTask -TaskName $taskName -TaskPath $taskPath `
            -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
            -Description "TraderBot heartbeat for agent $AgentName" -Force
        Write-Host "  Heartbeat task registered: $taskPath$taskName" -ForegroundColor Green
    } catch {
        Write-Host "  Warning: Heartbeat registration failed ($_)." -ForegroundColor Yellow
    }
}

# ─── Service Registration Flow ───────────────────────────────────────────────

function Invoke-AgentAssignment {
    Write-Host ""
    Write-Host "=== Agent Assignment ===" -ForegroundColor Cyan
    Write-Host ""

    $assignAgent = Read-Choice -Prompt "Assign this profile to an OpenClaw agent? (y/n): "
    if ($assignAgent -ne "y") {
        Write-Host "Skipping agent assignment." -ForegroundColor Yellow
        return
    }

    $agentName = ""
    while ([string]::IsNullOrEmpty($agentName)) {
        $agentName = Read-Host -Prompt "Agent name"
        if ([string]::IsNullOrEmpty($agentName)) {
            Write-Host "Agent name cannot be empty." -ForegroundColor Yellow
        } elseif ($agentName -notmatch '^[a-zA-Z0-9_-]+$') {
            Write-Host "Agent name contains invalid characters. Only alphanumeric, hyphens, and underscores allowed." -ForegroundColor Yellow
            $agentName = ""
        }
    }

    $profileToken = Read-Host -Prompt "Profile token"

    # --- Sandbox ---
    Write-Host ""
    $enableSandbox = $false
    $sandboxChoice = Read-Choice -Prompt "Enable agent filesystem sandbox? (y/n): " -Default "n" -ValidResponses @("y", "n")
    if ($sandboxChoice -eq "y") {
        $enableSandbox = $true
        Write-Host "Sandbox will lock src/ read-only and isolate workspace for agent tasks." -ForegroundColor Cyan
    } else {
        Write-Host "Sandbox disabled. Agent runs with full filesystem access." -ForegroundColor Yellow
    }

    # Register scheduled tasks
    Write-Host ""
    Write-Host "Registering Windows scheduled tasks..." -ForegroundColor Cyan
    Register-TraderBotTask -AgentName $agentName -ProfileToken $profileToken -Interval "HOURLY" -TaskType "agent" -EnableSandbox $enableSandbox
    Register-HeartbeatTask -AgentName $agentName -ProfileToken $profileToken -Interval "15MINUTES" -EnableSandbox $enableSandbox
    Write-Host ""

    # Register news ingest task (shared across agents)
    $existingNews = Get-ScheduledTaskByPrefix "${TASK_PREFIX}-news-ingest" 2>$null
    if (-not $existingNews) {
        Write-Host "Registering news ingest task (runs hourly)..." -ForegroundColor Cyan
        Register-NewsIngestTask -Interval "HOURLY"
        Write-Host ""
    }

    Write-Host "Agent '$agentName' configured with scheduled tasks." -ForegroundColor Green
    Write-Host "  The agent scan runs hourly via Windows Task Scheduler." -ForegroundColor Cyan
    Write-Host "  A heartbeat task runs every 15 minutes." -ForegroundColor Cyan
    Write-Host "  News ingest runs hourly (shared across all agents)." -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Check task status in Task Scheduler under: \TraderBot\" -ForegroundColor Cyan
}

# ─── Uninstall ───────────────────────────────────────────────────────────────

function Uninstall-TraderBot {
    Write-Host "=== Uninstalling TraderBot ===" -ForegroundColor Cyan

    # Remove scheduled tasks
    Write-Host "Removing scheduled tasks..." -ForegroundColor Yellow
    $tasks = Get-ScheduledTask -TaskPath "\TraderBot\" -ErrorAction SilentlyContinue
    if ($tasks) {
        foreach ($task in $tasks) {
            Write-Host "  Removing: $($task.TaskName)"
            Unregister-ScheduledTask -TaskName $task.TaskName -TaskPath "\TraderBot\" -Confirm:$false -ErrorAction SilentlyContinue
        }
    }
    # Clean up empty task folder
    try {
        schtasks /delete /tn "\TraderBot" /f 2>$null
    } catch { }

    Write-Host ""
    Write-Host "Scheduled tasks removed." -ForegroundColor Green
    Write-Host "Data preserved at:" -ForegroundColor Cyan
    Write-Host "  Installation: $INSTALL_DIR" -ForegroundColor Cyan
    Write-Host "  Configuration: $CONFIG_DIR" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "To remove completely, delete these directories manually:" -ForegroundColor Yellow
    Write-Host "  Remove-Item -Recurse -Force `"$INSTALL_DIR`"" -ForegroundColor Yellow
    Write-Host "  Remove-Item -Recurse -Force `"$CONFIG_DIR`"" -ForegroundColor Yellow
    Write-Host "  Remove-Item -Recurse -Force `"$env:USERPROFILE\.local\bin`"" -ForegroundColor Yellow
}

# ─── Update ──────────────────────────────────────────────────────────────────

function Update-TraderBot {
    Write-Host "=== Updating TraderBot ===" -ForegroundColor Cyan

    $tbBin = Join-Path $INSTALL_DIR ".venv\Scripts\traderbot.exe"

    # Verify Ed25519 trust anchor before pulling updates
    if (Test-Path $tbBin) {
        Write-Host "Verifying Ed25519 update trust anchor..." -ForegroundColor Cyan
        $trustResult = & $tbBin update --check 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  Ed25519 trust anchor verified." -ForegroundColor Green
        } else {
            Write-Host "  Warning: Update verification check failed. Proceeding with pull." -ForegroundColor Yellow
        }
    }

    # Stop scheduled tasks
    Write-Host "Stopping scheduled tasks..." -ForegroundColor Yellow
    $tasks = Get-ScheduledTask -TaskPath "\TraderBot\" -ErrorAction SilentlyContinue
    if ($tasks) {
        foreach ($task in $tasks) {
            Stop-ScheduledTask -TaskName $task.TaskName -TaskPath "\TraderBot\" -ErrorAction SilentlyContinue
        }
    }

    # Pull latest
    if (Test-Path (Join-Path $INSTALL_DIR ".git")) {
        Write-Host "Pulling latest from GitHub..." -ForegroundColor Cyan
        Push-Location $INSTALL_DIR
        try {
            git pull origin main 2>$null
            if ($LASTEXITCODE -ne 0) {
                git pull origin master 2>$null
            }
        } finally {
            Pop-Location
        }
    } else {
        Write-LogError "Not a git repository. Cannot auto-update."
        exit 4
    }

    # Re-install dependencies
    Install-Dependencies

    # Refresh TLS pin cache for Kalshi API
    $tbBin = Join-Path $INSTALL_DIR ".venv\Scripts\traderbot.exe"
    if (Test-Path $tbBin) {
        Write-Host "Refreshing Kalshi TLS pin..." -ForegroundColor Cyan
        & $tbBin auth check --service kalshi 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  TLS pin refreshed." -ForegroundColor Green
        } else {
            Write-Host "  Warning: TLS pin refresh failed (kalshi may use self-signed certs)." -ForegroundColor Yellow
        }
    }

    # Restart tasks
    Write-Host "Restarting scheduled tasks..." -ForegroundColor Cyan
    $tasks = Get-ScheduledTask -TaskPath "\TraderBot\" -ErrorAction SilentlyContinue
    if ($tasks) {
        foreach ($task in $tasks) {
            Start-ScheduledTask -TaskName $task.TaskName -TaskPath "\TraderBot\" -ErrorAction SilentlyContinue
        }
    }

    Write-Host "Update complete." -ForegroundColor Green
}

# ─── OpenClaw Check ──────────────────────────────────────────────────────────

function Test-OpenClaw {
    $ocDir = Join-Path $env:USERPROFILE ".openclaw"
    if (-not (Test-Path $ocDir)) {
        Write-Host "Note: OpenClaw directory not found at $ocDir" -ForegroundColor Yellow
        Write-Host "  TraderBot toolkit will be installed, but agent integration requires OpenClaw." -ForegroundColor Yellow
        $continue = Read-Choice -Prompt "Continue without OpenClaw? (y/n): "
        if ($continue -ne "y") {
            Write-Host "Install OpenClaw first: https://github.com/openclaw/openclaw" -ForegroundColor Cyan
            exit 0
        }
        return $false
    }
    Write-Host "OpenClaw found: $ocDir" -ForegroundColor Green
    return $true
}

# ─── Main ────────────────────────────────────────────────────────────────────

function Invoke-Install {
    Write-Host ""
    Write-Host "╔══════════════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "║           TraderBot Windows Installer               ║" -ForegroundColor Cyan
    Write-Host "╚══════════════════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""

    Test-OpenClaw | Out-Null

    # Phase 1: Dependencies
    Write-Host "[Phase 1/4] Installing dependencies..." -ForegroundColor Cyan
    Install-Git

    $pythonBin = Find-CompatiblePython
    if (-not $pythonBin) {
        $pythonBin = Install-Python312
    }
    Install-Uv

    # Phase 2: TraderBot
    Write-Host "`n[Phase 2/4] Installing TraderBot..." -ForegroundColor Cyan
    Install-TraderBot
    Install-Dependencies

    # Phase 3: Configuration
    Write-Host "`n[Phase 3/4] Configuration..." -ForegroundColor Cyan
    Invoke-MasterPasswordSetup
    Invoke-InteractiveConfig
    Setup-APICredentials

    # Phase 4: Service Registration
    Write-Host "`n[Phase 4/4] Service registration..." -ForegroundColor Cyan
    Invoke-AgentAssignment

    Write-Host ""
    Write-Host "╔══════════════════════════════════════════════════════╗" -ForegroundColor Green
    Write-Host "║         TraderBot Installation Complete!            ║" -ForegroundColor Green
    Write-Host "╚══════════════════════════════════════════════════════╝" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "  1. Verify installation: traderbot --version" -ForegroundColor Cyan
    Write-Host "  2. List profiles:       traderbot profile list" -ForegroundColor Cyan
    Write-Host "  3. Check tasks:         taskschd.msc → \TraderBot\" -ForegroundColor Cyan
    Write-Host "  4. View logs:           Get-Content ~/Library/Logs/traderbot-*.log" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "For deployment details, see: docs/deployment.md" -ForegroundColor Cyan
}

# ─── Dispatch ────────────────────────────────────────────────────────────────

if ($Uninstall) {
    Uninstall-TraderBot
} elseif ($Update) {
    Update-TraderBot
} else {
    Invoke-Install
}
