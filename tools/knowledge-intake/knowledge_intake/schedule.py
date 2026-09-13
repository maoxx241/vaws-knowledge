"""Optional per-user Windows Task Scheduler entry; never install on import."""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

from .common import IntakeError, command, digest

NS = "http://schemas.microsoft.com/windows/2004/02/mit/task"
OWNER = "knowledge-intake-feed/1:"


def schedule_spec(config_path: Path, *, executable: Path | None = None) -> dict:
    """Stable owner/action identity; config must live outside disposable envs."""
    config = config_path.resolve()
    ident = digest(str(config).casefold())[:24]
    python = (executable or Path(sys.executable)).resolve()
    windowless = python.with_name("pythonw.exe")
    if os.name == "nt" and windowless.is_file():
        python = windowless
    args = subprocess.list2cmdline(["-I", "-m", "knowledge_intake.feed_sync", "sync", str(config)])
    value = {"name": "knowledge-intake-feed-" + ident, "execute": str(python), "arguments": args,
             "working_directory": str(config.parent), "config": str(config)}
    value["owner"] = OWNER + ident
    value["description"] = value["owner"] + ":" + digest(value)
    return value


def task_xml(spec: dict, user_sid: str = "__CURRENT_USER_SID__") -> str:
    """An hourly and logon task, interactive current user, no saved password."""
    ET.register_namespace("", NS)
    def element(parent, tag, text=None, **attributes):
        node = ET.SubElement(parent, "{" + NS + "}" + tag, attributes)
        if text is not None:
            node.text = text
        return node
    root = ET.Element("{" + NS + "}Task", {"version": "1.2"})
    registration = element(root, "RegistrationInfo")
    element(registration, "Description", spec["description"])
    triggers = element(root, "Triggers")
    hourly = element(triggers, "TimeTrigger")
    repetition = element(hourly, "Repetition")
    element(repetition, "Interval", "PT1H")
    element(repetition, "StopAtDurationEnd", "false")
    element(hourly, "StartBoundary", "2020-01-01T00:00:00")
    element(hourly, "Enabled", "true")
    logon = element(triggers, "LogonTrigger")
    element(logon, "Enabled", "true")
    element(logon, "UserId", user_sid)
    principals = element(root, "Principals")
    principal = element(principals, "Principal", id="Author")
    element(principal, "UserId", user_sid)
    element(principal, "LogonType", "InteractiveToken")
    element(principal, "RunLevel", "LeastPrivilege")
    settings = element(root, "Settings")
    for tag, value in (("MultipleInstancesPolicy", "IgnoreNew"), ("DisallowStartIfOnBatteries", "false"),
                       ("StopIfGoingOnBatteries", "false"), ("StartWhenAvailable", "true"),
                       ("ExecutionTimeLimit", "PT5M"), ("Enabled", "true")):
        element(settings, tag, value)
    actions = element(root, "Actions", Context="Author")
    action = element(actions, "Exec")
    element(action, "Command", spec["execute"])
    element(action, "Arguments", spec["arguments"])
    element(action, "WorkingDirectory", spec["working_directory"])
    return ET.tostring(root, encoding="unicode")


def _script(payload: dict) -> str:
    # Data is encoded separately; config names never become PowerShell syntax.
    encoded = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    script = r'''
$ErrorActionPreference = 'Stop'
$data = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__PAYLOAD__')) | ConvertFrom-Json
function Resolve-FeedSid([string]$identity) {
    if (-not $identity) { return '' }
    if ($identity -match '^S-[0-9]-') {
        return (New-Object Security.Principal.SecurityIdentifier($identity)).Value
    }
    try {
        return ([Security.Principal.NTAccount]::new($identity)).Translate([Security.Principal.SecurityIdentifier]).Value
    } catch [Security.Principal.IdentityNotMappedException] {
        if ($identity -match '[\\/@]') { throw }
        return ([Security.Principal.NTAccount]::new($env:COMPUTERNAME, $identity)).Translate([Security.Principal.SecurityIdentifier]).Value
    }
}
$name = $data.spec.name
$existing = Get-ScheduledTask -TaskName $name -TaskPath '\' -ErrorAction SilentlyContinue
if ($existing -and -not $existing.Description.StartsWith($data.spec.owner + ':')) {
    throw 'The scheduled-task name is occupied by another owner; it was not changed.'
}
$status = 'absent'
if ($data.operation -eq 'status') {
    if ($existing) { $status = 'present' }
} elseif ($data.operation -eq 'uninstall') {
    if ($existing) {
        Unregister-ScheduledTask -TaskName $name -TaskPath '\' -Confirm:$false
        $status = 'uninstalled'
    }
} else {
    $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    [xml]$definition = $data.xml
    $definition.Task.Principals.Principal.UserId = $sid
    $definition.Task.Triggers.LogonTrigger.UserId = $sid
    $xml = $definition.OuterXml
    $same = $existing -and $existing.Description -eq $data.spec.description
    if ($same) {
        $actions = @($existing.Actions)
        $triggers = @($existing.Triggers)
        $same = $actions.Count -eq 1 -and $actions[0].Execute -eq $data.spec.execute -and $actions[0].Arguments -eq $data.spec.arguments -and $actions[0].WorkingDirectory -eq $data.spec.working_directory
        $same = $same -and $triggers.Count -eq 2 -and @($triggers | Where-Object { $_.CimClass.CimClassName -eq 'MSFT_TaskTimeTrigger' -and $_.Repetition.Interval -eq 'PT1H' -and $_.Enabled }).Count -eq 1
        $same = $same -and @($triggers | Where-Object { $_.CimClass.CimClassName -eq 'MSFT_TaskLogonTrigger' -and (Resolve-FeedSid $_.UserId) -eq $sid -and $_.Enabled }).Count -eq 1
        $same = $same -and $existing.Settings.Enabled -and (Resolve-FeedSid $existing.Principal.UserId) -eq $sid -and $existing.Principal.RunLevel -eq 0
    }
    if ($same) { $status = 'unchanged' }
    elseif ($existing) {
        Register-ScheduledTask -TaskName $name -TaskPath '\' -Xml $xml -Force | Out-Null
        $status = 'installed'
    } else {
        Register-ScheduledTask -TaskName $name -TaskPath '\' -Xml $xml | Out-Null
        $status = 'installed'
    }
}
@{status=$status;name=$name} | ConvertTo-Json -Compress
'''.replace("__PAYLOAD__", encoded)
    return script


def _powershell(payload: dict) -> dict:
    encoded_script = base64.b64encode(_script(payload).encode("utf-16-le")).decode("ascii")
    _, raw = command(["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded_script],
                     timeout=30, max_bytes=65536)
    return json.loads(raw.decode("utf-8-sig"))


def manage_schedule(operation: str, config_path: Path) -> dict:
    if operation not in {"install", "uninstall", "status"}:
        raise IntakeError("unknown feed scheduling operation")
    if os.name != "nt":
        raise IntakeError("this scheduling entry supports Windows Task Scheduler; one-shot sync is cross-platform")
    if operation == "install":
        from .feed_sync import load_config
        load_config(config_path)
        try:
            command([sys.executable, "-I", "-c", "import knowledge_intake.feed_sync"], timeout=15, max_bytes=4096)
        except IntakeError as exc:
            raise IntakeError("install knowledge-intake into this Python environment before scheduling; the task does not inherit PYTHONPATH") from exc
    spec = schedule_spec(config_path)
    result = _powershell({"operation": operation, "spec": spec, "xml": task_xml(spec)})
    return {**result, "config": spec["config"], "executable": spec["execute"],
            "schedule": "hourly and at this user's logon; only while logged on; no stored password"}
