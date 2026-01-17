# Makefile for Humble Bundle Downloader

.PHONY: install install-gui build-app build-app-dev clean test

# Install CLI dependencies with pip
install:
	pip install -e .

# Install with macOS GUI support (pip)
install-gui:
	pip install -e .
	pip install pyobjc-core pyobjc-framework-Cocoa py2app

# Build standalone macOS app (production)
build-app: install-gui
	rm -rf build dist
	python setup_app.py py2app
	@echo ""
	@echo "Build complete! App is at: dist/Humble Bundle Downloader.app"
	@echo "To install, drag the app to your Applications folder."

# Build macOS app in development mode (faster, creates alias)
build-app-dev: install-gui
	rm -rf build dist
	python setup_app.py py2app -A
	@echo ""
	@echo "Development build complete! App is at: dist/Humble Bundle Downloader.app"
	@echo "Note: This is an alias build - it requires the source files to remain in place."

# Create DMG installer (requires create-dmg: brew install create-dmg)
build-dmg: build-app
	rm -f "dist/HumbleBundleDownloader.dmg"
	create-dmg \
		--volname "Humble Bundle Downloader" \
		--window-pos 200 120 \
		--window-size 600 400 \
		--icon-size 100 \
		--icon "Humble Bundle Downloader.app" 150 190 \
		--app-drop-link 450 190 \
		"dist/HumbleBundleDownloader.dmg" \
		"dist/Humble Bundle Downloader.app"
	@echo ""
	@echo "DMG created at: dist/HumbleBundleDownloader.dmg"

# Clean build artifacts
clean:
	rm -rf build dist *.egg-info .eggs
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

# Run tests
test:
	python -m pytest

# Run the GUI directly (without building)
run-gui: install-gui
	python -m humblebundle_downloader.gui

# Run the CLI
run-cli:
	hbd --help
