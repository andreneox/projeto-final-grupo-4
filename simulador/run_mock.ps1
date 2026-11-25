param(
    [string]$Config = "$PSScriptRoot\config.toml"
)

$localPython = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
$parentPython = Join-Path $PSScriptRoot "..\venv\Scripts\python.exe"
$pythonExecutable = if (Test-Path -LiteralPath $localPython) {
    $localPython
} elseif (Test-Path -LiteralPath $parentPython) {
    $parentPython
} else {
    throw "Ambiente virtual nao encontrado em simulador\venv ou na pasta pai."
}

& $pythonExecutable "$PSScriptRoot\main.py" --config $Config
exit $LASTEXITCODE
