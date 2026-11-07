"""项目路径配置。所有路径都相对项目根目录，方便在别的机器上直接运行。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 版本号。发行版（公开）的 tag 和文件名是 O<版本号>，本地版（含剧本全文）的文件名是 <版本号>。
# 发版前由用户定，改这里再提交。
VERSION = "1.1"

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
