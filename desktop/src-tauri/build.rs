fn main() {
    // Single source of mark geometry: the extension's geometry.js (golden parity with server/app/resolver.py).
    println!("cargo:rerun-if-changed=../../extension/geometry.js");
    std::fs::copy("../../extension/geometry.js", "../ui/geometry.js").expect("copy extension/geometry.js");
    tauri_build::build()
}
