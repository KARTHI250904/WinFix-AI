
Add-Type -AssemblyName System.Speech
$speak = New-Object System.Speech.Synthesis.SpeechSynthesizer
$speak.SetOutputToWaveFile("$pwd/scratch/test_tts.wav")
$speak.Speak("Testing Windows speech synthesis for voice verification.")
$speak.Dispose()
