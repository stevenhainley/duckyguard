# Homebrew cask template. Publish in a tap (e.g. stevenhainley/homebrew-duckyguard) after a
# release exists; fill in url and sha256 from dist/DuckyGuard-<version>.dmg.sha256.
cask "duckyguard" do
  version "2.0.0"
  sha256 "REPLACE_WITH_SHA256_FROM_RELEASE"

  url "https://github.com/stevenhainley/DuckyGuard/releases/download/v#{version}/DuckyGuard-#{version}.dmg"
  name "DuckyGuard"
  desc "Blocks keystroke-injection devices (Rubber Ducky, Flipper Zero) by typing rhythm"
  homepage "https://github.com/stevenhainley/DuckyGuard"

  depends_on macos: ">= :monterey"

  app "DuckyGuard.app"

  # Unsigned build: Homebrew installs it, but macOS still needs the Gatekeeper override
  # documented in docs/INSTALL.md until the app is notarized.
  postflight do
    system_command "/usr/bin/xattr", args: ["-dr", "com.apple.quarantine", "#{appdir}/DuckyGuard.app"], sudo: false
  end

  uninstall quit: "co.shindustries.duckyguard"

  zap trash: [
    "~/Library/Application Support/DuckyGuard",
    "~/Library/LaunchAgents/co.shindustries.duckyguard.plist",
  ]
end
