from pathlib import Path
import sys
import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


@pytest.fixture()
def tmp_env(tmp_path: Path):
    data_dir = tmp_path / "dados"
    backup_dir = tmp_path / "backups"
    data_dir.mkdir(parents=True, exist_ok=True)
    backup_dir.mkdir(parents=True, exist_ok=True)
    return {
        "DATA_DIR": str(data_dir),
        "BACKUP_DIR": str(backup_dir),
        "TESTING": True,
    }
