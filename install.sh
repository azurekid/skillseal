#!/bin/sh
# Per-user standalone install for macOS and Linux. No Python or sudo needed.
set -eu

main() {
    version=${1:-latest}
    case "$version" in
        latest|v[0-9]*) ;;
        *) echo "Use a release tag (for example v0.2.0), or latest." >&2; exit 1 ;;
    esac
    case "$(uname -s)/$(uname -m)" in
        Darwin/arm64) asset=skillseal-macos-arm64.tar.gz ;;
        Linux/x86_64) asset=skillseal-linux-x64.tar.gz ;;
        *) echo "Unsupported platform. Use the Python install option in the README." >&2; exit 1 ;;
    esac
    case "${HOME:-}" in
        /*) ;;
        *) echo "HOME must be an absolute path." >&2; exit 1 ;;
    esac
    for tool in curl tar awk; do
        command -v "$tool" >/dev/null 2>&1 || {
            echo "Required command not found: $tool" >&2; exit 1;
        }
    done
    if command -v sha256sum >/dev/null 2>&1; then
        hash_tool=sha256sum
    elif command -v shasum >/dev/null 2>&1; then
        hash_tool=shasum
    else
        echo "Install sha256sum or shasum to verify the download." >&2; exit 1
    fi

    dest="$HOME/.local/share/skillseal"
    bin="$HOME/.local/bin"
    if [ -L "$dest" ] || { [ -e "$dest" ] && [ ! -x "$dest/skillseal" ]; }; then
        echo "Refusing to replace unexpected install path: $dest" >&2; exit 1
    fi
    if [ -e "$bin/skillseal" ] || [ -L "$bin/skillseal" ]; then
        if [ ! -L "$bin/skillseal" ] || [ "$(readlink "$bin/skillseal")" != "$dest/skillseal" ]; then
            echo "Another program already exists at $bin/skillseal. Move it first." >&2; exit 1
        fi
    fi

    mkdir -p "$HOME/.local/share" "$bin"
    tmp=$(mktemp -d "$HOME/.local/share/.skillseal-install.XXXXXXXX")
    trap 'rm -rf "$tmp"' EXIT
    trap 'exit 1' HUP INT TERM
    base=https://github.com/azurekid/skillseal/releases
    if [ "$version" = latest ]; then
        base="$base/latest/download"
    else
        base="$base/download/$version"
    fi
    echo "Downloading $asset ($version)..."
    curl -fsSL --retry 3 "$base/$asset" -o "$tmp/$asset"
    curl -fsSL --retry 3 "$base/SHA256SUMS.txt" -o "$tmp/SHA256SUMS.txt"
    expected=$(awk -v asset="$asset" '$2 == asset { print $1 }' "$tmp/SHA256SUMS.txt")
    if [ "${#expected}" -ne 64 ]; then
        echo "Missing or invalid checksum for $asset." >&2; exit 1
    fi
    case "$expected" in
        *[!0-9a-f]*) echo "Invalid SHA256 checksum." >&2; exit 1 ;;
    esac
    if [ "$hash_tool" = sha256sum ]; then
        actual=$(sha256sum "$tmp/$asset" | awk '{print $1}')
    else
        actual=$(shasum -a 256 "$tmp/$asset" | awk '{print $1}')
    fi
    if [ "$actual" != "$expected" ]; then
        echo "Checksum mismatch for $asset. Nothing was installed." >&2; exit 1
    fi
    echo "Checksum OK."
    tar -xzf "$tmp/$asset" -C "$tmp"
    if [ ! -x "$tmp/skillseal/skillseal" ]; then
        echo "Archive does not contain the skillseal executable." >&2; exit 1
    fi
    if ! "$tmp/skillseal/skillseal" --version; then
        echo "The downloaded binary cannot run. Linux needs glibc 2.35+. Your existing install was not changed." >&2
        exit 1
    fi
    if [ -e "$dest" ]; then
        mv "$dest" "$tmp/previous"
    fi
    if ! mv "$tmp/skillseal" "$dest"; then
        if [ -d "$tmp/previous" ]; then mv "$tmp/previous" "$dest"; fi
        echo "Could not install skillseal." >&2; exit 1
    fi
    ln -sf "$dest/skillseal" "$bin/skillseal"

    # Keep variables literal so the user's shell expands them at startup.
    # shellcheck disable=SC2016
    path_line='export PATH="$HOME/.local/bin:$PATH"'
    shell=${SHELL:-}
    case "${shell##*/}" in
        zsh) profiles="${ZDOTDIR:-$HOME}/.zshrc" ;;
        bash)
            profiles="$HOME/.bashrc"
            if [ -f "$HOME/.bash_profile" ]; then login="$HOME/.bash_profile"
            elif [ -f "$HOME/.bash_login" ]; then login="$HOME/.bash_login"
            elif [ -f "$HOME/.profile" ]; then login="$HOME/.profile"
            else login="$HOME/.bash_profile"; fi
            ;;
        fish)
            profiles="${XDG_CONFIG_HOME:-$HOME/.config}/fish/config.fish"
            # shellcheck disable=SC2016
            path_line='fish_add_path "$HOME/.local/bin"'
            ;;
        *) profiles="$HOME/.profile" ;;
    esac
    add_path() {
        mkdir -p "$(dirname "$1")"
        if ! grep -Fqx "$path_line" "$1" 2>/dev/null; then
            printf '\n# skillseal\n%s\n' "$path_line" >> "$1"
        fi
    }
    add_path "$profiles"
    if [ "${login:-}" ]; then add_path "$login"; fi
    echo "Installed: $dest/skillseal"
    echo "PATH setup saved to $profiles${login:+ and $login}."
    echo "Open a new terminal, then run: skillseal --version"
    echo "To update later, close your AI agents and run the same install command again."
}

main "$@"
