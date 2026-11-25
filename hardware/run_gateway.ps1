param(
    [string]$Config = "$PSScriptRoot\config.toml"
)

$localPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$parentPython = Join-Path $PSScriptRoot "..\venv\Scripts\python.exe"
$pythonExecutable = if (Test-Path -LiteralPath $localPython) {
    $localPython
} elseif (Test-Path -LiteralPath $parentPython) {
    $parentPython
} else {
    throw "Ambiente virtual nao encontrado em hardware\.venv ou na pasta pai."
}

Push-Location -LiteralPath $PSScriptRoot
try {
    $stopFile = Join-Path $PSScriptRoot "data\gateway.stop"
    Remove-Item -LiteralPath $stopFile -Force -ErrorAction SilentlyContinue
    $argumentLine = '"{0}" --config "{1}" --stop-file "{2}"' -f `
        (Join-Path $PSScriptRoot "main.py"), $Config, $stopFile
    $process = Start-Process `
        -FilePath $pythonExecutable `
        -ArgumentList $argumentLine `
        -NoNewWindow `
        -PassThru
    $oldControlMode = [Console]::TreatControlCAsInput
    [Console]::TreatControlCAsInput = $true
    try {
        while (-not $process.HasExited) {
            if ([Console]::KeyAvailable) {
                $key = [Console]::ReadKey($true)
                $isControlC = $key.Key -eq [ConsoleKey]::C -and `
                    ($key.Modifiers -band [ConsoleModifiers]::Control)
                if ($isControlC) {
                    Write-Host "`nEncerrando Gateway..."
                    New-Item -ItemType File -Path $stopFile -Force | Out-Null
                    if (-not $process.WaitForExit(20000)) {
                        Write-Warning "Tempo limite excedido; encerrando processo."
                        taskkill /PID $process.Id /T /F | Out-Null
                    }
                    break
                }
            }
            Start-Sleep -Milliseconds 100
            $process.Refresh()
        }
    } finally {
        [Console]::TreatControlCAsInput = $oldControlMode
        if (-not $process.HasExited) {
            New-Item -ItemType File -Path $stopFile -Force | Out-Null
            if (-not $process.WaitForExit(3000)) {
                taskkill /PID $process.Id /T /F | Out-Null
            }
        }
        Remove-Item -LiteralPath $stopFile -Force -ErrorAction SilentlyContinue
    }
    exit $process.ExitCode
} finally {
    Pop-Location
}
