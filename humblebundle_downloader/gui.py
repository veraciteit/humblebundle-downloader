"""
Native macOS GUI for Humble Bundle Downloader using PyObjC.

This module provides a full-featured download manager interface with:
- Library browser to view all bundles and products
- Download queue with progress tracking
- Settings panel for authentication and preferences
- Menu bar integration

Install with: poetry install --with macos-gui
Run with: hbd-gui
"""

import os
import sys
import json
import threading
from pathlib import Path

# Check for macOS
if sys.platform != "darwin":
    print("Error: The GUI is only available on macOS.")
    print("Use the command-line interface instead: hbd --help")
    sys.exit(1)

try:
    import objc
    from Foundation import (
        NSObject,
        NSUserDefaults,
        NSHomeDirectory,
        NSNotificationCenter,
        NSThread,
    )
    from AppKit import (
        NSApplication,
        NSApp,
        NSWindow,
        NSWindowStyleMaskTitled,
        NSWindowStyleMaskClosable,
        NSWindowStyleMaskMiniaturizable,
        NSWindowStyleMaskResizable,
        NSBackingStoreBuffered,
        NSView,
        NSTextField,
        NSSecureTextField,
        NSButton,
        NSButtonTypeSwitch,
        NSProgressIndicator,
        NSProgressIndicatorStyleBar,
        NSTableView,
        NSTableColumn,
        NSScrollView,
        NSOutlineView,
        NSSplitView,
        NSToolbar,
        NSToolbarItem,
        NSImage,
        NSImageNameFolder,
        NSImageNameRefreshTemplate,
        NSImageNameActionTemplate,
        NSMenu,
        NSMenuItem,
        NSAlert,
        NSAlertStyleWarning,
        NSAlertStyleInformational,
        NSOpenPanel,
        NSStatusBar,
        NSVariableStatusItemLength,
        NSFont,
        NSColor,
        NSBezelStyleRounded,
        NSTextFieldCell,
        NSTableViewSelectionHighlightStyleRegular,
        NSControlStateValueOn,
        NSControlStateValueOff,
        NSLayoutConstraint,
        NSStackView,
        NSUserInterfaceLayoutOrientationVertical,
        NSUserInterfaceLayoutOrientationHorizontal,
        NSBoxSeparator,
        NSBox,
        NSTabView,
        NSTabViewItem,
    )
except ImportError:
    print("Error: PyObjC is not installed.")
    print("Install it with: poetry install --with macos-gui")
    print("Or: pip install pyobjc-core pyobjc-framework-Cocoa")
    sys.exit(1)

from .download_library import DownloadLibrary, _clean_name

# App constants
APP_NAME = "Humble Bundle Downloader"
BUNDLE_ID = "com.humblebundle.downloader"
DEFAULT_LIBRARY_PATH = os.path.join(NSHomeDirectory(), "Downloads", "HumbleBundle")
SETTINGS_FILE = os.path.join(NSHomeDirectory(), ".hbd_settings.json")


class Settings:
    """Manages application settings persistence."""

    def __init__(self):
        self.settings_path = SETTINGS_FILE
        self._data = self._load()

    def _load(self):
        try:
            with open(self.settings_path, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {
                "library_path": DEFAULT_LIBRARY_PATH,
                "cookie_path": "",
                "session_auth": "",
                "progress_bar": True,
                "notifications": True,
                "ext_include": [],
                "ext_exclude": [],
                "platform_include": [],
            }

    def save(self):
        os.makedirs(os.path.dirname(self.settings_path), exist_ok=True)
        with open(self.settings_path, "w") as f:
            json.dump(self._data, f, indent=2)

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value
        self.save()


class DownloadItem:
    """Represents a download item in the queue."""

    def __init__(self, name, bundle_name, url, local_path, size=0):
        self.name = name
        self.bundle_name = bundle_name
        self.url = url
        self.local_path = local_path
        self.size = size
        self.downloaded = 0
        self.status = "pending"  # pending, downloading, completed, failed
        self.error = None

    @property
    def progress(self):
        if self.size == 0:
            return 0
        return min(100, int((self.downloaded / self.size) * 100))


class DownloadManager:
    """Manages the download queue and operations."""

    def __init__(self, settings, delegate=None):
        self.settings = settings
        self.delegate = delegate
        self.queue = []
        self.current_download = None
        self.is_running = False
        self._lock = threading.Lock()
        self._downloader = None

    def add_to_queue(self, item):
        with self._lock:
            self.queue.append(item)
        if self.delegate:
            self.delegate.downloadQueueUpdated()

    def start_downloads(self):
        if self.is_running:
            return
        self.is_running = True
        thread = threading.Thread(target=self._download_loop, daemon=True)
        thread.start()

    def stop_downloads(self):
        self.is_running = False

    def _download_loop(self):
        while self.is_running:
            with self._lock:
                pending = [item for item in self.queue if item.status == "pending"]
                if not pending:
                    self.is_running = False
                    break
                self.current_download = pending[0]
                self.current_download.status = "downloading"

            if self.delegate:
                self._notify_delegate("downloadStarted", self.current_download)

            try:
                self._perform_download(self.current_download)
                self.current_download.status = "completed"
            except Exception as e:
                self.current_download.status = "failed"
                self.current_download.error = str(e)

            if self.delegate:
                self._notify_delegate("downloadFinished", self.current_download)

            self.current_download = None

    def _perform_download(self, item):
        """Perform the actual download using requests."""
        import requests

        os.makedirs(os.path.dirname(item.local_path), exist_ok=True)

        session = requests.Session()
        cookie_path = self.settings.get("cookie_path")
        session_auth = self.settings.get("session_auth")

        if cookie_path and os.path.exists(cookie_path):
            with open(cookie_path, "r") as f:
                session.headers.update({"cookie": f.read().strip()})
        elif session_auth:
            session.headers.update(
                {"cookie": f"_simpleauth_sess={session_auth}"}
            )

        response = session.get(item.url, stream=True)
        response.raise_for_status()

        total_size = int(response.headers.get("content-length", 0))
        item.size = total_size

        with open(item.local_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=65536):
                if not self.is_running:
                    raise Exception("Download cancelled")
                f.write(chunk)
                item.downloaded += len(chunk)
                if self.delegate:
                    self._notify_delegate("downloadProgress", item)

    def _notify_delegate(self, method, item):
        """Thread-safe delegate notification."""
        if self.delegate and hasattr(self.delegate, method):
            # Use performSelectorOnMainThread for thread safety
            pass  # Will be handled by polling in the UI


class LibraryDataSource(NSObject):
    """Data source for the library outline view."""

    def init(self):
        self = objc.super(LibraryDataSource, self).init()
        if self is None:
            return None
        self.bundles = []
        self.expanded_bundles = {}
        return self

    def loadLibrary_(self, settings):
        """Load library data from Humble Bundle API."""
        self.bundles = []

        cookie_path = settings.get("cookie_path")
        session_auth = settings.get("session_auth")

        if not cookie_path and not session_auth:
            return

        try:
            downloader = DownloadLibrary(
                settings.get("library_path", DEFAULT_LIBRARY_PATH),
                cookie_path=cookie_path if cookie_path else None,
                cookie_auth=session_auth if session_auth else None,
            )

            # Get purchase keys
            keys = downloader._get_purchase_keys()

            for order_id in keys[:50]:  # Limit for performance
                try:
                    order_url = f"https://www.humblebundle.com/api/v1/order/{order_id}?all_tpkds=true"
                    order_r = downloader.session.get(
                        order_url,
                        headers={
                            "content-type": "application/json",
                            "content-encoding": "gzip",
                        },
                    )
                    order = order_r.json()
                    bundle_title = _clean_name(order["product"]["human_name"])

                    products = []
                    for product in order.get("subproducts", []):
                        product_title = _clean_name(product["human_name"])
                        downloads = []
                        for download_type in product.get("downloads", []):
                            platform = download_type.get("platform", "unknown")
                            for file_type in download_type.get("download_struct", []):
                                if "url" in file_type and "web" in file_type["url"]:
                                    url = file_type["url"]["web"]
                                    filename = url.split("?")[0].split("/")[-1]
                                    downloads.append({
                                        "name": filename,
                                        "url": url,
                                        "platform": platform,
                                    })
                        if downloads:
                            products.append({
                                "name": product_title,
                                "downloads": downloads,
                            })

                    if products:
                        self.bundles.append({
                            "name": bundle_title,
                            "order_id": order_id,
                            "products": products,
                        })
                except Exception:
                    continue

        except Exception as e:
            print(f"Error loading library: {e}")

    # NSOutlineViewDataSource methods
    def outlineView_numberOfChildrenOfItem_(self, outlineView, item):
        if item is None:
            return len(self.bundles)
        if isinstance(item, dict):
            if "products" in item:
                return len(item["products"])
            if "downloads" in item:
                return len(item["downloads"])
        return 0

    def outlineView_isItemExpandable_(self, outlineView, item):
        if item is None:
            return True
        if isinstance(item, dict):
            return "products" in item or "downloads" in item
        return False

    def outlineView_child_ofItem_(self, outlineView, index, item):
        if item is None:
            return self.bundles[index]
        if isinstance(item, dict):
            if "products" in item:
                return item["products"][index]
            if "downloads" in item:
                return item["downloads"][index]
        return None

    def outlineView_objectValueForTableColumn_byItem_(self, outlineView, column, item):
        if item is None:
            return ""
        if isinstance(item, dict):
            return item.get("name", "")
        return str(item)


class DownloadTableDataSource(NSObject):
    """Data source for the download queue table."""

    def init(self):
        self = objc.super(DownloadTableDataSource, self).init()
        if self is None:
            return None
        self.downloads = []
        return self

    def numberOfRowsInTableView_(self, tableView):
        return len(self.downloads)

    def tableView_objectValueForTableColumn_row_(self, tableView, column, row):
        if row >= len(self.downloads):
            return ""

        item = self.downloads[row]
        col_id = column.identifier()

        if col_id == "name":
            return item.name
        elif col_id == "status":
            return item.status.capitalize()
        elif col_id == "progress":
            return f"{item.progress}%"
        elif col_id == "size":
            if item.size > 0:
                mb = item.size / (1024 * 1024)
                return f"{mb:.1f} MB"
            return "Unknown"

        return ""


class SettingsWindowController(NSObject):
    """Controller for the settings window."""

    def init(self):
        self = objc.super(SettingsWindowController, self).init()
        if self is None:
            return None
        self.settings = None
        self.window = None
        self.delegate = None
        return self

    def showWithSettings_delegate_(self, settings, delegate):
        self.settings = settings
        self.delegate = delegate

        # Create window
        frame = ((200, 200), (500, 400))
        style = (
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
            | NSWindowStyleMaskMiniaturizable
        )
        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, style, NSBackingStoreBuffered, False
        )
        self.window.setTitle_("Settings")
        self.window.center()

        content = self.window.contentView()

        # Create tab view
        tabView = NSTabView.alloc().initWithFrame_(((10, 10), (480, 350)))

        # Authentication tab
        authTab = NSTabViewItem.alloc().initWithIdentifier_("auth")
        authTab.setLabel_("Authentication")
        authView = NSView.alloc().initWithFrame_(((0, 0), (480, 320)))
        self._setupAuthTab_(authView)
        authTab.setView_(authView)
        tabView.addTabViewItem_(authTab)

        # Download tab
        downloadTab = NSTabViewItem.alloc().initWithIdentifier_("download")
        downloadTab.setLabel_("Downloads")
        downloadView = NSView.alloc().initWithFrame_(((0, 0), (480, 320)))
        self._setupDownloadTab_(downloadView)
        downloadTab.setView_(downloadView)
        tabView.addTabViewItem_(downloadTab)

        # Filters tab
        filterTab = NSTabViewItem.alloc().initWithIdentifier_("filter")
        filterTab.setLabel_("Filters")
        filterView = NSView.alloc().initWithFrame_(((0, 0), (480, 320)))
        self._setupFilterTab_(filterView)
        filterTab.setView_(filterView)
        tabView.addTabViewItem_(filterTab)

        content.addSubview_(tabView)

        self.window.makeKeyAndOrderFront_(None)

    def _setupAuthTab_(self, view):
        y = 270

        # Cookie file label and field
        label = NSTextField.labelWithString_("Cookie File:")
        label.setFrame_(((20, y), (100, 20)))
        view.addSubview_(label)

        self.cookieField = NSTextField.alloc().initWithFrame_(((130, y), (250, 24)))
        self.cookieField.setStringValue_(self.settings.get("cookie_path", ""))
        view.addSubview_(self.cookieField)

        browseBtn = NSButton.alloc().initWithFrame_(((390, y), (70, 24)))
        browseBtn.setTitle_("Browse")
        browseBtn.setBezelStyle_(NSBezelStyleRounded)
        browseBtn.setTarget_(self)
        browseBtn.setAction_(objc.selector(self.browseCookieFile_, signature=b"v@:@"))
        view.addSubview_(browseBtn)

        y -= 40

        # Session auth label and field
        label2 = NSTextField.labelWithString_("Session Auth:")
        label2.setFrame_(((20, y), (100, 20)))
        view.addSubview_(label2)

        self.sessionField = NSSecureTextField.alloc().initWithFrame_(((130, y), (330, 24)))
        self.sessionField.setStringValue_(self.settings.get("session_auth", ""))
        view.addSubview_(self.sessionField)

        y -= 40

        # Help text
        helpText = NSTextField.labelWithString_(
            "Enter either a cookie file path OR the _simpleauth_sess cookie value.\n"
            "You can find your session cookie in your browser's developer tools."
        )
        helpText.setFrame_(((20, y - 30), (440, 50)))
        helpText.setFont_(NSFont.systemFontOfSize_(11))
        helpText.setTextColor_(NSColor.secondaryLabelColor())
        view.addSubview_(helpText)

        # Save button
        saveBtn = NSButton.alloc().initWithFrame_(((380, 20), (80, 32)))
        saveBtn.setTitle_("Save")
        saveBtn.setBezelStyle_(NSBezelStyleRounded)
        saveBtn.setTarget_(self)
        saveBtn.setAction_(objc.selector(self.saveSettings_, signature=b"v@:@"))
        view.addSubview_(saveBtn)

    def _setupDownloadTab_(self, view):
        y = 270

        # Library path
        label = NSTextField.labelWithString_("Download Path:")
        label.setFrame_(((20, y), (100, 20)))
        view.addSubview_(label)

        self.libraryField = NSTextField.alloc().initWithFrame_(((130, y), (250, 24)))
        self.libraryField.setStringValue_(self.settings.get("library_path", DEFAULT_LIBRARY_PATH))
        view.addSubview_(self.libraryField)

        browseBtn = NSButton.alloc().initWithFrame_(((390, y), (70, 24)))
        browseBtn.setTitle_("Browse")
        browseBtn.setBezelStyle_(NSBezelStyleRounded)
        browseBtn.setTarget_(self)
        browseBtn.setAction_(objc.selector(self.browseLibraryPath_, signature=b"v@:@"))
        view.addSubview_(browseBtn)

        y -= 40

        # Notifications checkbox
        self.notificationsCheck = NSButton.alloc().initWithFrame_(((20, y), (200, 24)))
        self.notificationsCheck.setButtonType_(NSButtonTypeSwitch)
        self.notificationsCheck.setTitle_("Enable notifications")
        self.notificationsCheck.setState_(
            NSControlStateValueOn if self.settings.get("notifications", True) else NSControlStateValueOff
        )
        view.addSubview_(self.notificationsCheck)

        # Save button
        saveBtn = NSButton.alloc().initWithFrame_(((380, 20), (80, 32)))
        saveBtn.setTitle_("Save")
        saveBtn.setBezelStyle_(NSBezelStyleRounded)
        saveBtn.setTarget_(self)
        saveBtn.setAction_(objc.selector(self.saveSettings_, signature=b"v@:@"))
        view.addSubview_(saveBtn)

    def _setupFilterTab_(self, view):
        y = 270

        # Platform filter
        label = NSTextField.labelWithString_("Platforms:")
        label.setFrame_(((20, y), (100, 20)))
        view.addSubview_(label)

        self.platformField = NSTextField.alloc().initWithFrame_(((130, y), (330, 24)))
        platforms = self.settings.get("platform_include", [])
        self.platformField.setStringValue_(", ".join(platforms) if platforms else "all")
        self.platformField.setPlaceholderString_("e.g., ebook, audio, video (or 'all')")
        view.addSubview_(self.platformField)

        y -= 40

        # Include extensions
        label2 = NSTextField.labelWithString_("Include Ext:")
        label2.setFrame_(((20, y), (100, 20)))
        view.addSubview_(label2)

        self.includeField = NSTextField.alloc().initWithFrame_(((130, y), (330, 24)))
        includes = self.settings.get("ext_include", [])
        self.includeField.setStringValue_(", ".join(includes))
        self.includeField.setPlaceholderString_("e.g., pdf, epub, mobi")
        view.addSubview_(self.includeField)

        y -= 40

        # Exclude extensions
        label3 = NSTextField.labelWithString_("Exclude Ext:")
        label3.setFrame_(((20, y), (100, 20)))
        view.addSubview_(label3)

        self.excludeField = NSTextField.alloc().initWithFrame_(((130, y), (330, 24)))
        excludes = self.settings.get("ext_exclude", [])
        self.excludeField.setStringValue_(", ".join(excludes))
        self.excludeField.setPlaceholderString_("e.g., exe, msi")
        view.addSubview_(self.excludeField)

        # Save button
        saveBtn = NSButton.alloc().initWithFrame_(((380, 20), (80, 32)))
        saveBtn.setTitle_("Save")
        saveBtn.setBezelStyle_(NSBezelStyleRounded)
        saveBtn.setTarget_(self)
        saveBtn.setAction_(objc.selector(self.saveSettings_, signature=b"v@:@"))
        view.addSubview_(saveBtn)

    def browseCookieFile_(self, sender):
        panel = NSOpenPanel.openPanel()
        panel.setCanChooseFiles_(True)
        panel.setCanChooseDirectories_(False)
        if panel.runModal():
            path = panel.URLs()[0].path()
            self.cookieField.setStringValue_(path)

    def browseLibraryPath_(self, sender):
        panel = NSOpenPanel.openPanel()
        panel.setCanChooseFiles_(False)
        panel.setCanChooseDirectories_(True)
        panel.setCanCreateDirectories_(True)
        if panel.runModal():
            path = panel.URLs()[0].path()
            self.libraryField.setStringValue_(path)

    def saveSettings_(self, sender):
        self.settings.set("cookie_path", self.cookieField.stringValue())
        self.settings.set("session_auth", self.sessionField.stringValue())
        self.settings.set("library_path", self.libraryField.stringValue())
        self.settings.set("notifications", self.notificationsCheck.state() == NSControlStateValueOn)

        # Parse filters
        platform_text = self.platformField.stringValue().strip()
        if platform_text and platform_text.lower() != "all":
            platforms = [p.strip() for p in platform_text.split(",") if p.strip()]
            self.settings.set("platform_include", platforms)
        else:
            self.settings.set("platform_include", [])

        include_text = self.includeField.stringValue().strip()
        if include_text:
            includes = [e.strip() for e in include_text.split(",") if e.strip()]
            self.settings.set("ext_include", includes)
        else:
            self.settings.set("ext_include", [])

        exclude_text = self.excludeField.stringValue().strip()
        if exclude_text:
            excludes = [e.strip() for e in exclude_text.split(",") if e.strip()]
            self.settings.set("ext_exclude", excludes)
        else:
            self.settings.set("ext_exclude", [])

        self.window.close()

        if self.delegate and hasattr(self.delegate, "settingsSaved"):
            self.delegate.settingsSaved()


class AppDelegate(NSObject):
    """Main application delegate."""

    def init(self):
        self = objc.super(AppDelegate, self).init()
        if self is None:
            return None
        self.settings = Settings()
        self.downloadManager = DownloadManager(self.settings, delegate=self)
        self.libraryDataSource = LibraryDataSource.alloc().init()
        self.downloadDataSource = DownloadTableDataSource.alloc().init()
        self.settingsController = SettingsWindowController.alloc().init()
        return self

    def applicationDidFinishLaunching_(self, notification):
        self._setupMainWindow()
        self._setupMenuBar()
        self._setupStatusItem()

        # Load library in background
        self._loadLibrary()

    def _setupMainWindow(self):
        # Main window
        frame = ((100, 100), (1000, 700))
        style = (
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
            | NSWindowStyleMaskMiniaturizable
            | NSWindowStyleMaskResizable
        )
        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, style, NSBackingStoreBuffered, False
        )
        self.window.setTitle_(APP_NAME)
        self.window.setMinSize_((800, 500))
        self.window.center()

        # Setup toolbar
        self._setupToolbar()

        # Main split view
        content = self.window.contentView()
        splitView = NSSplitView.alloc().initWithFrame_(content.bounds())
        splitView.setVertical_(True)
        splitView.setDividerStyle_(2)  # Thin divider
        splitView.setAutoresizingMask_(18)  # Width + Height

        # Left panel - Library browser
        leftPanel = NSView.alloc().initWithFrame_(((0, 0), (300, 700)))
        self._setupLibraryBrowser(leftPanel)
        splitView.addSubview_(leftPanel)

        # Right panel - Downloads
        rightPanel = NSView.alloc().initWithFrame_(((0, 0), (700, 700)))
        self._setupDownloadPanel(rightPanel)
        splitView.addSubview_(rightPanel)

        content.addSubview_(splitView)
        splitView.setPosition_ofDividerAtIndex_(300, 0)

        self.window.makeKeyAndOrderFront_(None)

    def _setupToolbar(self):
        toolbar = NSToolbar.alloc().initWithIdentifier_("MainToolbar")
        toolbar.setDelegate_(self)
        toolbar.setDisplayMode_(1)  # Icon and label
        toolbar.setAllowsUserCustomization_(False)
        self.window.setToolbar_(toolbar)

    def toolbar_itemForItemIdentifier_willBeInsertedIntoToolbar_(self, toolbar, identifier, flag):
        item = NSToolbarItem.alloc().initWithItemIdentifier_(identifier)

        if identifier == "refresh":
            item.setLabel_("Refresh")
            item.setImage_(NSImage.imageNamed_(NSImageNameRefreshTemplate))
            item.setTarget_(self)
            item.setAction_(objc.selector(self.refreshLibrary_, signature=b"v@:@"))
        elif identifier == "download":
            item.setLabel_("Download All")
            item.setImage_(NSImage.imageNamed_("NSDownloadsTemplate"))
            item.setTarget_(self)
            item.setAction_(objc.selector(self.downloadSelected_, signature=b"v@:@"))
        elif identifier == "settings":
            item.setLabel_("Settings")
            item.setImage_(NSImage.imageNamed_(NSImageNameActionTemplate))
            item.setTarget_(self)
            item.setAction_(objc.selector(self.showSettings_, signature=b"v@:@"))
        elif identifier == "stop":
            item.setLabel_("Stop")
            item.setImage_(NSImage.imageNamed_("NSStopProgressTemplate"))
            item.setTarget_(self)
            item.setAction_(objc.selector(self.stopDownloads_, signature=b"v@:@"))

        return item

    def toolbarAllowedItemIdentifiers_(self, toolbar):
        return ["refresh", "download", "stop", "settings", "NSToolbarFlexibleSpaceItem"]

    def toolbarDefaultItemIdentifiers_(self, toolbar):
        return ["refresh", "download", "stop", "NSToolbarFlexibleSpaceItem", "settings"]

    def _setupLibraryBrowser(self, container):
        # Title
        title = NSTextField.labelWithString_("Library")
        title.setFont_(NSFont.boldSystemFontOfSize_(14))
        title.setFrame_(((10, container.bounds().size.height - 30), (280, 24)))
        container.addSubview_(title)

        # Scroll view with outline view
        scrollView = NSScrollView.alloc().initWithFrame_(
            ((0, 0), (300, container.bounds().size.height - 40))
        )
        scrollView.setHasVerticalScroller_(True)
        scrollView.setBorderType_(1)
        scrollView.setAutoresizingMask_(18)

        self.outlineView = NSOutlineView.alloc().init()
        column = NSTableColumn.alloc().initWithIdentifier_("name")
        column.setTitle_("Bundles & Products")
        column.setWidth_(280)
        self.outlineView.addTableColumn_(column)
        self.outlineView.setOutlineTableColumn_(column)
        self.outlineView.setDataSource_(self.libraryDataSource)
        self.outlineView.setDelegate_(self)
        self.outlineView.setSelectionHighlightStyle_(NSTableViewSelectionHighlightStyleRegular)

        scrollView.setDocumentView_(self.outlineView)
        container.addSubview_(scrollView)

    def _setupDownloadPanel(self, container):
        bounds = container.bounds()

        # Title
        title = NSTextField.labelWithString_("Downloads")
        title.setFont_(NSFont.boldSystemFontOfSize_(14))
        title.setFrame_(((10, bounds.size.height - 30), (200, 24)))
        container.addSubview_(title)

        # Download table
        scrollView = NSScrollView.alloc().initWithFrame_(
            ((0, 50), (bounds.size.width, bounds.size.height - 90))
        )
        scrollView.setHasVerticalScroller_(True)
        scrollView.setBorderType_(1)
        scrollView.setAutoresizingMask_(18)

        self.downloadTable = NSTableView.alloc().init()

        # Add columns
        columns = [
            ("name", "Name", 300),
            ("status", "Status", 100),
            ("progress", "Progress", 80),
            ("size", "Size", 100),
        ]
        for col_id, col_title, width in columns:
            column = NSTableColumn.alloc().initWithIdentifier_(col_id)
            column.setTitle_(col_title)
            column.setWidth_(width)
            self.downloadTable.addTableColumn_(column)

        self.downloadTable.setDataSource_(self.downloadDataSource)
        self.downloadTable.setDelegate_(self)

        scrollView.setDocumentView_(self.downloadTable)
        container.addSubview_(scrollView)

        # Progress bar
        self.progressBar = NSProgressIndicator.alloc().initWithFrame_(
            ((10, 15), (bounds.size.width - 20, 20))
        )
        self.progressBar.setStyle_(NSProgressIndicatorStyleBar)
        self.progressBar.setIndeterminate_(False)
        self.progressBar.setMinValue_(0)
        self.progressBar.setMaxValue_(100)
        container.addSubview_(self.progressBar)

    def _setupMenuBar(self):
        mainMenu = NSMenu.alloc().init()

        # App menu
        appMenuItem = NSMenuItem.alloc().init()
        mainMenu.addItem_(appMenuItem)
        appMenu = NSMenu.alloc().init()

        aboutItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            f"About {APP_NAME}", objc.selector(self.showAbout_, signature=b"v@:@"), ""
        )
        appMenu.addItem_(aboutItem)
        appMenu.addItem_(NSMenuItem.separatorItem())

        settingsItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Settings...", objc.selector(self.showSettings_, signature=b"v@:@"), ","
        )
        appMenu.addItem_(settingsItem)
        appMenu.addItem_(NSMenuItem.separatorItem())

        quitItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            f"Quit {APP_NAME}", objc.selector(self.terminate_, signature=b"v@:@"), "q"
        )
        appMenu.addItem_(quitItem)
        appMenuItem.setSubmenu_(appMenu)

        # File menu
        fileMenuItem = NSMenuItem.alloc().init()
        mainMenu.addItem_(fileMenuItem)
        fileMenu = NSMenu.alloc().initWithTitle_("File")

        refreshItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Refresh Library", objc.selector(self.refreshLibrary_, signature=b"v@:@"), "r"
        )
        fileMenu.addItem_(refreshItem)
        fileMenuItem.setSubmenu_(fileMenu)

        NSApp.setMainMenu_(mainMenu)

    def _setupStatusItem(self):
        """Setup menu bar status item."""
        statusBar = NSStatusBar.systemStatusBar()
        self.statusItem = statusBar.statusItemWithLength_(NSVariableStatusItemLength)
        self.statusItem.setTitle_("HBD")

        statusMenu = NSMenu.alloc().init()

        showItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Show Window", objc.selector(self.showMainWindow_, signature=b"v@:@"), ""
        )
        statusMenu.addItem_(showItem)

        statusMenu.addItem_(NSMenuItem.separatorItem())

        quitItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Quit", objc.selector(self.terminate_, signature=b"v@:@"), ""
        )
        statusMenu.addItem_(quitItem)

        self.statusItem.setMenu_(statusMenu)

    def _loadLibrary(self):
        """Load library data in background thread."""
        def load():
            self.libraryDataSource.loadLibrary_(self.settings)
            # Reload outline view on main thread
            self.outlineView.performSelectorOnMainThread_withObject_waitUntilDone_(
                objc.selector(self.outlineView.reloadData, signature=b"v@:"),
                None,
                False
            )

        thread = threading.Thread(target=load, daemon=True)
        thread.start()

    # Actions
    def refreshLibrary_(self, sender):
        self._loadLibrary()

    def showSettings_(self, sender):
        self.settingsController.showWithSettings_delegate_(self.settings, self)

    def settingsSaved(self):
        self._loadLibrary()

    def downloadSelected_(self, sender):
        """Download selected items or all if nothing selected."""
        selected_row = self.outlineView.selectedRow()
        if selected_row < 0:
            self._downloadAllLibrary()
        else:
            item = self.outlineView.itemAtRow_(selected_row)
            self._downloadItem(item)

    def _downloadItem(self, item):
        """Add item to download queue."""
        if not isinstance(item, dict):
            return

        library_path = self.settings.get("library_path", DEFAULT_LIBRARY_PATH)

        if "url" in item:
            # Single download
            download = DownloadItem(
                name=item["name"],
                bundle_name="",
                url=item["url"],
                local_path=os.path.join(library_path, item["name"]),
            )
            self.downloadDataSource.downloads.append(download)
            self.downloadManager.add_to_queue(download)
        elif "downloads" in item:
            # Product with multiple downloads
            for dl in item["downloads"]:
                download = DownloadItem(
                    name=dl["name"],
                    bundle_name=item["name"],
                    url=dl["url"],
                    local_path=os.path.join(library_path, item["name"], dl["name"]),
                )
                self.downloadDataSource.downloads.append(download)
                self.downloadManager.add_to_queue(download)
        elif "products" in item:
            # Bundle with products
            for product in item["products"]:
                self._downloadItem(product)

        self.downloadTable.reloadData()
        self.downloadManager.start_downloads()

    def _downloadAllLibrary(self):
        """Download entire library."""
        for bundle in self.libraryDataSource.bundles:
            self._downloadItem(bundle)

    def stopDownloads_(self, sender):
        self.downloadManager.stop_downloads()

    def showMainWindow_(self, sender):
        self.window.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)

    def showAbout_(self, sender):
        alert = NSAlert.alloc().init()
        alert.setMessageText_(APP_NAME)
        alert.setInformativeText_(
            "A native macOS application for downloading\nyour Humble Bundle library.\n\n"
            "Version 0.4.3"
        )
        alert.setAlertStyle_(NSAlertStyleInformational)
        alert.runModal()

    def terminate_(self, sender):
        NSApp.terminate_(sender)

    # Download manager delegate methods
    def downloadQueueUpdated(self):
        self.downloadTable.performSelectorOnMainThread_withObject_waitUntilDone_(
            objc.selector(self.downloadTable.reloadData, signature=b"v@:"),
            None,
            False
        )

    def downloadStarted(self, item):
        self.downloadTable.reloadData()

    def downloadProgress(self, item):
        # Update progress bar
        total_progress = 0
        completed = 0
        for dl in self.downloadDataSource.downloads:
            if dl.status == "completed":
                completed += 1
            total_progress += dl.progress

        if self.downloadDataSource.downloads:
            avg_progress = total_progress / len(self.downloadDataSource.downloads)
            self.progressBar.setDoubleValue_(avg_progress)

        self.downloadTable.reloadData()

    def downloadFinished(self, item):
        self.downloadTable.reloadData()

        # Send notification if enabled
        if self.settings.get("notifications", True) and item.status == "completed":
            from .download_library import _send_macos_notification
            _send_macos_notification(
                "Download Complete",
                f"{item.name} has finished downloading.",
                sound=True
            )

    def applicationShouldTerminateAfterLastWindowClosed_(self, app):
        return False  # Keep running in menu bar


def main():
    """Entry point for the GUI application."""
    app = NSApplication.sharedApplication()
    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    app.setActivationPolicy_(0)  # Regular app
    app.activateIgnoringOtherApps_(True)
    app.run()


if __name__ == "__main__":
    main()
