"""项目路径配置。所有路径都相对项目根目录，方便在别的机器上直接运行。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

RAW_REPO = ROOT / "data" / "raw" / "ArknightsGameData"
GAMEDATA = RAW_REPO / "zh_CN" / "gamedata"
EXCEL = GAMEDATA / "excel"
STORY = GAMEDATA / "story"

CURATED = ROOT / "data" / "curated"
STRUCTURED = ROOT / "data" / "structured"
SITE = ROOT / "site"
SITE_DATA = SITE / "data"

DATA_REPO_URL = "https://github.com/Kengxxiao/ArknightsGameData"
SPARSE_PATHS = ["zh_CN/gamedata/story", "zh_CN/gamedata/excel"]
