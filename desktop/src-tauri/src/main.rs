// Fantasy Studio desktop shell (Phase 30) — Tauri 2, mirroring the Aurora
// pattern. Dev: launch.ps1 starts backend (8789) + vite (3000), this window
// loads devUrl. Release: frontendDist is the built SPA and the backend ships
// as a PyInstaller sidecar (build_installer.ps1, later).
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("error while running Fantasy Studio");
}
