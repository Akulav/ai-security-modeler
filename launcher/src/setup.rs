//! First-run setup, repeated only for what changed: unpacks the app, then gets uv, Python and the
//! backend's packages. Everything goes in the app's home folder, so nothing is installed system-wide.

use crate::platform;
use sha2::{Digest, Sha256};
use std::fs;
use std::io::{self, Cursor};
use std::path::{Path, PathBuf};
use std::process::Command;

/// The backend and built frontend, packed in by build.rs.
static PAYLOAD: &[u8] = include_bytes!(concat!(env!("OUT_DIR"), "/payload.zip"));
const PAYLOAD_HASH: &str = env!("PAYLOAD_HASH");

const UV_VERSION: &str = "0.9.7";
#[cfg(windows)]
const UV_TRIPLE: &str = "x86_64-pc-windows-msvc";
#[cfg(all(target_os = "linux", target_arch = "x86_64"))]
const UV_TRIPLE: &str = "x86_64-unknown-linux-gnu";
#[cfg(all(target_os = "linux", target_arch = "aarch64"))]
const UV_TRIPLE: &str = "aarch64-unknown-linux-gnu";
#[cfg(target_os = "macos")]
const UV_TRIPLE: &str = "aarch64-apple-darwin";
#[cfg(windows)]
const UV_ASSET: &str = "uv-x86_64-pc-windows-msvc.zip";
#[cfg(all(target_os = "linux", target_arch = "x86_64"))]
const UV_ASSET: &str = "uv-x86_64-unknown-linux-gnu.tar.gz";
#[cfg(all(target_os = "linux", target_arch = "aarch64"))]
const UV_ASSET: &str = "uv-aarch64-unknown-linux-gnu.tar.gz";
#[cfg(target_os = "macos")]
const UV_ASSET: &str = "uv-aarch64-apple-darwin.tar.gz";
const PYTHON_VERSION: &str = "3.13";

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
    // The Windows zip has uv at its top; the Linux archive has it in a folder named for the platform.
    let exe = if cfg!(windows) { folder.join("uv.exe") } else { folder.join(format!("uv-{UV_TRIPLE}")).join("uv") };
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
    unpack_uv(archive, &folder).map_err(|error| format!("Couldn't unpack uv: {error}"))?;
    fs::write(&marker, UV_VERSION).map_err(|error| error.to_string())?;
    Ok(exe)
}

#[cfg(windows)]
fn unpack_uv(archive: Vec<u8>, folder: &Path) -> io::Result<()> {
    zip::ZipArchive::new(Cursor::new(archive))?.extract(folder).map_err(io::Error::other)
}

#[cfg(unix)]
fn unpack_uv(archive: Vec<u8>, folder: &Path) -> io::Result<()> {
    let mut bundle = tar::Archive::new(flate2::read::GzDecoder::new(Cursor::new(archive)));
    // Keeps uv executable. Entries can't land outside the folder: `unpack` refuses those paths.
    bundle.set_preserve_permissions(true);
    bundle.unpack(folder)
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
    let mut command = Command::new(uv);
    platform::prepare_child(&mut command);
    contain(&mut command, home);
    let output = command
        .args(args)
        // Kept inside the home folder, and unaffected by any uv the user has configured.
        .env("UV_PYTHON_INSTALL_DIR", home.join("python"))
        .env("UV_CACHE_DIR", home.join("cache").join("uv"))
        .env("UV_NO_CONFIG", "1")
        // Nothing outside the folder: no python3.x shims in ~/.local/bin, no Python entry in the Windows registry.
        .env("UV_PYTHON_INSTALL_BIN", "0")
        .env("UV_PYTHON_INSTALL_REGISTRY", "0")
        .env("UV_TOOL_DIR", home.join("cache").join("uv-tools"))
        .env_remove("VIRTUAL_ENV")
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

/// Everything uv, Python and the LLM runtime write goes into the home folder, nowhere else on the computer:
/// temporary files, pip's and uv's caches, the per-user site folder. (Ollama gets its own home there as well:
/// backend/app/services/runtime.py.)
pub fn contain(command: &mut Command, home: &Path) {
    let tmp = home.join("cache").join("tmp");
    let _ = fs::create_dir_all(&tmp);
    command
        .env("TMP", &tmp)
        .env("TEMP", &tmp)
        .env("TMPDIR", &tmp)
        .env("PIP_CACHE_DIR", home.join("cache").join("pip"))
        .env("PYTHONUSERBASE", home.join("cache").join("userbase"))
        .env("PYTHONNOUSERSITE", "1")
        .env("MPLCONFIGDIR", home.join("cache").join("matplotlib"));
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
