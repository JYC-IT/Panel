Add-Type -AssemblyName "System.Runtime.WindowsRuntime"
[Windows.Globalization.Language,Windows.Foundation.UniversalApiContract,ContentType=WindowsRuntime] | Out-Null
[Windows.Media.Ocr.OcrEngine,Windows.Foundation.UniversalApiContract,ContentType=WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder,Windows.Foundation.UniversalApiContract,ContentType=WindowsRuntime] | Out-Null
[Windows.Storage.StorageFile,Windows.Foundation.UniversalApiContract,ContentType=WindowsRuntime] | Out-Null

$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 })[0]
$asTaskNonGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and -not $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 })[0]

function AwaitOp($op) {
    if ($op.GetType().IsGenericType) {
        $typeArg = $op.GetType().GetGenericArguments()[0]
        $m = $asTaskGeneric.MakeGenericMethod($typeArg)
        return $m.Invoke($null, @($op)).GetAwaiter().GetResult()
    } else {
        return $asTaskNonGeneric.Invoke($null, @($op)).GetAwaiter().GetResult()
    }
}

function Run-Ocr($filePath) {
    Write-Host "=== OCR for $filePath ==="
    $file = AwaitOp ([Windows.Storage.StorageFile]::GetFileFromPathAsync($filePath))
    $stream = AwaitOp ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read))
    $decoder = AwaitOp ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream))
    $bmp = AwaitOp ($decoder.GetSoftwareBitmapAsync())
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new('es-ES'))
    if (-not $engine) {
        $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new('en-US'))
    }
    $res = AwaitOp ($engine.RecognizeAsync($bmp))
    Write-Host $res.Text
}

Run-Ocr "C:\Users\suppo\.gemini\antigravity\brain\0db31fb6-179b-4ed4-b018-2bbe7af8782a\.user_uploaded\media_1792889941953_83521909.png"
Run-Ocr "C:\Users\suppo\.gemini\antigravity\brain\0db31fb6-179b-4ed4-b018-2bbe7af8782a\.user_uploaded\media_1793018119088_4d382ca8.png"
