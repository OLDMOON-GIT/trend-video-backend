param(
    [string]$q,
    [string]$question,
    [string]$f,
    [string]$file,
    [string]$a,
    [string]$agents,
    [switch]$headless,
    [switch]$i,
    [switch]$interactive,
    [switch]$no_chrome_profile
)

# PowerShell script for running AI Aggregator from backend
Write-Host "Starting AI Aggregator..." -ForegroundColor Green

# Build python arguments
$pythonArgs = @()

# Handle question parameter (-q or --question)
if ($q) {
    $pythonArgs += "-q"
    $pythonArgs += $q
} elseif ($question) {
    $pythonArgs += "--question"
    $pythonArgs += $question
}

# Handle file parameter (-f or --file)
if ($f) {
    $pythonArgs += "-f"
    $pythonArgs += $f
} elseif ($file) {
    $pythonArgs += "--file"
    $pythonArgs += $file
}

# Handle agents parameter (-a or --agents)
if ($a) {
    $pythonArgs += "-a"
    $pythonArgs += $a
} elseif ($agents) {
    $pythonArgs += "--agents"
    $pythonArgs += $agents
}

# Handle headless switch
if ($headless) {
    $pythonArgs += "--headless"
}

# Handle interactive switch (-i or --interactive)
if ($i -or $interactive) {
    $pythonArgs += "-i"
}

# Handle no-chrome-profile switch
if ($no_chrome_profile) {
    $pythonArgs += "--no-chrome-profile"
}

# Run the script
python run_ai_aggregator.py @pythonArgs
