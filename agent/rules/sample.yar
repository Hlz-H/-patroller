rule SuspiciousPowerShell
{
    meta:
        description = "Detects PowerShell with encoded command execution"
        author = "巡查者"
        severity = "high"
    
    strings:
        $encoded = "-EncodedCommand" nocase
        $hidden = "-WindowStyle Hidden" nocase
        $download = "DownloadString" nocase
    
    condition:
        any of them
}
