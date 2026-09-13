from __future__ import annotations

import json
import base64
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

from knowledge_intake.common import Budget, Limits, digest, write_atomic as original_write
from knowledge_intake.feed_sync import PROFILE, SCHEMA, GitFeed, _encoded, main, sync_feed, verified_snapshot
from knowledge_intake.schedule import NS, schedule_spec, task_xml


class FeedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / "publisher"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.test")
        self.git("config", "core.autocrlf", "false")
        self.git("checkout", "-qb", "codex/va-reference-feed")
        self.config = {"repository": str(self.repo), "state_root": str(self.root / "state"), "output_root": str(self.root / "notes")}
        self.output = Path(self.config["output_root"])
        self.number = 0

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], capture_output=True, check=True).stdout.decode().strip()

    def commit(self):
        self.git("add", ".")
        self.git("commit", "-qm", "prepared feed")
        return self.git("rev-parse", "HEAD")

    def publish(self, docs, *, commit=True):
        self.number += 1
        generation = f"{self.number:032x}"
        root = self.repo / "generations" / generation
        root.mkdir(parents=True)
        rows = []
        for name, text in sorted(docs.items()):
            raw = text.encode("utf8")
            normalized = digest(text.replace("\r\n", "\n").replace("\r", "\n").encode())
            metadata = _encoded({"conditions": {"hardware": "Ascend 910B"}, "retrieval": {"source_sha256": normalized,
                                "aliases": ["HCCL replay", {"text": "graph replay", "relation": "related", "scope": ["ascend"]}], "topics": ["ascend"]}})
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            path.with_suffix(".meta.json").write_bytes(metadata)
            rows.append({"path": name, "size": len(raw), "sha256": digest(raw), "source_sha256": normalized,
                         "input_sha256": digest(raw), "metadata_size": len(metadata), "metadata_sha256": digest(metadata)})
        snapshot = digest(_encoded({"files": rows, "includes": ["topics", "cases", "maintenance"], "redaction_profile": PROFILE}))
        manifest = {"schema": SCHEMA, "redaction_profile": PROFILE, "includes": ["topics", "cases", "maintenance"],
                    "snapshot": snapshot, "previous_snapshot": None, "files": rows,
                    "changes": {"added": list(docs), "removed": [], "updated": [], "renamed": []}}
        (root / "prepared.json").write_bytes(_encoded(manifest))
        (self.repo / "current.json").write_bytes(_encoded({"schema": SCHEMA, "generation": generation,
                            "manifest_sha256": digest(_encoded(manifest)), "snapshot": snapshot}))
        if commit:
            self.commit()
        return root

    def sync(self):
        return sync_feed(self.config)

    def visible(self):
        return {path.relative_to(self.output).as_posix(): path.read_bytes() for path in self.output.rglob("*") if path.is_file()}

    def test_committed_export_exact_metadata_replay_and_unrelated_notes(self):
        prepared = self.publish({"topics/hccl.md": "# HCCL\r\n\r\nRecorded once.\r\n"})
        self.output.mkdir()
        (self.output / "manual.md").write_text("Unrelated note", encoding="utf8")
        first = self.sync()
        self.assertEqual(first["status"], "updated", first)
        note = self.output / "topics/hccl.md"
        self.assertEqual(note.read_bytes(), (prepared / "topics/hccl.md").read_bytes())
        self.assertEqual(note.with_suffix(".meta.json").read_bytes(), (prepared / "topics/hccl.meta.json").read_bytes())
        before = {path: path.stat().st_mtime_ns for path in self.output.rglob("*") if path.is_file()}
        with patch("knowledge_intake.feed_sync.write_atomic", side_effect=AssertionError("replayed output write")), \
                patch.object(GitFeed, "read", side_effect=AssertionError("replayed source blob download")):
            again = self.sync()
        self.assertEqual(again["status"], "unchanged", again)
        self.assertTrue(again["reused_commit"])
        self.assertEqual(before, {path: path.stat().st_mtime_ns for path in before})
        self.assertEqual((self.output / "manual.md").read_text(), "Unrelated note")

    def test_verified_rename_and_removal_retire_only_owned_generated_files(self):
        self.publish({"cases/old.md": "# Case\n\nInitial.", "cases/removed.md": "# Removed"})
        self.sync()
        (self.output / "manual.md").write_text("Keep", encoding="utf8")
        self.publish({"cases/new.md": "# Case\n\nInitial."})
        result = self.sync()
        self.assertEqual(result["status"], "updated", result)
        self.assertEqual(result["deleted"], ["cases/old.md", "cases/removed.md"])
        self.assertFalse((self.output / "cases/old.meta.json").exists())
        self.assertEqual(set(self.visible()), {"cases/new.md", "cases/new.meta.json", "manual.md"})
        self.publish({})
        self.assertEqual(self.sync()["deleted"], ["cases/new.md"])
        self.assertEqual(set(self.visible()), {"manual.md"})

    def test_manual_body_or_metadata_conflict_preserves_complete_previous_set(self):
        self.publish({"topics/a.md": "# A", "topics/b.md": "# B"})
        self.sync()
        (self.output / "topics/a.meta.json").write_text("{\"manual\":true}", encoding="utf8")
        before = self.visible()
        self.publish({"topics/b.md": "# New B", "topics/c.md": "# New C"})
        result = self.sync()
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(result["conflicts"], ["topics/a.meta.json"])
        self.assertEqual(self.visible(), before)

    def test_unowned_collision_is_never_adopted(self):
        self.publish({"topics/a.md": "# A"})
        (self.output / "topics").mkdir(parents=True)
        (self.output / "topics/a.md").write_text("# A", encoding="utf8")
        self.assertEqual(self.sync()["status"], "conflict")
        self.assertFalse((self.output / "topics/a.meta.json").exists())

    def test_bad_manifest_hash_extra_file_and_body_keep_previous(self):
        self.publish({"topics/a.md": "# A"})
        self.sync()
        before = self.visible()
        for damage in ("pointer", "body", "unmanaged"):
            with self.subTest(damage=damage):
                prepared = self.publish({"topics/a.md": "# Changed"}, commit=False)
                if damage == "pointer":
                    pointer = json.loads((self.repo / "current.json").read_bytes())
                    pointer["manifest_sha256"] = "f" * 64
                    (self.repo / "current.json").write_bytes(_encoded(pointer))
                elif damage == "body":
                    (prepared / "topics/a.md").write_text("# Altered", encoding="utf8")
                else:
                    (prepared / "private.log").write_text("unmanaged", encoding="utf8")
                self.commit()
                self.assertEqual(self.sync()["status"], "error")
                self.assertEqual(self.visible(), before)

    def test_self_consistent_unsafe_paths_collisions_and_size_claims_are_rejected(self):
        self.publish({"topics/a.md": "# Original"})
        self.sync()
        before = self.visible()
        for damage in ("traversal", "collision", "oversize", "unknown_profile", "outside_selection", "bad_changes"):
            with self.subTest(damage=damage):
                prepared = self.publish({"topics/a.md": "# Changed"}, commit=False)
                manifest = json.loads((prepared / "prepared.json").read_bytes())
                if damage == "traversal":
                    manifest["files"][0]["path"] = "../outside.md"
                elif damage == "collision":
                    manifest["files"].append({**manifest["files"][0], "path": "TOPICS/a.md"})
                elif damage == "oversize":
                    manifest["files"][0]["size"] = 4 * 1024 * 1024 + 1
                elif damage == "unknown_profile":
                    manifest["redaction_profile"] = "unprepared"
                elif damage == "outside_selection":
                    manifest["includes"] = ["cases"]
                else:
                    manifest["changes"] = []
                manifest["snapshot"] = digest(_encoded({key: manifest[key] for key in ("files", "includes", "redaction_profile")}))
                (prepared / "prepared.json").write_bytes(_encoded(manifest))
                pointer = json.loads((self.repo / "current.json").read_bytes())
                pointer.update(manifest_sha256=digest(_encoded(manifest)), snapshot=manifest["snapshot"])
                (self.repo / "current.json").write_bytes(_encoded(pointer))
                self.commit()
                self.assertEqual(self.sync()["status"], "error")
                self.assertEqual(self.visible(), before)

    def test_same_feed_concurrent_lock_rejects_without_editing_output(self):
        from knowledge_intake.sync import _lock
        self.publish({"topics/a.md": "# Original"})
        self.sync()
        before = self.visible()
        with _lock(Path(self.config["state_root"]) / "sync.lock"):
            with self.assertRaisesRegex(Exception, "already being synchronized"):
                self.sync()
        self.assertEqual(self.visible(), before)

    def test_separate_states_share_one_output_lock(self):
        from knowledge_intake.sync import _lock
        from knowledge_intake.feed_sync import _output_lock
        self.publish({"topics/a.md": "# Original"})
        with _lock(_output_lock(self.output)):
            for state in ("state", "other-state"):
                with self.assertRaisesRegex(Exception, "already being synchronized"):
                    sync_feed({**self.config, "state_root": str(self.root / state)})
        self.assertFalse(self.output.exists())

    def test_malformed_journal_and_pending_write_error_receipt_and_preserve_notes(self):
        self.publish({"topics/a.md": "# Original"})
        self.sync()
        before = self.visible()
        path = Path(self.config["state_root"]) / "journal.json"
        original = path.read_bytes()
        for malformed in (b"[]", b"{broken", _encoded({**json.loads(original), "pending": [1]}),
                          _encoded({**json.loads(original), "files": {"../unsafe.md": "f" * 64}})):
            path.write_bytes(malformed)
            result = self.sync()
            self.assertEqual(result["status"], "error", result)
            self.assertEqual(json.loads(path.with_name("last-run.json").read_bytes())["status"], "error")
            self.assertEqual(self.visible(), before)

    def test_fixed_commit_does_not_mix_a_branch_update(self):
        self.publish({"topics/a.md": "# Old"})
        expected = self.git("rev-parse", "HEAD")
        read = GitFeed.read
        moved = []
        def advance(source, name, limit):
            data = read(source, name, limit)
            if not moved:
                moved.append(1)
                self.publish({"topics/a.md": "# New"})
            return data
        with patch.object(GitFeed, "read", advance):
            result = self.sync()
        self.assertEqual(result["revision"], expected)
        self.assertEqual((self.output / "topics/a.md").read_text(), "# Old")
        self.assertEqual(self.sync()["status"], "updated")

    def test_new_commit_downloads_only_changed_body_metadata_after_manifest_validation(self):
        docs = {f"topics/{index}.md": f"# Case {index}" for index in range(3)}
        self.publish(docs)
        self.sync()
        docs["topics/1.md"] = "# Changed case"
        self.publish(docs)
        read, paths = GitFeed.read, []
        def observed(source, name, limit):
            paths.append(name)
            return read(source, name, limit)
        with patch.object(GitFeed, "read", observed):
            result = self.sync()
        self.assertEqual(result["status"], "updated", result)
        self.assertEqual(result["reused_files"], 4)
        self.assertEqual(result["downloaded_files"], 4)
        self.assertEqual(len(paths), 4)
        self.assertFalse(any(name.endswith(("topics/0.md", "topics/2.md")) for name in paths))

    def test_same_manifest_hash_cannot_hide_tampered_blob_in_new_commit(self):
        prepared = self.publish({"topics/a.md": "# Original"})
        self.sync()
        before = self.visible()
        (prepared / "topics/a.md").write_text("# Undeclared publisher edit", encoding="utf8")
        self.commit()
        result = self.sync()
        self.assertEqual(result["status"], "error", result)
        self.assertIn("committed blob", result["reason"])
        self.assertEqual(self.visible(), before)

    def test_github_api_reads_pinned_blobs_and_reuses_tree_listing_within_pass(self):
        self.publish({"topics/a.md": "# A", "topics/b.md": "# B"})
        commit = self.git("rev-parse", "HEAD")
        root_tree = self.git("rev-parse", "HEAD^{tree}")
        calls = []
        def api(endpoint, budget):
            calls.append(endpoint)
            if endpoint == "repos/example/reference/commits/codex%2Fva-reference-feed":
                return {"sha": commit, "commit": {"tree": {"sha": root_tree}}}
            if "/git/trees/" in endpoint:
                sha = endpoint.rsplit("/", 1)[-1].split("?", 1)[0]
                flags = ["-r"] if "?recursive=1" in endpoint else []
                raw = subprocess.run(["git", "-C", str(self.repo), "ls-tree", *flags, "-z", sha], capture_output=True, check=True).stdout
                rows = []
                for entry in raw.split(b"\0"):
                    if entry:
                        info, name = entry.split(b"\t", 1)
                        mode, kind, oid = info.decode().split()
                        rows.append({"path": name.decode(), "mode": mode, "type": kind, "sha": oid,
                                     "size": int(self.git("cat-file", "-s", oid))})
                return {"tree": rows, "truncated": False}
            oid = endpoint.rsplit("/", 1)[-1]
            raw = subprocess.run(["git", "-C", str(self.repo), "cat-file", "blob", oid], capture_output=True, check=True).stdout
            return {"encoding": "base64", "content": base64.b64encode(raw).decode(), "size": len(raw)}
        with patch("knowledge_intake.feed_sync.github_api", api):
            source = GitFeed("https://github.com/example/reference", "codex/va-reference-feed", Budget(Limits()))
            result = verified_snapshot(source)
        self.assertEqual(result["revision"], commit)
        self.assertEqual(len(result["files"]), 4)
        trees = [value for value in calls if "/git/trees/" in value]
        self.assertEqual(len(trees), len(set(trees)), "same pass should reuse each directory tree")

    def test_mid_commit_io_failure_rolls_back_and_retry_succeeds(self):
        self.publish({"topics/a.md": "# Old A", "topics/b.md": "# Old B"})
        self.sync()
        before = self.visible()
        self.publish({"topics/a.md": "# New A", "topics/b.md": "# New B"})
        failed = []
        def fail_once(path, raw):
            if path == self.output / "topics/b.md" and not failed:
                failed.append(1)
                raise OSError("injected write failure")
            return original_write(path, raw)
        with patch("knowledge_intake.feed_sync.write_atomic", fail_once):
            result = self.sync()
        self.assertEqual(result["status"], "error", result)
        self.assertEqual(self.visible(), before)
        self.assertEqual(self.sync()["status"], "updated")

    def test_interrupted_batch_recovery_preserves_maintainer_change(self):
        self.publish({"topics/a.md": "# Old A", "topics/b.md": "# Old B"})
        self.sync()
        self.publish({"topics/a.md": "# New A", "topics/b.md": "# New B"})
        def interrupt(path, raw):
            if path == self.output / "topics/b.md":
                raise KeyboardInterrupt()
            return original_write(path, raw)
        with patch("knowledge_intake.feed_sync.write_atomic", interrupt), self.assertRaises(KeyboardInterrupt):
            self.sync()
        (self.output / "topics/a.md").write_text("Maintainer changed during outage", encoding="utf8")
        result = self.sync()
        self.assertEqual(result["status"], "error")
        self.assertIn("independently changed", result["reason"])
        self.assertEqual((self.output / "topics/a.md").read_text(), "Maintainer changed during outage")
        self.assertEqual((self.output / "topics/b.md").read_text(), "# Old B")

    def test_different_state_does_not_adopt_existing_generated_files(self):
        # Each feed must be configured once; a copied state path must not grant
        # ownership of the files already written by the first instance.
        self.publish({"topics/a.md": "# A"})
        self.sync()
        other = {**self.config, "state_root": str(self.root / "other-state")}
        self.assertEqual(sync_feed(other)["status"], "conflict")

    def test_missing_branch_failure_retains_previous(self):
        self.publish({"topics/a.md": "# A"})
        self.sync()
        before = self.visible()
        with patch.object(GitFeed, "__init__", side_effect=OSError("offline")):
            result = self.sync()
        self.assertEqual(result["status"], "error")
        self.assertEqual(self.visible(), before)

    def test_standalone_cli_needs_no_vaws_import_or_optional_dependencies(self):
        self.publish({"topics/a.md": "# CLI"})
        config = self.root / "feed.json"
        config.write_text(json.dumps(self.config), encoding="utf8")
        package = str(Path(__file__).resolve().parents[1])
        env = {**os.environ, "PYTHONPATH": package}
        process = subprocess.run([sys.executable, "-m", "knowledge_intake.feed_sync", "sync", str(config)],
                                 cwd=self.root, env=env, capture_output=True, timeout=20)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout)["status"], "updated")
        check = subprocess.run([sys.executable, "-c", "import knowledge_intake.feed_sync,sys; assert not any(n.startswith('vaws_') for n in sys.modules)"],
                               cwd=self.root, env=env, capture_output=True)
        self.assertEqual(check.returncode, 0, check.stderr)


class ScheduleTests(unittest.TestCase):
    def test_xml_is_per_user_hourly_and_logon_without_password_or_shell_arguments(self):
        config = Path(tempfile.gettempdir()) / 'feed with spaces & unicode.json'
        spec = schedule_spec(config)
        document = ET.fromstring(task_xml(spec, "S-1-5-21-test"))
        ns = {"t": NS}
        self.assertEqual(document.find("t:Triggers/t:TimeTrigger/t:Repetition/t:Interval", ns).text, "PT1H")
        self.assertIsNotNone(document.find("t:Triggers/t:LogonTrigger", ns))
        self.assertEqual(document.find("t:Principals/t:Principal/t:LogonType", ns).text, "InteractiveToken")
        self.assertEqual(document.find("t:Principals/t:Principal/t:RunLevel", ns).text, "LeastPrivilege")
        self.assertEqual(document.find("t:Actions/t:Exec/t:Arguments", ns).text, spec["arguments"])
        self.assertIn('"' + str(config.resolve()) + '"', spec["arguments"])
        self.assertEqual(schedule_spec(config)["description"], spec["description"])
        self.assertNotEqual(schedule_spec(config.with_name("different.json"))["name"], spec["name"])

    def test_manage_does_not_register_on_import_and_passes_explicit_operation(self):
        from knowledge_intake import schedule
        with patch.object(schedule, "_powershell", return_value={"status": "absent"}) as invoke:
            if os.name == "nt":
                result = schedule.manage_schedule("uninstall", Path("missing-feed.json"))
                self.assertEqual(result["status"], "absent")
                self.assertEqual(invoke.call_args.args[0]["operation"], "uninstall")
            else:
                with self.assertRaisesRegex(Exception, "Windows"):
                    schedule.manage_schedule("status", Path("missing-feed.json"))
                invoke.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "actual PowerShell syntax seam is Windows only")
    def test_actual_powershell_install_replay_uninstall_and_owner_conflict_with_fake_service(self):
        from knowledge_intake.schedule import _script
        spec = schedule_spec(Path(tempfile.gettempdir()) / 'feed spaces & quotes.json')
        setup = r'''
$global:fixtureTask = $null
$global:registered = 0
function Get-ScheduledTask { param($TaskName,$TaskPath,$ErrorAction) return $global:fixtureTask }
function Register-ScheduledTask { param($TaskName,$TaskPath,$Xml,[switch]$Force)
 $global:registered += 1
 [xml]$x=$Xml
 $a=$x.Task.Actions.Exec
 $sid=[Security.Principal.WindowsIdentity]::GetCurrent().Name.Split('\')[-1]
 $global:fixtureTask=[pscustomobject]@{
  Description=[string]$x.Task.RegistrationInfo.Description
  Actions=@([pscustomobject]@{Execute=[string]$a.Command;Arguments=[string]$a.Arguments;WorkingDirectory=[string]$a.WorkingDirectory})
  Triggers=@([pscustomobject]@{CimClass=@{CimClassName='MSFT_TaskTimeTrigger'};Repetition=@{Interval='PT1H'};Enabled=$true},[pscustomobject]@{CimClass=@{CimClassName='MSFT_TaskLogonTrigger'};UserId=$sid;Enabled=$true})
  Settings=@{Enabled=$true};Principal=@{UserId=$sid;RunLevel=0}
 }
}
function Unregister-ScheduledTask { param($TaskName,$TaskPath,$Confirm) $global:fixtureTask=$null }
'''
        script = setup
        for operation in ("install", "install", "status", "uninstall", "uninstall"):
            script += _script({"operation": operation, "spec": spec, "xml": task_xml(spec)})
        script += "\nif ($global:registered -ne 1) { throw 'registration replayed' }\n"
        encoded = base64.b64encode("& ([scriptblock]::Create([Console]::In.ReadToEnd()))".encode("utf-16-le")).decode()
        process = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                                 input=script.encode("utf-8"), capture_output=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertEqual(process.returncode, 0, process.stderr.decode(errors="replace"))
        self.assertEqual([json.loads(line)["status"] for line in process.stdout.splitlines()],
                         ["installed", "unchanged", "present", "uninstalled", "absent"])
        conflict = setup + "$global:fixtureTask=[pscustomobject]@{Description='someone else'}\n" + _script({"operation":"uninstall","spec":spec,"xml":task_xml(spec)})
        process = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                                 input=conflict.encode("utf-8"), capture_output=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn(b"another owner", process.stderr)


if __name__ == "__main__":
    unittest.main()
