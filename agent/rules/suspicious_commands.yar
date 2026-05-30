rule suspicious_powershell_encoded_command {
    meta:
        description = "Detects base64 encoded PowerShell commands often used in attacks"
        author = "巡查者"
        severity = "high"
    strings:
        $encoded = "-EncodedCommand" ascii nocase
        $enc = "-enc" ascii nocase
        $bypass = "-ExecutionPolicy Bypass" ascii nocase
        $hidden = "-WindowStyle Hidden" ascii nocase
    condition:
        ($encoded or $enc) and ($bypass or $hidden)
}

rule suspicious_rundll32 {
    meta:
        description = "Detects suspicious rundll32.exe execution patterns"
        author = "巡查者"
        severity = "medium"
    strings:
        $url = "http://" ascii
        $dll = ".dll" ascii
        $regsvr = "regsvr" ascii nocase
    condition:
        $url or ($dll and $regsvr)
}
