from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
PAGE_DIR = DATA_DIR / "pages"
VECTOR_DIR = DATA_DIR / "vectorstore"


class Settings(BaseSettings):
    APP_NAME: str = "smart-doc-ai-engine"
    HOST: str = "0.0.0.0"
    PORT: int = 8001

    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    EMBEDDING_MODEL: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    # 论文 PDF 默认可作基线；对比实验可改 PDF_RENDER_DPI（如 200 / 220 / 240）
    PDF_RENDER_DPI: int = 220
    OCR_USE_ANGLE_CLS: bool = False
    #使用cpu加速
    OCR_ENABLE_MKLDNN: bool = True
    OCR_CPU_THREADS: int = 6
    OCR_FILTER_MIN_SCORE: float = 0.35

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        extra="ignore",
    )


settings = Settings()
#父目录不存在时一起创建  目录已存在时不报错
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
PAGE_DIR.mkdir(parents=True, exist_ok=True)
VECTOR_DIR.mkdir(parents=True, exist_ok=True)
