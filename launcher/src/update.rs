//! Updates from this repository's GitHub releases, the same way in all of Akulav's apps.
//!
//! The launcher checks a minute after it starts and every 6 hours, or at once when asked: the tray's "Check for
//! updates", or the app's page writing `update.request` into the home folder. What it found goes to `update.json`
//! there, which the app's page shows:
//!
//!   {"current", "latest", "newer", "notes", "page", "checked", "error", "state", "asset", "managed"}
//!
//! Installing (the tray's "Update to …", or the page writing `update.apply`) downloads this system's release file
//! and checks it against GitHub's SHA-256 digest of it before anything changes. A release has three files, one per
//! system, and each one both installs and updates:
//!
//! - Windows: `SecurityModeler-Setup.exe` (Inno Setup, launcher/installer/security-modeler.iss) is started silently
//!   on this install's folder and the launcher quits; the setup replaces the program and starts it again.
//! - Linux, macOS: the release's program takes this one's place (this one is kept as `.old` until the next start)
//!   and the new one is started.
//!
//! Your map, settings and the LLM runtime are never touched. A program built with cargo never updates itself.

use std::fs;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

pub const REPO: &str = "Akulav/ai-security-modeler";
const AGENT: &str = concat!("SecurityModeler/", env!("CARGO_PKG_VERSION"));
pub const VERSION: &str = env!("CARGO_PKG_VERSION");
const FIRST: Duration = Duration::from_secs(60);
const EVERY: Duration = Duration::from_secs(6 * 3600);

/// The release file for this computer (Windows: the setup, which installs and updates alike).
pub fn asset_name() -> &'static str {
    if cfg!(windows) {
        "SecurityModeler-Setup.exe"
    } else if cfg!(target_os = "macos") {
        "SecurityModeler-macos-arm64"
    } else {
        "SecurityModeler-linux-x64"
    }
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct Release {
    pub version: String,
    pub url: String,
    /// GitHub's SHA-256 of this computer's file (lowercase hex).
    pub sha256: String,
    pub notes: String,
    pub page: String,
}

fn agent() -> ureq::Agent {
    ureq::Agent::config_builder()
        .timeout_connect(Some(Duration::from_secs(15)))
        .timeout_recv_response(Some(Duration::from_secs(60)))
        .build()
        .new_agent()
}

/// "v2.10.1" -> [2, 10, 1] (a pre-release suffix is ignored).
fn numbers(v: &str) -> Vec<u64> {
    v.trim().trim_start_matches('v').split(['-', '+']).next().unwrap_or("").split('.')
        .map(|x| x.parse().unwrap_or(0)).collect()
}

/// Is `latest` newer than `current`?
pub fn newer(latest: &str, current: &str) -> bool {
    let (a, b) = (numbers(latest), numbers(current));
    for i in 0..a.len().max(b.len()) {
        let (x, y) = (a.get(i).copied().unwrap_or(0), b.get(i).copied().unwrap_or(0));
        if x != y {
            return x > y;
        }
    }
    false
}

/// The release as GitHub's API describes it (the "latest release" JSON).
pub fn parse_release(json: &str) -> Result<Release, String> {
    let v: serde_json::Value = serde_json::from_str(json).map_err(|e| format!("GitHub's answer: {e}"))?;
    let tag = v["tag_name"].as_str().ok_or("GitHub's answer has no version")?;
    let asset = v["assets"].as_array().and_then(|a| a.iter().find(|a| a["name"].as_str() == Some(asset_name())));
    let field = |key: &str| asset.and_then(|a| a[key].as_str()).unwrap_or("").to_string();
    let sha256 = field("digest").strip_prefix("sha256:")
        .filter(|h| h.len() == 64 && h.chars().all(|c| c.is_ascii_hexdigit()))
        .map(str::to_lowercase).unwrap_or_default();
    Ok(Release {
        version: tag.trim_start_matches('v').to_string(),
        url: field("browser_download_url"),
        sha256,
        notes: v["body"].as_str().unwrap_or("").chars().take(4000).collect(),
        page: v["html_url"].as_str().unwrap_or("").to_string(),
    })
}

pub fn latest() -> Result<Release, String> {
    let url = format!("https://api.github.com/repos/{REPO}/releases/latest");
    let mut response = agent().get(&url).header("User-Agent", AGENT).header("Accept", "application/vnd.github+json")
        .call().map_err(|e| match e {
            ureq::Error::StatusCode(404) => format!("GitHub shows no release of {REPO} yet"),
            ureq::Error::StatusCode(code) => format!("GitHub answered {code}; try again later"),
            other => format!("couldn't reach GitHub: {other}"),
        })?;
    let body = response.body_mut().read_to_string().map_err(|e| format!("couldn't read GitHub's answer: {e}"))?;
    parse_release(&body)
}

fn now() -> u64 {
    SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0)
}

pub fn state_file(home: &Path) -> PathBuf {
    home.join("update.json")
}
pub fn request_file(home: &Path) -> PathBuf {
    home.join("update.request")
}
pub fn apply_file(home: &Path) -> PathBuf {
    home.join("update.apply")
}

/// A program built on this computer (cargo build: target/debug, target/release) never replaces itself.
pub fn self_built(exe: &Path) -> bool {
    exe.components().any(|c| c.as_os_str() == "target")
}

pub fn managed() -> bool {
    std::env::current_exe().is_ok_and(|exe| !self_built(&exe))
}

/// What the app's page and the tray show: update.json in the home folder.
pub fn write_state(home: &Path, rel: Option<&Release>, error: &str, state: &str) {
    let v = serde_json::json!({
        "current": VERSION,
        "latest": rel.map(|r| r.version.clone()),
        "newer": rel.is_some_and(|r| newer(&r.version, VERSION) && !r.url.is_empty()),
        "notes": rel.map(|r| r.notes.clone()).unwrap_or_default(),
        "page": rel.map(|r| r.page.clone()).unwrap_or_default(),
        "checked": now(),
        "error": error,
        "state": state,
        "asset": asset_name(),
        "managed": managed(),
    });
    let path = state_file(home);
    let tmp = path.with_extension("json.tmp");
    if fs::write(&tmp, serde_json::to_string_pretty(&v).unwrap_or_default()).is_ok() {
        let _ = fs::rename(&tmp, &path);
    }
}

/// Check now. The release when it's newer than this program (the reason of a failure is in update.json).
pub fn check(home: &Path) -> Option<Release> {
    match latest() {
        Ok(r) => {
            let is_newer = newer(&r.version, VERSION) && !r.url.is_empty();
            write_state(home, Some(&r), "", "checked");
            is_newer.then_some(r)
        }
        Err(e) => {
            write_state(home, None, &e, "check failed");
            None
        }
    }
}

fn sha256_hex(data: &[u8]) -> String {
    use sha2::{Digest, Sha256};
    Sha256::digest(data).iter().map(|b| format!("{b:02x}")).collect()
}

/// Download this computer's release file to `dest`, checked against GitHub's SHA-256 of it.
pub fn download(rel: &Release, dest: &Path, status: &dyn Fn(&str)) -> Result<PathBuf, String> {
    if rel.url.is_empty() {
        return Err(format!("the release {} has no {}", rel.version, asset_name()));
    }
    if rel.sha256.is_empty() {
        return Err(format!("the release {} has no checksum for {}", rel.version, asset_name()));
    }
    let response = agent().get(&rel.url).header("User-Agent", AGENT).header("Accept", "application/octet-stream")
        .call().map_err(|e| format!("download failed: {e}"))?;
    let total: usize = response.headers().get("content-length").and_then(|v| v.to_str().ok())
        .and_then(|s| s.parse().ok()).unwrap_or(0);
    let mut reader = response.into_body().into_reader();
    let mut data = Vec::with_capacity(total.max(1 << 20));
    let mut buf = vec![0u8; 1 << 16];
    let mut said = 0;
    loop {
        let n = reader.read(&mut buf).map_err(|e| format!("download failed: {e}"))?;
        if n == 0 {
            break;
        }
        data.extend_from_slice(&buf[..n]);
        if total > 0 && data.len() * 100 / total >= said + 10 {
            said = data.len() * 100 / total;
            status(&format!("Downloading {} ({said}%)", rel.version));
        }
    }
    if total > 0 && data.len() != total {
        return Err(format!("download cut short ({} of {total} bytes)", data.len()));
    }
    if sha256_hex(&data) != rel.sha256 {
        return Err("the download doesn't match the release's checksum, so nothing was installed".into());
    }
    if let Some(p) = dest.parent() {
        let _ = fs::create_dir_all(p);
    }
    let mut f = fs::File::create(dest).map_err(|e| format!("couldn't save the download: {e}"))?;
    f.write_all(&data).map_err(|e| format!("couldn't save the download: {e}"))?;
    drop(f);
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let _ = fs::set_permissions(dest, fs::Permissions::from_mode(0o755));
    }
    Ok(dest.to_path_buf())
}

/// Where the downloaded setup waits.
pub fn setup_file(home: &Path, version: &str) -> PathBuf {
    home.join("cache").join("update").join(format!("SecurityModeler-Setup-{version}.exe"))
}

/// The setup's options for an update: this folder, a progress window but no questions, start the app when done.
pub fn setup_args(app_dir: &Path, home: &Path) -> Vec<String> {
    vec!["/SILENT".into(), "/SUPPRESSMSGBOXES".into(), "/NORESTART".into(), "/UPDATE".into(),
         format!("/DIR={}", app_dir.display()),
         format!("/LOG={}", home.join("logs").join("setup.log").display())]
}

/// program -> program.new / program.old
pub fn sibling(exe: &Path, ext: &str) -> PathBuf {
    let mut s = exe.as_os_str().to_owned();
    s.push(format!(".{ext}"));
    PathBuf::from(s)
}

/// Put the new program in this one's place (this one is kept as .old until the next start removes it).
pub fn swap(exe: &Path, new: &Path) -> Result<(), String> {
    let old = sibling(exe, "old");
    let _ = fs::remove_file(&old);
    fs::rename(exe, &old).map_err(|e| format!("couldn't move this program aside: {e}"))?;
    if let Err(e) = fs::rename(new, exe) {
        let _ = fs::rename(&old, exe);
        return Err(format!("couldn't put the new program in place: {e}"));
    }
    Ok(())
}

/// What a step of the update left behind: the previous program, an unfinished download, used setups.
pub fn clean_up(exe: &Path, home: &Path) {
    let _ = fs::remove_file(sibling(exe, "old"));
    let _ = fs::remove_file(sibling(exe, "new"));
    let _ = fs::remove_dir_all(home.join("cache").join("update"));
    let _ = fs::remove_file(apply_file(home));
}

/// Download and check this system's file and put it in place. Ok(next step) means the update is ready: the caller
/// quits the app, then calls `finish` with it. Nothing changes on an Err.
pub fn prepare(home: &Path, rel: &Release, status: &dyn Fn(&str)) -> Result<PathBuf, String> {
    let exe = std::env::current_exe().map_err(|e| format!("where is this program? {e}"))?;
    if self_built(&exe) {
        return Err("this program was built on this computer: update it from the source instead".into());
    }
    write_state(home, Some(rel), "", "downloading");
    if cfg!(windows) {
        download(rel, &setup_file(home, &rel.version), status)
    } else {
        let new = download(rel, &sibling(&exe, "new"), status)?;
        swap(&exe, &new)?;
        Ok(exe)
    }
}

/// After the app has stopped: start the setup (Windows) or the new program (elsewhere). The launcher then exits.
pub fn finish(home: &Path, next: &Path) -> Result<(), String> {
    let exe = std::env::current_exe().map_err(|e| e.to_string())?;
    let mut command = std::process::Command::new(next);
    if cfg!(windows) {
        let dir = exe.parent().ok_or("where is this program's folder?")?;
        command.args(setup_args(dir, home));
    } else {
        command.arg("--after-update");
    }
    crate::platform::detach(&mut command);
    command.spawn().map(|_| ()).map_err(|e| format!("couldn't start the update: {e}"))
}

pub enum Found {
    Newer(Release),
    Nothing,
    Apply,
}

/// The background check: a minute after start, every 6 hours, when update.request appears, and update.apply.
pub fn watch(home: PathBuf, found: impl Fn(Found) + Send + 'static) {
    let _ = fs::remove_file(apply_file(&home));
    std::thread::spawn(move || {
        let mut next = Instant::now() + FIRST;
        loop {
            if fs::remove_file(apply_file(&home)).is_ok() {
                found(Found::Apply);
            }
            if fs::remove_file(request_file(&home)).is_ok() || Instant::now() >= next {
                write_state(&home, None, "", "checking");
                found(check(&home).map_or(Found::Nothing, Found::Newer));
                next = Instant::now() + EVERY;
            }
            std::thread::sleep(Duration::from_secs(2));
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn versions_compare_by_number() {
        assert!(newer("0.10.0", "0.9.9"));
        assert!(newer("v1.2.1", "1.2.0"));
        assert!(!newer("1.2.0", "1.2.0"));
        assert!(!newer("1.1.9", "1.2.0"));
        assert!(!newer("1.2.0-beta", "1.2.0"));
    }

    #[test]
    fn the_release_gives_this_systems_file_and_its_digest() {
        let h = "AB".repeat(32);
        let json = format!(r#"{{"tag_name": "v0.3.0", "html_url": "https://x/r", "body": "notes", "assets": [
            {{"name": "other", "browser_download_url": "https://dl/other"}},
            {{"name": "{}", "browser_download_url": "https://dl/me", "digest": "sha256:{h}"}}]}}"#, asset_name());
        let r = parse_release(&json).unwrap();
        assert_eq!((r.version.as_str(), r.url.as_str(), r.notes.as_str()), ("0.3.0", "https://dl/me", "notes"));
        assert_eq!(r.sha256, h.to_lowercase());
        assert_eq!(parse_release(&json.replace("sha256:", "md5:")).unwrap().sha256, "");
        assert!(parse_release("{}").is_err());
    }

    #[test]
    fn swap_keeps_the_old_program_until_clean_up() {
        let dir = std::env::temp_dir().join(format!("sm-swap-{}", std::process::id()));
        fs::create_dir_all(&dir).unwrap();
        let exe = dir.join("prog");
        fs::write(&exe, b"old").unwrap();
        fs::write(sibling(&exe, "new"), b"new").unwrap();
        swap(&exe, &sibling(&exe, "new")).unwrap();
        assert_eq!(fs::read(&exe).unwrap(), b"new");
        assert_eq!(fs::read(sibling(&exe, "old")).unwrap(), b"old");
        clean_up(&exe, &dir);
        assert!(!sibling(&exe, "old").exists());
        assert!(swap(&exe, &sibling(&exe, "new")).is_err());
        assert_eq!(fs::read(&exe).unwrap(), b"new");
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn the_setup_updates_this_folder_silently() {
        let args = setup_args(Path::new("D:/Apps/SM"), Path::new("D:/Apps/SM"));
        assert!(args.contains(&"/SILENT".to_string()) && args.contains(&"/UPDATE".to_string()));
        assert!(args.contains(&"/DIR=D:/Apps/SM".to_string()));
        assert!(self_built(Path::new("C:/src/launcher/target/release/SecurityModeler.exe")));
        assert!(!self_built(Path::new("C:/Users/me/AppData/Local/SecurityModeler/SecurityModeler.exe")));
    }
}
