# Homebrew cask for DuckyGuard 2.2.0. Publish in a tap (e.g. stevenhainley/homebrew-duckyguard)
# alongside the GitHub release: brew tap stevenhainley/duckyguard && brew install --cask duckyguard
cask "duckyguard" do
  version "2.2.0"
  sha256 "eecdc382443261e197033eb3d0129f5d3f8698adb3e1d357a0e1a64cf339ff51"

  url "https://github.com/stevenhainley/duckyguard/releases/download/v#{version}/DuckyGuard-#{version}.dmg"
  name "DuckyGuard"
  desc "Blocks keystroke-injection devices (Rubber Ducky, Flipper Zero) by typing rhythm"
  homepage "https://shindustries.co/duckyguard/"

  depends_on macos: ">= :tahoe"
  depends_on arch: :arm64

  app "DuckyGuard.app"

  # Ad-hoc signed build: removes the browser/Homebrew quarantine flag. macOS users
  # still grant Input Monitoring and Accessibility in Privacy & Security (docs/INSTALL.md).
  postflight do
    system_command "/usr/bin/xattr", args: ["-dr", "com.apple.quarantine", "#{appdir}/DuckyGuard.app"], sudo: false
  end

  uninstall quit: "co.shindustries.duckyguard"

  zap trash: [
    "~/Library/Application Support/DuckyGuard",
    "~/Library/LaunchAgents/co.shindustries.duckyguard.plist",
  ]
end
