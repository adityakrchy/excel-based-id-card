#[cfg(windows)]
fn main() {
    println!("cargo:rerun-if-changed=build.rs");

    // The version resource is only needed by the Windows binary.  No icon is
    // embedded, so the build remains usable with the repository's existing
    // assets and the executable keeps the normal Windows default icon.
    if std::env::var_os("CARGO_CFG_WINDOWS").is_some() {
        let mut resource = winres::WindowsResource::new();
        resource.set("FileDescription", "Excel ID Card Generator");
        resource.set("ProductName", "Excel ID Card Generator");
        resource.set("ProductVersion", env!("CARGO_PKG_VERSION"));
        resource.set("FileVersion", env!("CARGO_PKG_VERSION"));
        resource.set("OriginalFilename", "excel-id-card-rust.exe");
        resource.set("LegalCopyright", "CardForge");
        resource
            .compile()
            .expect("failed to compile Windows version resource");
    }
}

#[cfg(not(windows))]
fn main() {
    println!("cargo:rerun-if-changed=build.rs");
}
