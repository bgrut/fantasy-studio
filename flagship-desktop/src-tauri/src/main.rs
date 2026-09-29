// Crystal Works as a desktop game (2026-09-29): the flagship demo in a native
// window, for a Steam depot. The game is the packed flagship folder, embedded
// in the executable (tauri.conf.json frontendDist), so the build is one .exe
// and nothing else; saves live in the WebView2 profile under the identifier.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

// STEAMWORKS (the "steam" feature, 2026-09-29). Launched by Steam, the client
// knows its app from Steam itself; run by hand, it reads steam_appid.txt
// beside the executable. No Steam running, or no app to be, is not an error
// for the game: it plays the same and its achievements wait in the save until
// a launch under Steam hands them over.
#[cfg(feature = "steam")]
mod steam {
    use std::sync::OnceLock;

    static CLIENT: OnceLock<Option<steamworks::Client>> = OnceLock::new();

    pub fn start() {
        // run by hand, the app id is read from beside the executable, not from
        // wherever the shortcut happened to start it
        if let Ok(exe) = std::env::current_exe() {
            if let Some(dir) = exe.parent() {
                let _ = std::env::set_current_dir(dir);
            }
        }
        let client = steamworks::Client::init().ok();
        if let Some(c) = client.clone() {
            // Steam answers through callbacks; they are pumped off the UI thread
            std::thread::spawn(move || loop {
                c.run_callbacks();
                std::thread::sleep(std::time::Duration::from_millis(100));
            });
        }
        let _ = CLIENT.set(client);
    }

    pub fn client() -> Option<&'static steamworks::Client> {
        CLIENT.get().and_then(|c| c.as_ref())
    }
}

// ACHIEVEMENTS: the game calls this with an API name the moment one is earned,
// and again at launch for everything already earned, so a run played while
// Steam was closed still counts.
#[tauri::command]
fn steam_achieve(id: String) -> Result<(), String> {
    #[cfg(feature = "steam")]
    {
        let c = steam::client().ok_or_else(|| "Steam is not running".to_string())?;
        let stats = c.user_stats();
        stats
            .achievement(&id)
            .set()
            .map_err(|_| format!("this app has no achievement named {id}"))?;
        stats.store_stats().map_err(|_| "Steam did not store the stats".to_string())?;
        Ok(())
    }
    #[cfg(not(feature = "steam"))]
    {
        let _ = id;
        Err("this build has no Steam client".into())
    }
}

#[derive(serde::Serialize)]
struct SteamInfo {
    built_in: bool,
    running: bool,
    app_id: u32,
    player: String,
    overlay: bool,
}

// What the pause menu shows: whether Steam is here, as whom, and whether its
// overlay is available to open.
#[tauri::command]
fn steam_state() -> SteamInfo {
    #[cfg(feature = "steam")]
    {
        if let Some(c) = steam::client() {
            return SteamInfo {
                built_in: true,
                running: true,
                app_id: c.utils().app_id().0,
                player: c.friends().name(),
                overlay: c.utils().is_overlay_enabled(),
            };
        }
        return SteamInfo { built_in: true, running: false, app_id: 0, player: String::new(), overlay: false };
    }
    #[cfg(not(feature = "steam"))]
    SteamInfo { built_in: false, running: false, app_id: 0, player: String::new(), overlay: false }
}

// Opens the Steam overlay's achievements page from the pause menu.
#[tauri::command]
fn steam_overlay(dialog: String) -> bool {
    #[cfg(feature = "steam")]
    {
        if let Some(c) = steam::client() {
            c.friends().activate_game_overlay(&dialog);
            return true;
        }
        false
    }
    #[cfg(not(feature = "steam"))]
    {
        let _ = dialog;
        false
    }
}

fn main() {
    // The same WebGL resilience as the studio shell: WebView2 keeps a
    // persistent gpu-crash blocklist, and after a few lost contexts it refuses
    // WebGL for good. A game that stops drawing after a driver hiccup is worse
    // than one that falls back to software for a frame.
    std::env::set_var(
        "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS",
        "--disable-gpu-process-crash-limit --ignore-gpu-blocklist --enable-unsafe-swiftshader --autoplay-policy=no-user-gesture-required",
    );
    #[cfg(feature = "steam")]
    steam::start();
    // CrystalWorks.exe --steam-selftest: is Steam here, for which app, with an
    // overlay, and does a stats call reach it. It asks for an achievement no
    // app has, so the answer is a refusal and nothing on the account changes.
    // Written beside the executable (a windowed build has no console).
    if std::env::args().any(|a| a == "--steam-selftest") {
        let s = steam_state();
        let probe = steam_achieve("CW_SELFTEST_NO_SUCH_ACHIEVEMENT".into());
        let report = serde_json::json!({
            "built_in": s.built_in, "running": s.running, "app_id": s.app_id,
            "player_known": !s.player.is_empty(), "overlay": s.overlay,
            "stats_call": match probe { Ok(()) => "accepted".to_string(), Err(e) => e },
        });
        if let Ok(exe) = std::env::current_exe() {
            if let Some(dir) = exe.parent() {
                let _ = std::fs::write(dir.join("steam_selftest.json"), report.to_string());
            }
        }
        return;
    }
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![steam_achieve, steam_state, steam_overlay])
        .run(tauri::generate_context!())
        .expect("error while running Crystal Works");
}
