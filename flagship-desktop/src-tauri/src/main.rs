// Crystal Works as a desktop game (2026-09-29): the flagship demo in a native
// window, for a Steam depot. The game is the packed flagship folder, embedded
// in the executable (tauri.conf.json frontendDist), so the build is one .exe
// and nothing else; saves live in the WebView2 profile under the identifier.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    // The same WebGL resilience as the studio shell: WebView2 keeps a
    // persistent gpu-crash blocklist, and after a few lost contexts it refuses
    // WebGL for good. A game that stops drawing after a driver hiccup is worse
    // than one that falls back to software for a frame.
    std::env::set_var(
        "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS",
        "--disable-gpu-process-crash-limit --ignore-gpu-blocklist --enable-unsafe-swiftshader --autoplay-policy=no-user-gesture-required",
    );
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("error while running Crystal Works");
}
