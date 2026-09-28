import hashlib
import subprocess
import zipfile

import pytest

from campus.artifacts import generate_document, package_repository, read_document, validate_artifact
from campus.models import CampusError
from campus.security import Capability, authorize, inside, redact


@pytest.mark.parametrize("cap", [Capability.WRITE_REMOTE, Capability.SUBMIT, Capability.SEND_EMAIL])
def test_remote_writes_never_execute(cap):
    assert authorize(cap)["executed"] is False
    with pytest.raises(CampusError):
        authorize(cap, confirmed=True, dry_run=False)


def test_output_traversal_rejected(tmp_path):
    with pytest.raises(CampusError):
        inside(tmp_path, tmp_path / ".." / "escape.zip")


def test_terminal_and_password_redaction(monkeypatch):
    monkeypatch.setenv("MOODLE_PASSWORD", "secret-example-value")
    assert "secret-example-value" not in redact("secret-example-value")
    assert "\x1b" not in redact("\x1b[2Jmalicious")


@pytest.fixture
def repository(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    (repo / "main.py").write_text("print('hello')\n", encoding="utf-8")
    (repo / "README.md").write_text("Example source project", encoding="utf-8")
    (repo / ".env").write_text("NOT_A_REAL_CREDENTIAL=example", encoding="utf-8")
    (repo / "credentials.json").write_text("{}", encoding="utf-8")
    (repo / "unsafe.txt").write_text("password = synthetic-test-only", encoding="utf-8")
    (repo / "binary.zip").write_bytes(b"not-an-archive")
    (repo / "untracked.txt").write_text("private note", encoding="utf-8")
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "add",
            "main.py",
            "README.md",
            ".env",
            "credentials.json",
            "unsafe.txt",
            "binary.zip",
        ],
        check=True,
        capture_output=True,
    )
    return repo


def test_zip_secret_exclusion_and_reproducibility(repository, tmp_path):
    one, two = tmp_path / "one.zip", tmp_path / "two.zip"
    result = package_repository(repository, one)
    package_repository(repository, two)
    assert set(result["included"]) == {"main.py", "README.md"}
    with zipfile.ZipFile(one) as archive:
        assert set(archive.namelist()) == {"main.py", "README.md"}
        assert archive.testzip() is None
    assert one.read_bytes() == two.read_bytes()
    assert hashlib.sha256(one.read_bytes()).hexdigest() == result["sha256"]


@pytest.mark.parametrize("extension", ["md", "txt", "pdf", "docx"])
def test_documents_validate_extract_and_repeat(tmp_path, extension):
    first = tmp_path / ("first." + extension)
    second = tmp_path / ("second." + extension)
    text = "Academic report\nRequisitos e validação local."
    generate_document(text, first)
    generate_document(text, second)
    assert validate_artifact(first)
    assert "Academic report" in read_document(first)
    assert first.read_bytes() == second.read_bytes()


def test_document_secret_rejected(tmp_path):
    with pytest.raises(CampusError):
        generate_document("-----BEGIN PRIVATE KEY-----\nexample", tmp_path / "leak.txt")


def test_artifact_wont_overwrite(tmp_path):
    target = tmp_path / "keep.md"
    target.write_text("keep", encoding="utf-8")
    with pytest.raises(CampusError):
        generate_document("replace", target)
    assert target.read_text() == "keep"
