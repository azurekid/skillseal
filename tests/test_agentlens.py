import copy
import io
import json
from email import policy
from email.parser import BytesParser
from http.client import IncompleteRead
from urllib.error import HTTPError, URLError

import pytest

from conftest import make_skill
from skillseal import agentlens
from skillseal.cli import main
from skillseal.scan import ScanError

URL = "https://scanner.example.test"


def report_for(skill):
    return {
        "status": "complete",
        "skipped": [],
        "files": [
            {"path": f"{skill.name}/SKILL.md", "findings": []},
            {"path": f"{skill.name}/scripts/run.sh", "findings": []},
        ],
    }


def mock_report(monkeypatch, report):
    monkeypatch.setattr(agentlens, "urlopen", lambda *args, **kwargs: io.BytesIO(json.dumps(report).encode()))


def test_uploads_exact_skill_contents_without_signature_or_git(tmp_path, monkeypatch, capsys):
    skill = make_skill(tmp_path)
    (skill / "skill.oms.sig").write_text("old approval")
    (skill / ".git").mkdir()
    (skill / ".git/config").write_text("not submitted")
    script = skill / "scripts" / "hello.py"
    script.write_text("print('hello')\n")
    report = report_for(skill)
    report["files"].append({"path": f"{skill.name}/scripts/hello.py", "findings": []})

    def request_scan(request, timeout):
        assert request.full_url == URL + "/api/scan/files"
        assert request.method == "POST"
        assert timeout == 120
        message = BytesParser(policy=policy.default).parsebytes(
            f"Content-Type: {request.get_header('Content-type')}\r\n\r\n".encode() + request.data
        )
        parts = list(message.iter_parts())
        assert [part.get_payload(decode=True) for part in parts[:2]] == [b"true", b"false"]
        assert {part.get_filename(): part.get_payload(decode=True) for part in parts[2:]} == {
            f"{skill.name}/SKILL.md": (skill / "SKILL.md").read_bytes(),
            f"{skill.name}/scripts/run.sh": (skill / "scripts/run.sh").read_bytes(),
            f"{skill.name}/scripts/hello.py": script.read_bytes(),
        }
        return io.BytesIO(json.dumps(report).encode())

    monkeypatch.setattr(agentlens, "urlopen", request_scan)
    assert main(["scan", "--agentlens-url", URL, str(skill)]) == 0
    assert "no AgentLens findings" in capsys.readouterr().out


@pytest.mark.parametrize(("severity", "threshold", "expected"), [
    ("CRITICAL", "HIGH", 1), ("HIGH", "HIGH", 1), ("MEDIUM", "HIGH", 0),
    ("LOW", "LOW", 1), ("HIGH", "CRITICAL", 0),
])
def test_remote_severity_gate(tmp_path, monkeypatch, capsys, severity, threshold, expected):
    skill = make_skill(tmp_path)
    report = report_for(skill)
    report["files"][0]["findings"] = [
        {"severity": severity, "line": 2, "rule": "TEST-001", "message": "Synthetic test finding"},
    ]
    mock_report(monkeypatch, report)
    assert main(["scan", "--agentlens-url", URL, "--fail-on", threshold, str(skill)]) == expected
    assert f"[{severity}] {skill / 'SKILL.md'}:2: TEST-001" in capsys.readouterr().out


@pytest.mark.parametrize("change", [
    {"status": "partial"}, {"status": "no_targets"}, {"skipped": ["unsupported"]},
    {"skipped": None}, {"files": []}, {"files": None}, {"files": [None]},
    {"files": [{"path": "unexpected/SKILL.md", "findings": []}]},
    {"files": [{"path": "demo/SKILL.md", "findings": None}]},
])
def test_incomplete_or_invalid_results_block(tmp_path, monkeypatch, capsys, change):
    skill = make_skill(tmp_path)
    report = report_for(skill)
    report.update(change)
    mock_report(monkeypatch, report)
    assert main(["scan", "--agentlens-url", URL, str(skill)]) == 2
    assert "[ERROR]" in capsys.readouterr().err


@pytest.mark.parametrize("finding", [
    None, {}, {"severity": "UNKNOWN", "line": 1, "rule": "TEST", "message": "test"},
    {"severity": "HIGH", "line": True, "rule": "TEST", "message": "test"},
    {"severity": "HIGH", "line": 1, "rule": None, "message": "test"},
])
def test_invalid_findings_block(tmp_path, monkeypatch, finding):
    skill = make_skill(tmp_path)
    report = report_for(skill)
    report["files"][0]["findings"] = [finding]
    mock_report(monkeypatch, report)
    with pytest.raises(ScanError, match="invalid finding"):
        agentlens.scan_agentlens(skill, URL)


def test_duplicate_results_block(tmp_path, monkeypatch):
    skill = make_skill(tmp_path)
    report = report_for(skill)
    report["files"].append(copy.deepcopy(report["files"][0]))
    mock_report(monkeypatch, report)
    with pytest.raises(ScanError, match="duplicate"):
        agentlens.scan_agentlens(skill, URL)


@pytest.mark.parametrize("error", [
    URLError("unavailable"), TimeoutError("timed out"),
    IncompleteRead(b""),
    HTTPError(URL, 503, "unavailable", {}, None),
])
def test_network_errors_block(tmp_path, monkeypatch, capsys, error):
    skill = make_skill(tmp_path)

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(agentlens, "urlopen", fail)
    assert main(["scan", "--agentlens-url", URL, str(skill)]) == 2
    assert "AgentLens scan failed" in capsys.readouterr().err


def test_non_json_response_blocks(tmp_path, monkeypatch):
    skill = make_skill(tmp_path)
    monkeypatch.setattr(agentlens, "urlopen", lambda *args, **kwargs: io.BytesIO(b"<html>unavailable</html>"))
    with pytest.raises(ScanError, match="AgentLens scan failed"):
        agentlens.scan_agentlens(skill, URL)


@pytest.mark.parametrize("url", ["http://scanner.test", "https://user:pass@scanner.test",
                               "https://scanner.test?token=test", "https://scanner.test/#fragment"])
def test_invalid_urls_do_not_upload(tmp_path, monkeypatch, url):
    skill = make_skill(tmp_path)
    monkeypatch.setattr(agentlens, "urlopen", lambda *args, **kwargs: pytest.fail("must not upload"))
    with pytest.raises(ScanError, match="HTTPS base URL"):
        agentlens.scan_agentlens(skill, url)


@pytest.mark.parametrize("size", [256 * 1024 + 1, 5 * 1024 * 1024 + 1])
def test_oversized_files_do_not_upload(tmp_path, monkeypatch, size):
    skill = make_skill(tmp_path)
    (skill / "SKILL.md").write_bytes(b"x" * size)
    monkeypatch.setattr(agentlens, "urlopen", lambda *args, **kwargs: pytest.fail("must not upload"))
    with pytest.raises(ScanError, match="256 KiB"):
        agentlens.scan_agentlens(skill, URL)


def test_aggregate_upload_limit_blocks_before_network(tmp_path, monkeypatch):
    skill = make_skill(tmp_path)
    for index in range(21):
        (skill / f"part-{index}.md").write_bytes(b"x" * (256 * 1024))
    monkeypatch.setattr(agentlens, "urlopen", lambda *args, **kwargs: pytest.fail("must not upload"))
    with pytest.raises(ScanError, match="5 MiB"):
        agentlens.scan_agentlens(skill, URL)


def test_file_count_limit_blocks_before_network(tmp_path, monkeypatch):
    skill = make_skill(tmp_path)
    for index in range(499):
        (skill / f"part-{index}.md").write_text("hello")
    monkeypatch.setattr(agentlens, "urlopen", lambda *args, **kwargs: pytest.fail("must not upload"))
    with pytest.raises(ScanError, match="500 files"):
        agentlens.scan_agentlens(skill, URL)


def test_local_scanning_remains_offline(tmp_path, monkeypatch, capsys):
    skill = make_skill(tmp_path)
    monkeypatch.setattr(agentlens, "urlopen", lambda *args, **kwargs: pytest.fail("must not upload"))
    assert main(["scan", str(skill)]) == 0
    assert "no heuristic findings" in capsys.readouterr().out


def test_remote_error_removes_previous_approval_when_signing(tmp_path, monkeypatch, capsys):
    skill = make_skill(tmp_path)
    signature = skill / "skill.oms.sig"
    signature.write_text("previous approval")
    command = f"skillseal scan --agentlens-url {URL} {{path}}"

    def run_scan(command, path):
        assert main(["scan", "--agentlens-url", URL, str(path)]) == 2
        return False, "AgentLens scan failed"

    mock_report(monkeypatch, {"status": "partial"})
    monkeypatch.setattr("skillseal.cli.run_scanner", run_scan)
    assert main(["sign", "--scan", command, str(skill)]) == 1
    assert not signature.exists()
    assert "[BLOCKED]" in capsys.readouterr().err
