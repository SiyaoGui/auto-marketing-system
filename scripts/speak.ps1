param([Parameter(Mandatory=$true)][string]$InputJson)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$spec = Get-Content -LiteralPath $InputJson -Raw -Encoding UTF8 | ConvertFrom-Json
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
  if ($spec.voice) {
    $synth.SelectVoice($spec.voice)
  } else {
    $wanted = ([string]$spec.language).Split('-')[0]
    $chosen = $synth.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.TwoLetterISOLanguageName -eq $wanted } | Select-Object -First 1
    if (-not $chosen) { throw "No installed speech voice for language $wanted" }
    $synth.SelectVoice($chosen.VoiceInfo.Name)
  }
  $synth.Rate = 0
  $synth.SetOutputToWaveFile($spec.output)
  $synth.Speak($spec.text)
} finally {
  $synth.Dispose()
}
