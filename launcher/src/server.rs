//! Runs the backend and talks to it.

use crate::platform;
use crate::setup::Runtime;
use std::fs;
use std::net::TcpListener;
use std::path::Path;
use std::process::{Child, Command, Stdio};
use std::time::{Duration, Instant};

const PREFERRED_PORT: u16 = 8000;
const STARTUP_TIMEOUT: Duration = Duration::from_secs(120);

/// The preferred port, or a free one when something else already uses it.
pub fn pick_port() -> u16 {
    let wanted = std::env::var("SECURITY_MODELER_PORT")
        .ok()
        .and_then(|port| port.parse().ok())
        .unwrap_or(PREFERRED_PORT);
    if TcpListener::bind(("127.0.0.1", wanted)).is_ok() {
        return wanted;
    }
    TcpListener::bind(("127.0.0.1", 0))
        .and_then(|listener| listener.local_addr())
        .map(|address| address.port())
        .unwrap_or(wanted)
}

pub fn start(home: &Path, runtime: &Runtime, port: u16, token: &str) -> Result<Child, String> {
    let logs = home.join("logs");
    let log = logs.join("backend.log");
    // The previous run's log is kept, for a look after a crash.
    let _ = fs::rename(&log, logs.join("backend.previous.log"));
    let output = fs::File::create(&log).map_err(|error| error.to_string())?;
    let errors = output.try_clone().map_err(|error| error.to_string())?;
    let mut command = Command::new(&runtime.python);
    platform::prepare_child(&mut command);
    command
        // -s leaves out packages from the user's own Python.
        .args(["-s", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", &port.to_string()])
        .current_dir(runtime.app.join("backend"))
        .env("PYTHONPATH", &runtime.packages)
        .env("PYTHONUTF8", "1")
        .env("PYTHONUNBUFFERED", "1")
        .env("SECURITY_MODELER_HOME", home)
        .env("LAUNCHER_TOKEN", token)
        .stdin(Stdio::null())
        .stdout(output)
        .stderr(errors)
        .spawn()
        .map_err(|error| format!("Couldn't start the app: {error}"))
}

pub fn wait_until_ready(url: &str, child: &mut Child) -> Result<(), String> {
    let deadline = Instant::now() + STARTUP_TIMEOUT;
    while Instant::now() < deadline {
        if let Ok(Some(status)) = child.try_wait() {
            return Err(format!("The app stopped while starting ({status})."));
        }
        if agent(Duration::from_secs(2)).get(format!("{url}/api/catalog")).call().is_ok() {
            return Ok(());
        }
        std::thread::sleep(Duration::from_millis(300));
    }
    Err("The app didn't start in time.".into())
}

/// One line about the local LLM, for the tray menu.
pub fn llm_summary(url: &str) -> Option<String> {
    let body = agent(Duration::from_secs(5))
        .get(format!("{url}/api/llm/status"))
        .call()
        .ok()?
        .into_body()
        .read_to_string()
        .ok()?;
    let status: serde_json::Value = serde_json::from_str(&body).ok()?;
    let text = |key: &str| status[key].as_str().unwrap_or_default().to_string();
    if status["busy"].as_bool() == Some(true) {
        let (done, total) = (status["completed"].as_f64().unwrap_or(0.0), status["total"].as_f64().unwrap_or(0.0));
        let message = text("message");
        return Some(if total > 0.0 { format!("{message} ({:.0}%)", done / total * 100.0) } else { message });
    }
    if text("phase") == "error" {
        return Some("LLM needs attention: open the app".into());
    }
    let loaded = status["loaded"].as_array().map_or(0, Vec::len);
    Some(if loaded > 0 { "Model in memory".into() } else { "No model in memory".into() })
}

pub fn unload_model(url: &str) -> bool {
    agent(Duration::from_secs(30)).post(format!("{url}/api/llm/unload")).send_empty().is_ok()
}

/// Asks the backend to stop Ollama. The launcher ends the backend itself afterwards.
pub fn request_quit(url: &str, token: &str) {
    let _ = agent(Duration::from_secs(20))
        .post(format!("{url}/api/launcher/quit"))
        .header("X-Launcher-Token", token)
        .send_empty();
}

fn agent(timeout: Duration) -> ureq::Agent {
    ureq::Agent::config_builder()
        .timeout_global(Some(timeout))
        .build()
        .new_agent()
}
