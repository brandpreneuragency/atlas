import pytest

from app.files.safe_path import PathViolation, resolve_safe


@pytest.fixture
def jail(tmp_path):
    (tmp_path / "01_inbox").mkdir()
    (tmp_path / "01_inbox" / "a.md").write_text("x")
    return tmp_path


def test_normal_relative_path(jail):
    assert resolve_safe(jail, "01_inbox/a.md") == jail / "01_inbox" / "a.md"


def test_empty_is_root(jail):
    assert resolve_safe(jail, "") == jail


@pytest.mark.parametrize("bad", [
    "../etc/passwd", "..", "01_inbox/../../etc", "/etc/passwd",
    "C:\\Windows", "01_inbox/%2e%2e/secret", "..\\..\\x",
    "01_inbox/\x00hack", "~/.ssh/id_rsa",
])
def test_traversal_rejected(jail, bad):
    with pytest.raises(PathViolation):
        resolve_safe(jail, bad)


def test_symlink_escape_rejected(jail, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside")
    try:
        (jail / "link").symlink_to(outside)
    except OSError:
        pytest.skip("symlinks unavailable on this platform (Windows non-admin)")
    with pytest.raises(PathViolation):
        resolve_safe(jail, "link/escape.txt")
