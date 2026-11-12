import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings:
    APP_TITLE: str = "BOM / BOQ Studio Pro"
    APP_DESCRIPTION: str = "Enterprise Bill of Materials & Quantities Management System"
    APP_VERSION: str = "2.1.0"
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "b0m-sUpEr-s3cr3t-kEy-998822-ph-engr-alex-2026")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    COOKIE_NAME: str = "bom_session_token"
    
    # Storage & Persistence (supports Docker data mount)
    DATA_DIR: Path = Path(os.getenv("DATA_DIR", str(BASE_DIR)))
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{Path(os.getenv('DATA_DIR', str(BASE_DIR))) / 'bom_system.db'}")
    
    # Storage
    UPLOAD_DIR: Path = Path(os.getenv("UPLOAD_DIR", str(Path(os.getenv('DATA_DIR', str(BASE_DIR))) / "uploads")))
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10 MB
    ALLOWED_EXTENSIONS: set = {"pdf", "jpg", "jpeg", "png"}
    
    # Seeding
    AUTO_SEED: bool = os.getenv("AUTO_SEED", "true").lower() in ("true", "1", "yes")
    
    # Host & Port
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    
    # Tailscale & Funnel
    TS_HOSTNAME: str = os.getenv("TS_HOSTNAME", "bom")
    TS_TAILNET: str = os.getenv("TS_TAILNET", "ratfish-regulus.ts.net")
    FUNNEL_URL: str = os.getenv("FUNNEL_URL", f"https://{os.getenv('TS_HOSTNAME', 'bom')}.{os.getenv('TS_TAILNET', 'ratfish-regulus.ts.net')}")

settings = Settings()

# Ensure uploads directory exists
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
