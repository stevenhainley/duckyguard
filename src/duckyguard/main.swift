import Cocoa
import WebKit

class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate {
    var window: NSWindow!
    var webView: WKWebView!
    var serverProcess: Process?
    var statusItem: NSStatusItem?

    func applicationDidFinishLaunching(_ notification: Notification) {
        // Setup macOS Status Bar Item (Top Menu Bar Icon)
        setupStatusItem()

        // Start backend Python API server if not already running
        startBackendServerIfNeeded()

        // Configure WKWebView
        let config = WKWebViewConfiguration()
        config.preferences.setValue(true, forKey: "developerExtrasEnabled")

        let screenRect = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1200, height: 800)
        let width: CGFloat = 1040
        let height: CGFloat = 720
        let x = (screenRect.width - width) / 2 + screenRect.minX
        let y = (screenRect.height - height) / 2 + screenRect.minY

        let windowRect = NSRect(x: x, y: y, width: width, height: height)

        window = NSWindow(
            contentRect: windowRect,
            styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )

        window.title = "DuckyGuard"
        window.titlebarAppearsTransparent = true
        window.titleVisibility = .hidden
        window.minSize = NSSize(width: 860, height: 560)
        window.isReleasedWhenClosed = false
        window.delegate = self
        window.backgroundColor = NSColor(red: 0.992, green: 0.984, blue: 0.969, alpha: 1.0) // Warm Ivory #FDFBF7

        webView = WKWebView(frame: window.contentView!.bounds, configuration: config)
        webView.autoresizingMask = [.width, .height]
        webView.setValue(false, forKey: "drawsBackground") // Let window warm color show
        window.contentView?.addSubview(webView)

        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)

        // Load UI with retry
        loadDashboard(retries: 5)
    }

    func setupStatusItem() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        if let button = statusItem?.button {
            let iconPath = "/Users/stevenhainley/DuckyGuard/assets/menubar_icon.png"
            if let img = NSImage(contentsOfFile: iconPath) {
                img.size = NSSize(width: 18, height: 18)
                img.isTemplate = false
                button.image = img
            } else {
                button.title = "Ducky"
            }
            button.target = self
            button.action = #selector(statusBarClicked)
            button.toolTip = "DuckyGuard — Physical HID Injection Defense"
        }
    }

    @objc func statusBarClicked() {
        if window.isVisible {
            window.orderFrontRegardless()
            NSApp.activate(ignoringOtherApps: true)
        } else {
            window.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
        }
    }

    func loadDashboard(retries: Int) {
        guard let url = URL(string: "http://127.0.0.1:4848") else { return }
        
        // Check if server is answering
        let task = URLSession.shared.dataTask(with: url) { [weak self] (_, response, error) in
            DispatchQueue.main.async {
                if error == nil, let http = response as? HTTPURLResponse, http.statusCode == 200 {
                    self?.webView.load(URLRequest(url: url))
                } else if retries > 0 {
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) {
                        self?.loadDashboard(retries: retries - 1)
                    }
                } else {
                    self?.webView.load(URLRequest(url: url))
                }
            }
        }
        task.resume()
    }

    func startBackendServerIfNeeded() {
        // Ping port 4848
        guard let checkURL = URL(string: "http://127.0.0.1:4848/api/status") else { return }
        var isUp = false
        let sem = DispatchSemaphore(value: 0)
        let pingTask = URLSession.shared.dataTask(with: checkURL) { (_, resp, err) in
            if err == nil, let http = resp as? HTTPURLResponse, http.statusCode == 200 {
                isUp = true
            }
            sem.signal()
        }
        pingTask.resume()
        _ = sem.wait(timeout: .now() + 0.3)

        if isUp { return }

        // Spawn background Python server
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/arch")
        p.arguments = ["-arm64", "/usr/bin/python3", "-m", "duckyguard.server"]
        
        var env = ProcessInfo.processInfo.environment
        env["PYTHONPATH"] = "/Users/stevenhainley/DuckyGuard/src"
        p.environment = env
        p.currentDirectoryURL = URL(fileURLWithPath: "/Users/stevenhainley/DuckyGuard")

        try? p.run()
        self.serverProcess = p
    }

    func applicationWillTerminate(_ notification: Notification) {
        serverProcess?.terminate()
    }

    func windowShouldClose(_ sender: NSWindow) -> Bool {
        NSApp.terminate(nil)
        return true
    }
}

// Entrypoint
let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
