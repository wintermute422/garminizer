# Garminizer installer for Windows (PowerShell 5.1 or newer, Docker Desktop).
#
#   irm https://raw.githubusercontent.com/wintermute422/garminizer/main/install.ps1 | iex
#
# Installs the latest release into %LOCALAPPDATA%\Garminizer, or updates the installation
# that is already there: fetches the release's compose.yml, creates .env with random secrets
# (once; never printed), pulls the ready-made image, starts the three containers, waits until
# the dashboard answers, adds a Start-menu shortcut and opens the dashboard.
#
# No git, no Python and no image build. Docker Desktop must be installed. Running it again
# updates to the latest release after a database backup; your .env and data are kept.
#
#   -InstallDir DIR   where compose.yml, .env and the data folder live
#   -Version X.Y.Z    install that release instead of the latest one
#   -TimeZone ZONE    IANA name such as Europe/Berlin (default: taken from Windows)
#   -Port N           dashboard port on this computer (default 8420)
#   -DbPort N         database port on this computer (default 55433)
#   -PrepareOnly      write the files, do not touch Docker
#   -NoShortcut       no Start-menu shortcut;  -NoOpen  do not open the browser
#   -Source DIR|URL   read compose.yml and .env.example from there (needs -Version)
#   -ShortcutDir DIR  folder for the shortcut (default: the Start menu)
#   -DockerDesktop EXE  Docker Desktop.exe, when it is not installed under Program Files
#
# To pass options to the one-liner:
#   & ([scriptblock]::Create((irm https://raw.githubusercontent.com/wintermute422/garminizer/main/install.ps1))) -Port 8421
#
# This file must stay pure ASCII: Windows PowerShell 5.1 reads scripts without a byte-order
# mark in the system code page.
param(
    [string]$InstallDir,
    [string]$Version = 'latest',
    [string]$TimeZone,
    [int]$Port = 0,
    [int]$DbPort = 0,
    [string]$Source,
    [string]$ShortcutDir,
    [string]$DockerDesktop,
    [switch]$PrepareOnly,
    [switch]$NoShortcut,
    [switch]$NoOpen
)

$Repository = 'wintermute422/garminizer'
$MinCompose = [version]'2.24.0'

# Windows time zone id -> IANA name, for the zones most people live in. Others fall back to
# UTC (it only sets the time of the nightly backup; days follow your Garmin profile).
$Zones = @{
    'UTC' = 'UTC'
    'GMT Standard Time' = 'Europe/London'
    'Greenwich Standard Time' = 'Atlantic/Reykjavik'
    'W. Europe Standard Time' = 'Europe/Berlin'
    'Central Europe Standard Time' = 'Europe/Budapest'
    'Central European Standard Time' = 'Europe/Warsaw'
    'Romance Standard Time' = 'Europe/Paris'
    'GTB Standard Time' = 'Europe/Bucharest'
    'FLE Standard Time' = 'Europe/Helsinki'
    'E. Europe Standard Time' = 'Europe/Chisinau'
    'Turkey Standard Time' = 'Europe/Istanbul'
    'Russian Standard Time' = 'Europe/Moscow'
    'Israel Standard Time' = 'Asia/Jerusalem'
    'Egypt Standard Time' = 'Africa/Cairo'
    'South Africa Standard Time' = 'Africa/Johannesburg'
    'W. Central Africa Standard Time' = 'Africa/Lagos'
    'E. Africa Standard Time' = 'Africa/Nairobi'
    'Arab Standard Time' = 'Asia/Riyadh'
    'Arabian Standard Time' = 'Asia/Dubai'
    'Pakistan Standard Time' = 'Asia/Karachi'
    'India Standard Time' = 'Asia/Kolkata'
    'Bangladesh Standard Time' = 'Asia/Dhaka'
    'SE Asia Standard Time' = 'Asia/Bangkok'
    'Singapore Standard Time' = 'Asia/Singapore'
    'China Standard Time' = 'Asia/Shanghai'
    'Taipei Standard Time' = 'Asia/Taipei'
    'Tokyo Standard Time' = 'Asia/Tokyo'
    'Korea Standard Time' = 'Asia/Seoul'
    'W. Australia Standard Time' = 'Australia/Perth'
    'Cen. Australia Standard Time' = 'Australia/Adelaide'
    'E. Australia Standard Time' = 'Australia/Brisbane'
    'AUS Eastern Standard Time' = 'Australia/Sydney'
    'New Zealand Standard Time' = 'Pacific/Auckland'
    'Hawaiian Standard Time' = 'Pacific/Honolulu'
    'Alaskan Standard Time' = 'America/Anchorage'
    'Pacific Standard Time' = 'America/Los_Angeles'
    'US Mountain Standard Time' = 'America/Phoenix'
    'Mountain Standard Time' = 'America/Denver'
    'Central Standard Time' = 'America/Chicago'
    'Canada Central Standard Time' = 'America/Regina'
    'Central Standard Time (Mexico)' = 'America/Mexico_City'
    'Eastern Standard Time' = 'America/New_York'
    'Atlantic Standard Time' = 'America/Halifax'
    'Newfoundland Standard Time' = 'America/St_Johns'
    'SA Pacific Standard Time' = 'America/Bogota'
    'Pacific SA Standard Time' = 'America/Santiago'
    'Argentina Standard Time' = 'America/Argentina/Buenos_Aires'
    'E. South America Standard Time' = 'America/Sao_Paulo'
}

function Say([string]$Message) { Write-Host "  $Message" }

function Step([string]$Message) { Write-Host ''; Write-Host "> $Message" -ForegroundColor Cyan }

function Get-Text([string]$Name) {
    # One file of the release, from a folder or over HTTPS.
    if (Test-Path -LiteralPath $script:From -PathType Container) {
        $path = Join-Path $script:From $Name
        if (-not (Test-Path -LiteralPath $path)) { throw "$Name not found in $($script:From)" }
        return [System.IO.File]::ReadAllText($path)
    }
    try {
        $response = Invoke-WebRequest -Uri "$($script:From)/$Name" -UseBasicParsing
    } catch {
        throw "could not download $Name from $($script:From): $($_.Exception.Message)"
    }
    $content = $response.Content
    if ($content -is [byte[]]) { $content = [System.Text.Encoding]::UTF8.GetString($content) }
    return [string]$content
}

function Write-Text([string]$Path, [string]$Text) {
    # UTF-8 without a byte-order mark and with LF endings: what Docker Compose expects.
    $clean = $Text.Replace("`r`n", "`n")
    [System.IO.File]::WriteAllText($Path, $clean, (New-Object System.Text.UTF8Encoding $false))
}

function New-Secret([int]$Length) {
    # Letters and digits only: the database password is also part of a URL.
    $alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $buffer = New-Object byte[] 1
    $chars = New-Object System.Text.StringBuilder
    while ($chars.Length -lt $Length) {
        $rng.GetBytes($buffer)
        # 248 = 4 x 62: bytes above it would favour the first letters.
        if ($buffer[0] -lt 248) { [void]$chars.Append($alphabet[$buffer[0] % 62]) }
    }
    $rng.Dispose()
    return $chars.ToString()
}

function Set-EnvValue([string]$Text, [string]$Key, [string]$Value) {
    # Replace the first (possibly commented) KEY= line, or append one.
    $line = "$Key=$Value"
    $pattern = New-Object System.Text.RegularExpressions.Regex "(?m)^[ \t]*#?[ \t]*$([regex]::Escape($Key))=[^\r\n]*"
    if ($pattern.IsMatch($Text)) { return $pattern.Replace($Text, $line.Replace('$', '$$'), 1) }
    return $Text.TrimEnd() + "`n$line`n"
}

function Get-EnvValue([string]$Text, [string]$Key, [string]$Default) {
    $match = [regex]::Match($Text, "(?m)^[ \t]*$([regex]::Escape($Key))=([^\r\n]*)")
    if ($match.Success -and $match.Groups[1].Value.Trim()) { return $match.Groups[1].Value.Trim() }
    return $Default
}

function Get-IanaZone {
    try { $id = [System.TimeZoneInfo]::Local.Id } catch { return 'UTC' }
    if ($id -match '^[A-Za-z_]+/[A-Za-z_/+-]+$') { return $id }  # already an IANA name
    if ($Zones.ContainsKey($id)) { return $Zones[$id] }
    return 'UTC'
}

function Invoke-Docker([string[]]$Arguments, [switch]$Capture) {
    # Runs docker and returns its exit code (and its output with -Capture). Native tools write
    # progress to stderr; with 'Stop' Windows PowerShell 5.1 would turn that into an error.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $output = $null
    try {
        if ($Capture) { $output = & docker @Arguments 2>$null } else { & docker @Arguments | Out-Host }
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
    return New-Object psobject -Property @{ Code = $code; Output = ($output -join "`n") }
}

function Assert-Docker([bool]$OnWindows) {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw ('Docker is not installed. Install Docker Desktop from ' +
            'https://www.docker.com/products/docker-desktop/ , start it once, then run this installer again.')
    }
    if ((Invoke-Docker @('info') -Capture).Code -ne 0) {
        $desktop = $DockerDesktop
        if (-not $desktop) { $desktop = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe' }
        if ($OnWindows -and (Test-Path -LiteralPath $desktop)) {
            Say 'Docker Desktop is not running; starting it (this can take a minute)...'
            Start-Process -FilePath $desktop | Out-Null
            $deadline = (Get-Date).AddSeconds(180)
            while ((Get-Date) -lt $deadline -and (Invoke-Docker @('info') -Capture).Code -ne 0) {
                Start-Sleep -Seconds 3
            }
        }
        if ((Invoke-Docker @('info') -Capture).Code -ne 0) {
            throw 'Docker is installed but not running. Start Docker Desktop, wait until it is ready, then run this installer again.'
        }
    }
    $compose = Invoke-Docker @('compose', 'version', '--short') -Capture
    $found = $null
    if ($compose.Code -eq 0 -and $compose.Output -match '(\d+\.\d+\.\d+)') { $found = [version]$Matches[1] }
    if (-not $found -or $found -lt $MinCompose) {
        throw "Docker Compose $MinCompose or newer is needed (found: $($compose.Output.Trim())). Update Docker Desktop."
    }
    Say "Docker is running (Compose $found)."
}

function Assert-NoOtherInstallation([string]$Project, [string]$Dir, [bool]$Fresh) {
    # The Compose project and its database volume are named after the project, not the folder.
    # Starting a second installation would take over the containers of the first one and could
    # not open its database (different password), so refuse instead.
    $here = [System.IO.Path]::GetFullPath($Dir).TrimEnd('\', '/')
    $listing = Invoke-Docker @('compose', 'ls', '--all', '--format', 'json') -Capture
    if ($listing.Code -eq 0 -and $listing.Output.Trim()) {
        # Assign first: Windows PowerShell 5.1 hands a JSON list down the pipeline as ONE object,
        # so @(... | ConvertFrom-Json) would loop once over all projects at the same time.
        $entries = $listing.Output | ConvertFrom-Json
        foreach ($entry in $entries) {
            if ($entry.Name -ne $Project) { continue }
            foreach ($file in ([string]$entry.ConfigFiles).Split(',')) {
                if (-not $file.Trim()) { continue }
                $other = [System.IO.Path]::GetDirectoryName($file.Trim()).TrimEnd('\', '/')
                if ($other -ine $here) {
                    throw ("Garminizer is already installed in $other. Update it there, or run this " +
                        "installer with -InstallDir `"$other`". Nothing was changed.")
                }
            }
        }
    }
    if ($Fresh) {
        $volume = "${Project}_pgdata"
        $volumes = Invoke-Docker @('volume', 'ls', '-q', '--filter', "name=$volume") -Capture
        if ($volumes.Code -eq 0 -and (($volumes.Output -split "`n") | Where-Object { $_.Trim() -eq $volume })) {
            throw ("A Garminizer database from an earlier installation exists (Docker volume $volume), " +
                "but $here has no .env with its password. Copy the .env of that installation into " +
                "$here and run this installer again. Nothing was changed.")
        }
    }
}

function Wait-Dashboard([string]$Url) {
    $deadline = (Get-Date).AddSeconds(180)
    while ((Get-Date) -lt $deadline) {
        try {
            $health = Invoke-WebRequest -Uri "$Url/api/health" -UseBasicParsing -TimeoutSec 5
            if ($health.StatusCode -eq 200) { return $true }
        } catch { }
        Start-Sleep -Seconds 2
    }
    return $false
}

function Install-Garminizer {
    $ErrorActionPreference = 'Stop'
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $onWindows = ($env:OS -eq 'Windows_NT')
    $dir = $InstallDir
    if (-not $dir) {
        if ($onWindows) { $dir = Join-Path $env:LOCALAPPDATA 'Garminizer' } else { $dir = Join-Path $HOME 'garminizer' }
    }
    $dir = [System.IO.Path]::GetFullPath($dir)
    $project = 'garminizer'
    if ($env:COMPOSE_PROJECT_NAME) { $project = $env:COMPOSE_PROJECT_NAME }

    Write-Host ''
    Write-Host 'Garminizer installer' -ForegroundColor Cyan
    Say "Folder: $dir"

    if (-not $PrepareOnly) {
        Step 'Checking Docker'
        Assert-Docker $onWindows
    }

    Step 'Finding the release'
    $wanted = $Version.TrimStart('v')
    if ($Source) {
        if ($wanted -eq 'latest') { throw '-Source needs -Version X.Y.Z' }
        $script:From = $Source.TrimEnd('/')
    } else {
        if ($wanted -eq 'latest') {
            try {
                $release = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repository/releases/latest" -UseBasicParsing
            } catch {
                throw "could not ask GitHub for the latest release: $($_.Exception.Message)"
            }
            $wanted = ([string]$release.tag_name).TrimStart('v')
        }
        $script:From = "https://raw.githubusercontent.com/$Repository/v$wanted"
    }
    if ($wanted -notmatch '^\d+\.\d+\.\d+$') { throw "'$wanted' is not a version like 0.1.0" }
    Say "Version $wanted"

    $compose = Get-Text 'compose.yml'
    if ($compose -notmatch '(?m)^services:') { throw 'the downloaded compose.yml does not look like a Compose file' }
    $envPath = Join-Path $dir '.env'
    $fresh = -not (Test-Path -LiteralPath $envPath)
    if ($fresh) { $settings = Get-Text '.env.example' } else { $settings = [System.IO.File]::ReadAllText($envPath) }

    if (-not $PrepareOnly) { Assert-NoOtherInstallation $project $dir $fresh }

    Step 'Writing the settings'
    if ($fresh) {
        $password = New-Secret 32
        $settings = Set-EnvValue $settings 'POSTGRES_PASSWORD' $password
        $settings = Set-EnvValue $settings 'APP_SECRET_KEY' (New-Secret 64)
        $url = Get-EnvValue $settings 'DATABASE_URL' ''
        if ($url) {
            $settings = Set-EnvValue $settings 'DATABASE_URL' ($url -replace '(?<=//garminizer:)[^@]*(?=@)', $password)
        }
        $zone = $TimeZone
        if (-not $zone) { $zone = Get-IanaZone }
        $settings = Set-EnvValue $settings 'TZ' $zone
        Say "New .env with a random database password and secret key (time zone $zone)."
    } else {
        if ($TimeZone) { $settings = Set-EnvValue $settings 'TZ' $TimeZone }
        Say 'Keeping the existing .env (passwords and settings unchanged).'
    }
    $settings = Set-EnvValue $settings 'GARMINIZER_VERSION' $wanted
    if ($Port -gt 0) { $settings = Set-EnvValue $settings 'APP_PORT' ([string]$Port) }
    if ($DbPort -gt 0) {
        $settings = Set-EnvValue $settings 'DB_PORT' ([string]$DbPort)
        $url = Get-EnvValue $settings 'DATABASE_URL' ''
        if ($url) { $settings = Set-EnvValue $settings 'DATABASE_URL' ($url -replace '(?<=@127\.0\.0\.1:)\d+', [string]$DbPort) }
    }
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    Write-Text (Join-Path $dir 'compose.yml') $compose
    Write-Text $envPath $settings
    $dashboard = 'http://localhost:' + (Get-EnvValue $settings 'APP_PORT' '8420')

    if ($PrepareOnly) {
        Say "Files are ready in $dir. Start with: docker compose pull; docker compose up -d"
        return
    }

    Push-Location -LiteralPath $dir
    try {
        if (-not $fresh) {
            $running = Invoke-Docker @('compose', 'ps', '--status', 'running', '--services') -Capture
            if ($running.Code -eq 0 -and (($running.Output -split "`n") | Where-Object { $_.Trim() -eq 'worker' })) {
                Step 'Backing up the database before the update'
                if ((Invoke-Docker @('compose', 'exec', '-T', 'worker', 'garminizer', 'backup', 'create')).Code -ne 0) {
                    throw 'the backup failed, so nothing was updated. See the messages above.'
                }
            }
        }
        Step 'Downloading Garminizer'
        if ((Invoke-Docker @('compose', 'pull')).Code -ne 0) {
            throw ("the image for version $wanted could not be downloaded. Check your internet connection " +
                "and that this release exists: https://github.com/$Repository/releases")
        }
        Step 'Starting Garminizer'
        if ((Invoke-Docker @('compose', 'up', '-d', '--no-build')).Code -ne 0) {
            throw ("Docker could not start Garminizer. If a port is in use, run the installer again with " +
                "-Port 8421 (dashboard) or -DbPort 55434 (database).")
        }
    } finally {
        Pop-Location
    }

    Step 'Waiting for the dashboard'
    if (-not (Wait-Dashboard $dashboard)) {
        throw "the dashboard did not answer at $dashboard. Look at: docker compose logs app  (in $dir)"
    }
    Say "Garminizer $wanted is running at $dashboard"

    if ($onWindows -and -not $NoShortcut) {
        $menu = $ShortcutDir
        if (-not $menu) { $menu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs' }
        New-Item -ItemType Directory -Force -Path $menu | Out-Null
        [System.IO.File]::WriteAllText((Join-Path $menu 'Garminizer.url'), "[InternetShortcut]`r`nURL=$dashboard/`r`n")
        Say 'Start-menu shortcut "Garminizer" added.'
    }
    if (-not $NoOpen) { try { Start-Process $dashboard } catch { } }

    Write-Host ''
    Write-Host 'Done.' -ForegroundColor Green
    Say 'Garminizer starts with Docker Desktop. Enable "Start Docker Desktop when you sign in"'
    Say 'in its settings to have it always running.'
    Say 'Update: run this installer again. Your data stays in Docker and in:'
    Say "  $dir"
}

$exitCode = 0
try {
    Install-Garminizer
} catch {
    Write-Host ''
    Write-Host "Garminizer installer: $($_.Exception.Message)" -ForegroundColor Red
    $exitCode = 1
}
# Leave the window open when pasted as a one-liner; report the result when run as a file.
if ($PSCommandPath) { exit $exitCode }
