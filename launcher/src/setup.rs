//! First-run setup, repeated only for what changed: unpacks the app, then gets uv, Python and the
//! backend's packages. Everything goes in the app's home folder, so nothing is installed system-wide.

use sha2::{Digest, Sha256};
use std::fs;
use std::io::{self, Cursor};
use std::os::windows::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::Command;

/// The backend and built frontend, packed in by build.rs.
static PAYLOAD: &[u8] = include_bytes!(concat!(env!("OUT_DIR"), "/payload.zip"));
const PAYLOAD_HASH: &str = env!("PAYLOAD_HASH");

const UV_VERSION: &str = "0.9.7";
const UV_ASSET: &str = "uv-x86_64-pc-windows-msvc.zip";
const PYTHON_VERSION: &str = "3.13";
pub const NO_WINDOW: u32 = 0x0800_0000;

pub struct Runtime {
    pub python: PathBuf,
    /// Holds backend/ and frontend/dist.
    pub app: PathBuf,
    pub packages: PathBuf,
}

pub fn prepare(home: &Path, report: &dyn Fn(&str)) -> Result<Runtime, String> {
    report("Unpacking the app");
    let app = unpack_app(home).map_err(|error| format!("Couldn't unpack the app: {error}"))?;
    let settings = home.join(".env");
    if !settings.exists() {
        fs::copy(app.join(".env.example"), &settings).map_err(|error| format!("Couldn't create .env: {error}"))?;
    }

    let uv = get_uv(home, report)?;
    let python = get_python(home, &uv, report)?;
    let packages = get_packages(home, &uv, &python, &app, report)?;
    Ok(Runtime { python, app, packages })
}

fn unpack_app(home: &Path) -> io::Result<PathBuf> {
    let app = home.join("app");
    let marker = app.join(".payload");
    if fs::read_to_string(&marker).is_ok_and(|hash| hash == PAYLOAD_HASH) {
        return Ok(app);
    }
    // Unpacked beside the old copy and swapped in last, so a half-finished unpack never counts.
    let fresh = home.join("app.new");
    let _ = fs::remove_dir_all(&fresh);
    zip::ZipArchive::new(Cursor::new(PAYLOAD))?.extract(&fresh)?;
    fs::write(fresh.join(".payload"), PAYLOAD_HASH)?;
    let _ = fs::remove_dir_all(&app);
    fs::rename(&fresh, &app)?;
    Ok(app)
}

fn get_uv(home: &Path, report: &dyn Fn(&str)) -> Result<PathBuf, String> {
    let folder = home.join("tools").join("uv");
    let exe = folder.join("uv.exe");
    let marker = folder.join("VERSION");
    if exe.exists() && fs::read_to_string(&marker).is_ok_and(|version| version == UV_VERSION) {
        return Ok(exe);
    }
    report("Downloading uv, which installs Python");
    let base = format!("https://github.com/astral-sh/uv/releases/download/{UV_VERSION}");
    let checksum = download(&format!("{base}/{UV_ASSET}.sha256"))?;
    let expected = String::from_utf8_lossy(&checksum)
        .split_whitespace()
        .next()
        .unwrap_or_default()
        .to_lowercase();
    let archive = download(&format!("{base}/{UV_ASSET}"))?;
    if hex(&Sha256::digest(&archive)) != expected {
        return Err("The uv download failed its checksum. Try again.".into());
    }
    let _ = fs::remove_dir_all(&folder);
    zip::ZipArchive::new(Cursor::new(archive))
        .and_then(|mut zip| zip.extract(&folder))
        .map_err(|error| format!("Couldn't unpack uv: {error}"))?;
    fs::write(&marker, UV_VERSION).map_err(|error| error.to_string())?;
    Ok(exe)
}

/// A Python of the app's own, managed by uv inside the home folder.
fn get_python(home: &Path, uv: &Path, report: &dyn Fn(&str)) -> Result<PathBuf, String> {
    let find = || uv_command(home, uv, &["python", "find", PYTHON_VERSION, "--python-preference", "only-managed"]);
    if let Ok(found) = find() {
        return Ok(PathBuf::from(found.trim()));
    }
    report("Downloading Python");
    uv_command(home, uv, &["python", "install", PYTHON_VERSION])?;
    Ok(PathBuf::from(find()?.trim()))
}

fn get_packages(home: &Path, uv: &Path, python: &Path, app: &Path, report: &dyn Fn(&str)) -> Result<PathBuf, String> {
    let requirements = app.join("backend").join("requirements.txt");
    let wanted = {
        let listed = fs::read(&requirements).map_err(|error| error.to_string())?;
        let mut hash = Sha256::new();
        hash.update(&listed);
        hash.update(python.to_string_lossy().as_bytes());
        hex(&hash.finalize())
    };
    let packages = home.join("packages");
    let marker = packages.join(".requirements");
    if fs::read_to_string(&marker).is_ok_and(|hash| hash == wanted) {
        return Ok(packages);
    }
    report("Installing the app's Python packages");
    let fresh = home.join("packages.new");
    let _ = fs::remove_dir_all(&fresh);
    uv_command(home, uv, &[
        "pip", "install", "--quiet",
        "--python", &python.to_string_lossy(),
        "--target", &fresh.to_string_lossy(),
        "-r", &requirements.to_string_lossy(),
    ])?;
    fs::write(fresh.join(".requirements"), &wanted).map_err(|error| error.to_string())?;
    let _ = fs::remove_dir_all(&packages);
    fs::rename(&fresh, &packages).map_err(|error| error.to_string())?;
    Ok(packages)
}

fn uv_command(home: &Path, uv: &Path, args: &[&str]) -> Result<String, String> {
    let output = Command::new(uv)
        .args(args)
        // Kept inside the home folder, and unaffected by any uv the user has configured.
        .env("UV_PYTHON_INSTALL_DIR", home.join("python"))
        .env("UV_CACHE_DIR", home.join("cache").join("uv"))
        .env("UV_NO_CONFIG", "1")
        .env_remove("VIRTUAL_ENV")
        .creation_flags(NO_WINDOW)
        .output()
        .map_err(|error| format!("Couldn't run uv: {error}"))?;
    if output.status.success() {
        return Ok(String::from_utf8_lossy(&output.stdout).into_owned());
    }
    let detail = String::from_utf8_lossy(&output.stderr);
    let tail: Vec<&str> = detail.lines().rev().take(6).collect();
    Err(format!(
        "uv {} failed:\n{}",
        args.first().unwrap_or(&""),
        tail.into_iter().rev().collect::<Vec<_>>().join("\n")
    ))
}

fn download(url: &str) -> Result<Vec<u8>, String> {
    let failed = |error: &dyn std::fmt::Display| format!("Couldn't download {url}: {error}. Check your internet connection.");
    let response = ureq::get(url).call().map_err(|error| failed(&error))?;
    let mut data = Vec::new();
    io::copy(&mut response.into_body().into_reader(), &mut data).map_err(|error| failed(&error))?;
    Ok(data)
}

pub fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}
