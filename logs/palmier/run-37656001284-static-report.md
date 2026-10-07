## Palmier Pro static analysis

### Platform requirements (Package.swift)
// swift-tools-version: 6.2
    platforms: [.macOS(.v26)],
    platforms: [.macOS(.v26)],

### Scale
Swift files: 615, LOC: 119706

### GUI framework coupling
SwiftUI imports: 146
AppKit imports:  83

### CLI surface
Files referencing CommandLine.arguments: 0

### Entry point (Sources/PalmierPro/App/main.swift)
import AppKit

Log.bootstrap()
Telemetry.start()
Analytics.start()
Analytics.capture(.appOpened)
BundledFonts.register()
AccountService.shared.configure()
ModelCatalog.shared.configure()

// Shorten the default tooltip delay from 2s to 0.01s.
UserDefaults.standard.set(10, forKey: "NSInitialToolTipDelay")

let app = NSApplication.shared
AppAppearanceStore.shared.apply()
let delegate = AppDelegate.shared
app.delegate = delegate
app.mainMenu = MainMenuBuilder.buildMenu()
app.run()

### MCP server surface
MCP service file: Sources/PalmierPro/Agent/Tools/ToolExecutor.swift
Sources/PalmierPro/Agent/MCP/MCPService.swift:9:    static let port: UInt16 = 19789

### MCP tool names (first 40)

### Export pipeline (programmatic surface?)
139:    func export(
362:    func exportPalmierProject(
427:    private func exportHDR(
600:    private func exportPresetName(format: ExportFormat, resolution: ExportResolution) -> String {

### License model
# Palmier Pro Binary License

Copyright (C) 2026 Palmier, Inc. All rights reserved.

Palmier Pro binary releases after v0.7.6 are proprietary to Palmier, Inc. No
permission is granted to copy, modify, redistribute, sublicense, reverse
engineer, or create derivative works except under a separate written agreement
with Palmier, Inc.

Third-party components remain subject to their respective licenses.

### macOS version / hardware of this runner
ProductName:		macOS
ProductVersion:		26.6.2
BuildVersion:		25G83
Apple M1 (Virtual)
cores: 3, RAM: 7 GB
Xcode 26.6
Build version 17F113
swift-driver version: 1.148.6 Apple Swift version 6.3.3 (swiftlang-6.3.3.1.3 clang-2100.1.1.101)
Target: arm64-apple-macosx26.0
