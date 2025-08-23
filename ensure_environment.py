"""
Helper module to ensure the virtual environment is active
and all dependencies are installed before running the app.
"""
import os
import sys
import subprocess
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

VENV_NAME = "myenv"
REQUIRED_PACKAGES = [
    "django",
    "requests",
    "bs4",
    "google-generativeai"  # For Gemini API
]


def is_venv_active():
    """Check if a virtual environment is active"""
    return hasattr(sys, 'real_prefix') or (
        hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix
    )


def activate_venv():
    """Activate the virtual environment"""
    venv_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), VENV_NAME)
    
    # Check if venv exists
    if not os.path.exists(venv_dir):
        logger.info(f"Creating virtual environment '{VENV_NAME}'...")
        try:
            subprocess.check_call([sys.executable, "-m", "venv", venv_dir])
            logger.info("Virtual environment created successfully")
        except subprocess.CalledProcessError:
            logger.error("Failed to create virtual environment")
            return False
    
    # Construct activation script path based on OS
    if sys.platform == 'win32':
        activate_script = os.path.join(venv_dir, "Scripts", "activate")
        activate_cmd = f"{activate_script}"
    else:
        activate_script = os.path.join(venv_dir, "bin", "activate")
        activate_cmd = f"source {activate_script}"
    
    logger.info(f"Please activate the virtual environment with: {activate_cmd}")
    return False


def install_packages():
    """Install required packages if they're not already installed"""
    if not is_venv_active():
        logger.warning("Virtual environment is not active! Packages will be installed globally.")
        response = input("Do you want to continue with global installation? (y/n): ")
        if response.lower() != 'y':
            logger.info("Installation aborted.")
            return False
    
    for package in REQUIRED_PACKAGES:
        try:
            logger.info(f"Checking if {package} is installed...")
            __import__(package.replace('-', '_'))
            logger.info(f"{package} is already installed.")
        except ImportError:
            logger.info(f"Installing {package}...")
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", package])
                logger.info(f"{package} installed successfully")
            except subprocess.CalledProcessError:
                logger.error(f"Failed to install {package}")
                return False
    
    logger.info("All required packages are installed.")
    return True


def ensure_environment():
    """Ensure the environment is properly set up"""
    if not is_venv_active():
        return activate_venv()
    
    return install_packages()


if __name__ == "__main__":
    if ensure_environment():
        logger.info("Environment is ready.")
    else:
        logger.warning("Environment setup incomplete.")
