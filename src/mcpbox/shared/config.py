import os
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv


class Config:
    """Configuration class for MCP Box"""

    def __init__(self) -> None:
        # API Configuration
        self.MCPBOX_API_URL = get_env("MCPBOX_API_URL")

        # AWS Configurations
        self.AWS_REGION = get_env("AWS_REGION")
        self.AWS_ACCESS_KEY_ID = get_env("AWS_ACCESS_KEY_ID")
        self.AWS_SECRET_ACCESS_KEY = get_env("AWS_SECRET_ACCESS_KEY")
        self.S3_BUCKET_NAME = get_env("S3_BUCKET_NAME")
        self.LAMBDA_BASE_URL = get_env("LAMBDA_BASE_URL")

        # Firebase Configuration
        self.FIREBASE_API_KEY = get_env("FIREBASE_API_KEY")
        self.FIREBASE_PROJECT_ID = get_env("FIREBASE_PROJECT_ID")

        # OAuth Configurations
        self.GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
        self.GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
        self.GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID")
        self.GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET")

        # Scanners Configurations
        self.SONAR_TOKEN = get_env("SONAR_TOKEN")
        self.SONAR_ORGANIZATION = get_env("SONAR_ORGANIZATION")
        self.GITGUARDIAN_API_KEY = get_env("GITGUARDIAN_API_KEY")

        # Razorpay Configurations
        self.RAZORPAY_KEY_ID = get_env("RAZORPAY_KEY_ID")
        self.RAZORPAY_KEY_SECRET = get_env("RAZORPAY_KEY_SECRET")

    def validate_server(self) -> bool:
        """Validate required configuration for server"""
        required = {
            "MCPBOX_API_URL": self.MCPBOX_API_URL,
            "AWS_REGION": self.AWS_REGION,
            "AWS_ACCESS_KEY_ID": self.AWS_ACCESS_KEY_ID,
            "AWS_SECRET_ACCESS_KEY": self.AWS_SECRET_ACCESS_KEY,
            "S3_BUCKET_NAME": self.S3_BUCKET_NAME,
            "LAMBDA_BASE_URL": self.LAMBDA_BASE_URL,
            "FIREBASE_API_KEY": self.FIREBASE_API_KEY,
            "FIREBASE_PROJECT_ID": self.FIREBASE_PROJECT_ID,
            "RAZORPAY_KEY_ID": self.RAZORPAY_KEY_ID,
            "RAZORPAY_KEY_SECRET": self.RAZORPAY_KEY_SECRET,
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            raise ValueError(f"Missing required config: {', '.join(missing)}")
        return True

    def validate_cli(self) -> bool:
        """Validate required configuration for CLI"""
        required = {
            "MCPBOX_API_URL": self.MCPBOX_API_URL,
            "AWS_REGION": self.AWS_REGION,
            "AWS_ACCESS_KEY_ID": self.AWS_ACCESS_KEY_ID,
            "AWS_SECRET_ACCESS_KEY": self.AWS_SECRET_ACCESS_KEY,
            "S3_BUCKET_NAME": self.S3_BUCKET_NAME,
            "FIREBASE_API_KEY": self.FIREBASE_API_KEY,
            "FIREBASE_PROJECT_ID": self.FIREBASE_PROJECT_ID,
            "SONAR_TOKEN": self.SONAR_TOKEN,
            "SONAR_ORGANIZATION": self.SONAR_ORGANIZATION,
            "GITGUARDIAN_API_KEY": self.GITGUARDIAN_API_KEY,
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            raise ValueError(f"Missing required config: {', '.join(missing)}")
        return True


class ServerConfig:
    """Server settings and middleware configuration"""

    def app_params(self) -> Dict[str, Any]:
        return {
            "title": "MCP Box Server",
            "description": "API server for MCP server registry and management",
            "version": "1.0.0",
        }

    def cors_params(self) -> Dict[str, Any]:
        return {
            "allow_origins": ["*"],
            "allow_credentials": True,
            "allow_methods": ["*"],
            "allow_headers": ["*"],
        }


def load_env(env_path: Optional[os.PathLike | str] = None) -> None:
    """Load environment variables from .env file"""
    if env_path is None:
        env_path = Path.cwd() / ".env"
    else:
        env_path = Path(env_path)

    if env_path.exists():
        load_dotenv(env_path)


def get_env(key: str) -> str:
    """Get environment variable - raises error if not found"""
    value = os.environ.get(key)
    if value is None:
        raise ValueError(f"Required environment variable '{key}' not found")
    return value
