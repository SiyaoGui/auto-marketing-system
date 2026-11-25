Add-Type -AssemblyName System.Speech
$voiceReader = New-Object System.Speech.Synthesis.SpeechSynthesizer
try { $voiceReader.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo | Select-Object Name,Culture } }
finally { $voiceReader.Dispose() }
