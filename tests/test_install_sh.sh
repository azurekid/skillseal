#!/bin/sh
set -eu

repo=$(CDPATH='' cd -- "$(dirname "$0")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
trap 'exit 1' HUP INT TERM
export FIXTURE="$tmp/assets"
mkdir -p "$FIXTURE/skillseal" "$tmp/mocks"
cat > "$FIXTURE/skillseal/skillseal" <<'EOF'
#!/bin/sh
echo "skillseal installer-test"
EOF
chmod +x "$FIXTURE/skillseal/skillseal"
for asset in skillseal-macos-arm64.tar.gz skillseal-linux-x64.tar.gz; do
    tar -czf "$FIXTURE/$asset" -C "$FIXTURE" skillseal
    if command -v sha256sum >/dev/null 2>&1; then
        hash=$(sha256sum "$FIXTURE/$asset" | awk '{print $1}')
    else
        hash=$(shasum -a 256 "$FIXTURE/$asset" | awk '{print $1}')
    fi
    printf '%s  %s\n' "$hash" "$asset" >> "$FIXTURE/SHA256SUMS.txt"
done
cat > "$tmp/mocks/curl" <<'EOF'
#!/bin/sh
set -eu
while [ "$#" -gt 0 ]; do
    case "$1" in
        https:*) url=$1; shift ;;
        -o) output=$2; shift 2 ;;
        --retry) shift 2 ;;
        *) shift ;;
    esac
done
if [ "${DOWNLOAD_FAIL:-0}" = 1 ]; then exit 22; fi
cp "$FIXTURE/${url##*/}" "$output"
EOF
cat > "$tmp/mocks/uname" <<'EOF'
#!/bin/sh
case "$1" in
    -s) echo "$TEST_OS" ;;
    -m) echo "$TEST_ARCH" ;;
esac
EOF
chmod +x "$tmp/mocks/curl" "$tmp/mocks/uname"
export PATH="$tmp/mocks:$PATH"
export HOME="$tmp/user home" SHELL=/bin/zsh TEST_OS=Darwin TEST_ARCH=arm64
mkdir -p "$HOME"

# Use piped stdin, as in the one-line README command.
cat "$repo/install.sh" | sh
test "$("$HOME/.local/bin/skillseal" --version)" = "skillseal installer-test"
test "$(grep -Fc 'export PATH=' "$HOME/.zshrc")" = 1
# The account default is zsh, but VS Code may run bash instead.
test "$(HOME="$HOME" bash -ic 'command -v skillseal' 2>/dev/null)" = "$HOME/.local/bin/skillseal"
test "$(HOME="$HOME" bash -lc 'command -v skillseal')" = "$HOME/.local/bin/skillseal"
cat "$repo/install.sh" | sh
test "$(grep -Fc 'export PATH=' "$HOME/.zshrc")" = 1
test "$(grep -Fc 'export PATH=' "$HOME/.bashrc")" = 1
test "$(grep -Fc 'export PATH=' "$HOME/.bash_profile")" = 1
test "$(find "$HOME/.local/share" -name '.skillseal-install.*' | wc -l | tr -d ' ')" = 0

# Failed updates must preserve the existing install.
if DOWNLOAD_FAIL=1 sh "$repo/install.sh"; then echo "Download failure accepted"; exit 1; fi
cp "$FIXTURE/SHA256SUMS.txt" "$tmp/checksums"
printf '%064d  skillseal-macos-arm64.tar.gz\n' 0 > "$FIXTURE/SHA256SUMS.txt"
if sh "$repo/install.sh"; then echo "Checksum failure accepted"; exit 1; fi
test "$("$HOME/.local/bin/skillseal" --version)" = "skillseal installer-test"
cp "$tmp/checksums" "$FIXTURE/SHA256SUMS.txt"
printf 'no checksum\n' > "$FIXTURE/SHA256SUMS.txt"
if sh "$repo/install.sh"; then echo "Missing checksum accepted"; exit 1; fi
cp "$tmp/checksums" "$FIXTURE/SHA256SUMS.txt"

# Linux bash login and interactive shells both get PATH, without duplicates.
export HOME="$tmp/linux" SHELL=/bin/bash TEST_OS=Linux TEST_ARCH=x86_64
mkdir -p "$HOME"
printf '# existing profile\n' > "$HOME/.profile"
sh "$repo/install.sh" v0.2.0
sh "$repo/install.sh"
test "$(grep -Fc 'export PATH=' "$HOME/.bashrc")" = 1
test "$(grep -Fc 'export PATH=' "$HOME/.profile")" = 1
grep -q '# existing profile' "$HOME/.profile"

export HOME="$tmp/fish" SHELL=/usr/bin/fish XDG_CONFIG_HOME="$tmp/fish config"
sh "$repo/install.sh"
# shellcheck disable=SC2016
grep -Fq 'fish_add_path "$HOME/.local/bin"' "$XDG_CONFIG_HOME/fish/config.fish"

export HOME="$tmp/other-shell" SHELL=/bin/sh
sh "$repo/install.sh"
test -f "$HOME/.profile"

export HOME="$tmp/unsupported" TEST_ARCH=aarch64
if sh "$repo/install.sh"; then echo "Unsupported platform accepted"; exit 1; fi
test ! -e "$HOME"

export HOME="$tmp/collision" TEST_ARCH=x86_64
mkdir -p "$HOME/.local/bin"
printf 'do not overwrite\n' > "$HOME/.local/bin/skillseal"
if sh "$repo/install.sh"; then echo "Existing program overwritten"; exit 1; fi
grep -q 'do not overwrite' "$HOME/.local/bin/skillseal"
echo "install.sh tests passed"
