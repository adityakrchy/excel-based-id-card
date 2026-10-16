$ErrorActionPreference = "Stop"

$toolchain = "stable-x86_64-pc-windows-msvc"
rustup toolchain install $toolchain
rustup target add x86_64-pc-windows-msvc --toolchain $toolchain
rustup run $toolchain cargo fmt --all -- --check
rustup run $toolchain cargo test --all-targets
rustup run $toolchain cargo build --release --target x86_64-pc-windows-msvc

$installer = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if ($null -ne $installer) {
    & $installer.Source "packaging\rust_installer.iss"
} else {
    Write-Warning "ISCC.exe was not found; executable build completed but installer was skipped."
}
