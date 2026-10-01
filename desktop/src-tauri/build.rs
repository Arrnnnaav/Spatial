fn main() {
    // Single source of mark geometry: the extension's geometry.js (golden parity with server/app/resolver.py).
    println!("cargo:rerun-if-changed=../../extension/geometry.js");
    std::fs::copy("../../extension/geometry.js", "../ui/geometry.js").expect("copy extension/geometry.js");
    // Every app command needs an explicit per-window permission (see capabilities/*.json). `foreground_target` is
    // only called from Rust, so no window is granted it.
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(tauri_build::AppManifest::new().commands(&[
        "own_pid", "desktop_token", "pairing_token", "startup_notice", "foreground_target", "paste_dictation", "set_dictation_active",
    ])))
    .expect("failed to run tauri-build");
}
