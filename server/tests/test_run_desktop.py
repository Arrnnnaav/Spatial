import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from run_desktop import pairing_token


def test_pairing_token_is_random_and_persistent(tmp_path):
    first = pairing_token(tmp_path)
    assert len(first) == 64
    assert pairing_token(tmp_path) == first
    (tmp_path / "api.token").write_text("invalid", encoding="ascii")
    assert pairing_token(tmp_path) != first
