"""
py2app build script for Humble Bundle Downloader macOS app.

Usage:
    # Development mode (creates alias, faster for testing)
    python setup_app.py py2app -A

    # Production build (standalone .app bundle)
    python setup_app.py py2app

The built app will be in the 'dist' folder.
"""

from setuptools import setup

APP = ["humblebundle_downloader/gui.py"]
APP_NAME = "Humble Bundle Downloader"

DATA_FILES = []

OPTIONS = {
    "argv_emulation": False,
    "iconfile": "assets/icon.icns",  # Optional: add your own icon
    "plist": {
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleIdentifier": "com.humblebundle.downloader",
        "CFBundleVersion": "0.4.3",
        "CFBundleShortVersionString": "0.4.3",
        "LSMinimumSystemVersion": "10.15",
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,  # Support dark mode
        "LSApplicationCategoryType": "public.app-category.utilities",
        "NSHumanReadableCopyright": "MIT License",
    },
    "packages": [
        "humblebundle_downloader",
        "requests",
        "parsel",
        "lxml",
        "urllib3",
        "certifi",
        "charset_normalizer",
        "idna",
    ],
    "includes": [
        "objc",
        "Foundation",
        "AppKit",
    ],
    "excludes": [
        "tkinter",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "wx",
        "matplotlib",
        "numpy",
        "pandas",
        "scipy",
        "PIL",
        "cv2",
    ],
    "strip": True,
    "optimize": 2,
}

setup(
    name=APP_NAME,
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
