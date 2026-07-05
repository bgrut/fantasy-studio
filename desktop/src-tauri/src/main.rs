// Fantasy Studio desktop shell (Phase 30) — Tauri 2, mirroring the Aurora
// pattern. Dev: launch.ps1 starts backend (8789) + vite (3000), this window
// loads devUrl. Release: frontendDist is the built SPA and the backend ships
// as a PyInstaller sidecar (build_installer.ps1, later).
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    // WebGL resilience on iGPU-only machines (2026-07-05): WebView2 keeps a
    // PERSISTENT gpu-crash blocklist in its profile — after a few context
    // losses (e.g. playing a game while Blender renders on the same iGPU)
    // it refuses ALL new WebGL contexts, and the block survives app
    // restarts ("Error creating WebGL context" forever). These Chromium
    // flags disable the crash-count kill switch and allow a software
    // fallback so game previews always come back.
    std::env::set_var(
        "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS",
        "--disable-gpu-process-crash-limit --ignore-gpu-blocklist --enable-unsafe-swiftshader",
    );
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("error while running Fantasy Studio");
}
