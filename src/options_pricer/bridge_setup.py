"""One-time setup to register the options-pricer:// custom protocol handler.

macOS: Creates a minimal .app bundle in ~/Applications/ with an Info.plist
       declaring the URL scheme. The app's executable runs the bridge.

Windows: Writes registry keys at HKCU\\Software\\Classes\\options-pricer
         pointing to a launcher .bat file.

Usage:
    python -m options_pricer.bridge_setup install [--port 8195]
"""

import argparse
import os
import platform
import stat
import sys
import textwrap


def _get_python() -> str:
    """Return the path to the current Python interpreter."""
    return sys.executable


def install_macos(port: int) -> None:
    """Register options-pricer:// protocol handler on macOS."""
    app_dir = os.path.expanduser("~/Applications/OptionsPricerBridge.app")
    contents = os.path.join(app_dir, "Contents")
    macos_dir = os.path.join(contents, "MacOS")

    os.makedirs(macos_dir, exist_ok=True)

    # Info.plist declaring URL scheme
    plist = textwrap.dedent(f"""\
        <?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
          "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
        <plist version="1.0">
        <dict>
            <key>CFBundleIdentifier</key>
            <string>com.optionspricer.bridge</string>
            <key>CFBundleName</key>
            <string>Options Pricer Bridge</string>
            <key>CFBundleExecutable</key>
            <string>launch</string>
            <key>CFBundleURLTypes</key>
            <array>
                <dict>
                    <key>CFBundleURLName</key>
                    <string>Options Pricer Bridge</string>
                    <key>CFBundleURLSchemes</key>
                    <array>
                        <string>options-pricer</string>
                    </array>
                </dict>
            </array>
        </dict>
        </plist>
    """)

    plist_path = os.path.join(contents, "Info.plist")
    with open(plist_path, "w") as f:
        f.write(plist)

    # Shell script launcher
    python = _get_python()
    launcher = textwrap.dedent(f"""\
        #!/bin/bash
        exec "{python}" -m options_pricer.bloomberg_bridge --port {port}
    """)

    launcher_path = os.path.join(macos_dir, "launch")
    with open(launcher_path, "w") as f:
        f.write(launcher)
    os.chmod(launcher_path, os.stat(launcher_path).st_mode | stat.S_IEXEC)

    # Register with Launch Services
    os.system(f'/System/Library/Frameworks/CoreServices.framework/Frameworks/'
              f'LaunchServices.framework/Support/lsregister -R "{app_dir}"')

    print(f"Installed: {app_dir}")
    print(f"Protocol handler registered: options-pricer://")
    print(f"Bridge will run: {python} -m options_pricer.bloomberg_bridge --port {port}")


def install_windows(port: int) -> None:
    """Register options-pricer:// protocol handler on Windows."""
    import winreg

    python = _get_python()
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Create launcher .bat
    bat_dir = os.path.expanduser("~/.options_pricer")
    os.makedirs(bat_dir, exist_ok=True)
    bat_path = os.path.join(bat_dir, "launch_bridge.bat")

    bat_content = f'@echo off\r\n"{python}" -m options_pricer.bloomberg_bridge --port {port}\r\n'
    with open(bat_path, "w") as f:
        f.write(bat_content)

    # Register URL protocol in HKCU
    key_path = r"Software\Classes\options-pricer"

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "URL:Options Pricer Bridge")
        winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path + r"\shell\open\command") as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, f'"{bat_path}" "%1"')

    print(f"Installed launcher: {bat_path}")
    print(f"Protocol handler registered: options-pricer://")
    print(f"Bridge will run: {python} -m options_pricer.bloomberg_bridge --port {port}")


def main():
    parser = argparse.ArgumentParser(description="Register options-pricer:// protocol handler")
    parser.add_argument("action", choices=["install"], help="Action to perform")
    parser.add_argument("--port", type=int, default=8195,
                        help="Port the bridge will listen on (default: 8195)")
    args = parser.parse_args()

    system = platform.system()
    if system == "Darwin":
        install_macos(args.port)
    elif system == "Windows":
        install_windows(args.port)
    else:
        print(f"Unsupported platform: {system}. Manual setup required.")
        print(f"Run: python -m options_pricer.bloomberg_bridge --port {args.port}")
        sys.exit(1)


if __name__ == "__main__":
    main()
