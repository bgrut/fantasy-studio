// Fantasy Studio desktop shell — Tauri 2.
//
// Development: launch.ps1 starts the backend (8789) and Vite (3000) and this
// window loads devUrl, as before.
//
// Installed (2026-10-22): the window opens on the shell's own page (shell/).
// On first run it offers a setup, which runs installer/engine-setup.ps1 (shipped
// as a resource) to put a private Python, the engine for this app version, the
// 3D library and the local AI into %LOCALAPPDATA%\FantasyStudio\engine, showing
// its progress. Every later start just launches the engine's backend hidden,
// waits for it to answer, and the page moves to http://127.0.0.1:8789/, where
// the backend serves the studio's own UI (FS_UI_DIR). The backend is stopped
// when the app closes.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::{Emitter, Manager};

#[cfg(windows)]
use std::os::windows::process::CommandExt;
#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

const PORT: u16 = 8789;

struct Engine(Mutex<Option<Child>>);

fn engine_dir() -> PathBuf {
    let base = std::env::var("LOCALAPPDATA").unwrap_or_else(|_| ".".into());
    PathBuf::from(base).join("FantasyStudio").join("engine")
}

fn app_version() -> String {
    env!("CARGO_PKG_VERSION").to_string()
}

#[derive(serde::Serialize)]
struct Status {
    installed: bool,
    version: String,
    installed_version: Option<String>,
    engine_dir: String,
    running: bool,
}

fn port_answers() -> bool {
    std::net::TcpStream::connect_timeout(
        &format!("127.0.0.1:{PORT}").parse().unwrap(),
        Duration::from_millis(400),
    )
    .is_ok()
}

#[tauri::command]
fn engine_status() -> Status {
    let dir = engine_dir();
    let stamp = dir.join("app").join(".version");
    let installed_version = std::fs::read_to_string(&stamp).ok().map(|s| s.trim().to_string());
    let ready = dir.join("installed.json").exists()
        && dir.join("app").join("backend").join("venv").join("Scripts").join("python.exe").exists();
    Status {
        installed: ready && installed_version.as_deref() == Some(app_version().as_str()),
        version: app_version(),
        installed_version,
        engine_dir: dir.display().to_string(),
        running: port_answers(),
    }
}

/// Run the engine setup, streaming its "@@ pct message" lines to the window as
/// "setup-progress" events. Returns when it ends; Err carries the reason.
#[tauri::command]
async fn run_setup(app: tauri::AppHandle, mode: String, skip_ollama: bool) -> Result<(), String> {
    let script = app
        .path()
        .resolve("installer/engine-setup.ps1", tauri::path::BaseDirectory::Resource)
        .map_err(|e| e.to_string())?;
    let dir = engine_dir();
    let mut cmd = Command::new("powershell.exe");
    cmd.args(["-NoProfile", "-ExecutionPolicy", "Bypass", "-File"])
        .arg(&script)
        .arg("-EngineDir")
        .arg(&dir)
        .arg("-Version")
        .arg(app_version())
        .arg("-Mode")
        .arg(if mode == "full" { "full" } else { "game" });
    if skip_ollama {
        cmd.arg("-SkipOllama");
    }
    if let Ok(zip) = std::env::var("FS_ENGINE_ZIP") {
        cmd.arg("-EngineZip").arg(zip);
    }
    cmd.stdout(Stdio::piped()).stderr(Stdio::null());
    #[cfg(windows)]
    cmd.creation_flags(CREATE_NO_WINDOW);
    let mut child = cmd.spawn().map_err(|e| format!("could not start setup: {e}"))?;
    let out = child.stdout.take().ok_or("no setup output")?;
    let app2 = app.clone();
    let result = tauri::async_runtime::spawn_blocking(move || {
        let mut err: Option<String> = None;
        let mut done = false;
        for line in BufReader::new(out).lines().map_while(Result::ok) {
            let l = line.trim().to_string();
            if l == "@@DONE" {
                done = true;
            } else if let Some(m) = l.strip_prefix("@@ERROR ") {
                err = Some(m.to_string());
            }
            if l.starts_with("@@") {
                let _ = app2.emit("setup-progress", l);
            }
        }
        let _ = child.wait();
        match (done, err) {
            (_, Some(e)) => Err(e),
            (true, None) => Ok(()),
            (false, None) => Err("setup stopped before it finished".into()),
        }
    })
    .await
    .map_err(|e| e.to_string())?;
    result
}

/// Start the engine's backend (hidden) unless something already answers on the
/// port, and wait until it does. Returns the URL to open.
#[tauri::command]
async fn start_engine(state: tauri::State<'_, Engine>) -> Result<String, String> {
    let url = format!("http://127.0.0.1:{PORT}/");
    if port_answers() {
        return Ok(url);
    }
    let dir = engine_dir().join("app");
    let backend = dir.join("backend");
    let py = backend.join("venv").join("Scripts").join("python.exe");
    if !py.exists() {
        return Err("the engine is not installed".into());
    }
    let mut cmd = Command::new(&py);
    cmd.args(["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", &PORT.to_string()])
        .current_dir(&backend)
        .env("PYTHONUTF8", "1")
        .env("FS_UI_DIR", dir.join("frontend").join("dist"))
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    #[cfg(windows)]
    cmd.creation_flags(CREATE_NO_WINDOW);
    let child = cmd.spawn().map_err(|e| format!("could not start the engine: {e}"))?;
    *state.0.lock().unwrap() = Some(child);
    let t0 = Instant::now();
    while t0.elapsed() < Duration::from_secs(90) {
        if port_answers() {
            return Ok(url);
        }
        tokio_sleep(Duration::from_millis(500)).await;
    }
    Err("the engine did not start within 90 seconds".into())
}

async fn tokio_sleep(d: Duration) {
    let _ = tauri::async_runtime::spawn_blocking(move || std::thread::sleep(d)).await;
}

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
    let app = tauri::Builder::default()
        .manage(Engine(Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![engine_status, run_setup, start_engine])
        .build(tauri::generate_context!())
        .expect("error while building Fantasy Studio");
    app.run(|handle, event| {
        if let tauri::RunEvent::Exit = event {
            if let Some(mut c) = handle.state::<Engine>().0.lock().unwrap().take() {
                let _ = c.kill();
            }
        }
    });
}
