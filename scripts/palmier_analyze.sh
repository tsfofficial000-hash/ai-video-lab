#!/usr/bin/env bash
# =============================================================================
# TEST E (part 1) — Palmier Pro static forensic analysis (macOS runner).
# Documents: project structure, entry point, CLI surface, MCP server,
# license model, platform requirements. ~2 minutes, no build.
# =============================================================================
set -uo pipefail
log(){ echo "[PALMIER] $*"; }
metric(){ echo "[METRIC] palmier_$1=$2" | tee -a palmier_metrics.txt; }

cd "$RUNNER_TEMP" 2>/dev/null || cd /tmp
rm -rf palmier-pro
log "cloning palmier-io/palmier-pro..."
git clone --depth 1 --quiet https://github.com/palmier-io/palmier-pro.git 2>&1 \
  || { metric repo_clone failed; echo "REPO CLONE FAILED"; exit 0; }
metric repo_clone success
cd palmier-pro || exit 0

{
echo "## Palmier Pro static analysis"
echo ""
echo "### Platform requirements (Package.swift)"
grep -E "swift-tools-version|platforms:" Package.swift | head -4
grep -E "\.macOS\(" Package.swift | head -2
echo ""
echo "### Scale"
SWIFTS=$(git ls-files '*.swift' | wc -l | tr -d ' ')
LOCS=$(git ls-files '*.swift' | xargs wc -l 2>/dev/null | tail -1 | awk '{print $1}')
echo "Swift files: $SWIFTS, LOC: $LOCS"
echo ""
echo "### GUI framework coupling"
echo "SwiftUI imports: $(grep -rl 'import SwiftUI' Sources/ | wc -l | tr -d ' ')"
echo "AppKit imports:  $(grep -rl 'import AppKit' Sources/ | wc -l | tr -d ' ')"
echo ""
echo "### CLI surface"
echo "Files referencing CommandLine.arguments: $(grep -rl 'CommandLine.arguments' Sources/ | wc -l | tr -d ' ')"
echo ""
echo "### Entry point (Sources/PalmierPro/App/main.swift)"
\cat Sources/PalmierPro/App/main.swift 2>/dev/null || echo "(not found)"
echo ""
echo "### MCP server surface"
MCPFILE=$(grep -rln "ToolDefinitions.mcpServer" Sources/ | head -1)
echo "MCP service file: $MCPFILE"
grep -rn "127.0.0.1:19789\|19789" Sources/ --include="*.swift" | head -5
echo ""
echo "### MCP tool names (first 40)"
grep -rhoE 'name: "[a-z_.]+"' "$MCPFILE" 2>/dev/null | head -40
TOOLDEFS=$(grep -rln "mcpServer: \[Tool\|mcpServer=\|static let mcpServer" Sources/ | head -3)
for f in $TOOLDEFS; do echo "--- $f ---"; grep -oE '"[a-z_]+(\.[a-z_]+)?"' "$f" | sort -u | head -40; done
echo ""
echo "### Export pipeline (programmatic surface?)"
grep -n "func export" Sources/PalmierPro/Export/ExportService.swift | head -5
echo ""
echo "### License model"
head -12 BINARY_LICENSE.md 2>/dev/null
echo ""
echo "### macOS version / hardware of this runner"
sw_vers
sysctl -n machdep.cpu.brand_string
echo "cores: $(sysctl -n hw.ncpu), RAM: $(( $(sysctl -n hw.memsize) / 1073741824 )) GB"
xcodebuild -version
swift --version 2>&1 | head -2
} > palmier_static_report.md 2>&1 || true

cat palmier_static_report.md
SWIFTFILES=$(git ls-files '*.swift' | wc -l | tr -d ' ')
metric swift_files "$SWIFTFILES"
CLIREFS=$(grep -rl 'CommandLine.arguments' Sources/ | wc -l | tr -d ' ')
metric cli_argument_references "$CLIREFS"
metric requires_macos "26_tahoe_apple_silicon"
echo "[PALMIER-STATIC-DONE]"
