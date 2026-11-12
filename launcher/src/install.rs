//! Installing and uninstalling, the same way in all of Akulav's apps. Wherever it's installed, the app keeps
//! everything in that one folder: the program, your map, its settings, Python, the LLM and its models, the logs,
//! temporary files and downloaded updates. Outside it there is only what makes it show up as an app: the Start menu
//! and Settings → Apps entries on Windows, an app-menu entry on Linux; all of it goes with the uninstall.
//!
//! - Windows: the setup (launcher/installer/security-modeler.iss) asks for the folder, installs, and is also the update.
//!   `--uninstall` starts the setup's uninstaller.
//! - Linux, macOS: the release's program installs itself. Started from anywhere else (Downloads, the desktop), with a
//!   desktop, it asks where to install (usually ~/.local/share/SecurityModeler, or ~/Applications/Security Modeler
//!   on a Mac, where the folder holds a Security Modeler.app too), copies itself there, marks the folder (`.install`)
//!   and starts from there. A later download offers the same folder, and updates the copy in it.
//!
//! It stays where it is with `--here`, `--headless`, a custom SECURITY_MODELER_HOME, and when built with cargo.

use std::path::Path;
#[cfg(unix)]
use std::{fs, path::PathBuf};

#[cfg(unix)]
pub const NAME: &str = "Security Modeler";
#[cfg(unix)]
pub const EXE: &str = "SecurityModeler";
/// Marks a folder this program installed itself into (Linux, macOS); platform::home() looks for it.
#[cfg(unix)]
pub const MARKER: &str = ".install";
#[cfg(all(unix, not(target_os = "macos")))]
const ICON_PNG: &[u8] = include_bytes!("../assets/icon-256.png");
#[cfg(target_os = "macos")]
const ICON_ICNS: &[u8] = include_bytes!("../assets/icon.icns");

#[cfg(unix)]
fn user_home() -> Option<PathBuf> {
    std::env::var_os("HOME").filter(|h| !h.is_empty()).map(PathBuf::from)
}

/// The folder offered first.
#[cfg(unix)]
pub fn usual_dir() -> Option<PathBuf> {
    if cfg!(target_os = "macos") {
        return user_home().map(|h| h.join("Applications").join(NAME));
    }
    std::env::var_os("XDG_DATA_HOME").filter(|d| !d.is_empty()).map(PathBuf::from)
        .or_else(|| user_home().map(|h| h.join(".local").join("share")))
        .map(|d| d.join("SecurityModeler"))
}

/// A folder this app lives in already.
#[cfg(unix)]
pub fn is_install(dir: &Path) -> bool {
    dir.join(MARKER).exists() || dir.join(EXE).is_file() && dir.join("data").is_dir()
}

/// The version of the program at `exe` ("Security Modeler 0.2.0, made by Akulav"), if it answers.
#[cfg(unix)]
fn version_of(exe: &Path) -> Option<String> {
    let out = std::process::Command::new(exe).arg("--version").stdin(std::process::Stdio::null())
        .stderr(std::process::Stdio::null()).output().ok()?;
    String::from_utf8_lossy(&out.stdout).split_whitespace().nth(2).map(|v| v.trim_end_matches(',').to_string())
}

/// Linux, macOS: when this program runs from somewhere else than an install, ask where to install, copy it there
/// and start it. Ok(true) means this one should end (the installed copy runs, or the person cancelled).
#[cfg(unix)]
pub fn install_if_needed(args: &[String]) -> Result<bool, String> {
    let exe = std::env::current_exe().map_err(|e| e.to_string())?;
    let Some(dir) = exe.parent() else { return Ok(false) };
    if crate::update::self_built(&exe) || is_install(dir) || std::env::var_os("SECURITY_MODELER_HOME").is_some() {
        return Ok(false);
    }
    let Some(usual) = usual_dir() else { return Ok(false) };
    let texts = crate::folder::Texts {
        title: "Install Security Modeler",
        question: "Install Security Modeler in\n{dir} ?\n\nThe program, your map and the local AI (about 18 GB once \
                   downloaded) all stay in that folder.",
        install: "Install",
        choose: "Choose another folder…",
        cancel: "Cancel",
        prompt: "Where should Security Modeler be installed?",
    };
    let Some(target) = crate::folder::choose(&texts, &usual, if cfg!(target_os = "macos") { NAME } else { "SecurityModeler" }, is_install)
    else {
        return Ok(true);
    };
    let this = crate::update::VERSION;
    fs::create_dir_all(&target).map_err(|e| format!("couldn't make {}: {e}", target.display()))?;
    let installed = target.join(EXE);
    let first = !installed.exists();
    let same = !first && fs::read(&installed).ok() == fs::read(&exe).ok();
    let replace = !first && !same && version_of(&installed).is_none_or(|v| crate::update::newer(this, &v));
    if !crate::platform::first_instance(&target) {
        crate::platform::message(&if replace {
            format!("{NAME} is running. Quit it from its tray icon, then start this file again to install version {this}.")
        } else {
            format!("{NAME} is already running from {}.", target.display())
        }, false);
        return Ok(true);
    }
    crate::platform::release_instance(&target);
    if first || replace {
        let new = crate::update::sibling(&installed, "new");
        fs::copy(&exe, &new).map_err(|e| format!("couldn't copy the program to {}: {e}", target.display()))?;
        {
            use std::os::unix::fs::PermissionsExt;
            let _ = fs::set_permissions(&new, fs::Permissions::from_mode(0o755));
        }
        #[cfg(target_os = "macos")]
        let _ = std::process::Command::new("xattr").arg("-d").arg("com.apple.quarantine").arg(&new)
            .stderr(std::process::Stdio::null()).status();
        if installed.exists() {
            crate::update::swap(&installed, &new)?;
        } else {
            fs::rename(&new, &installed).map_err(|e| e.to_string())?;
        }
    }
    fs::write(target.join(MARKER), this).map_err(|e| e.to_string())?;
    if let Err(e) = add_to_system(&installed, &target) {
        eprintln!("Couldn't add {NAME} to the app list: {e}");
    }
    let mut command = std::process::Command::new(&installed);
    command.args(args).current_dir(&target);
    crate::platform::detach(&mut command);
    command.spawn().map_err(|e| format!("couldn't start the installed program: {e}"))?;
    if first {
        crate::platform::message(&format!("{NAME} is installed in {} and starting now. It's in your app list; its \
                                           icon sits in the tray (the menu bar on a Mac).\n\nYou can delete the \
                                           file you downloaded.", target.display()), false);
    }
    Ok(true)
}

#[cfg(all(unix, not(target_os = "macos")))]
fn menu_entry() -> Option<PathBuf> {
    std::env::var_os("XDG_DATA_HOME").filter(|d| !d.is_empty()).map(PathBuf::from)
        .or_else(|| user_home().map(|h| h.join(".local").join("share")))
        .map(|d| d.join("applications").join("security-modeler.desktop"))
}

/// The app-menu entry: the one file outside the install folder (its icon stays inside).
#[cfg(all(unix, not(target_os = "macos")))]
fn add_to_system(exe: &Path, dir: &Path) -> Result<(), String> {
    let icon = dir.join("security-modeler.png");
    fs::write(&icon, ICON_PNG).map_err(|e| e.to_string())?;
    let entry = format!("[Desktop Entry]\nType=Application\nName={NAME}\nComment=Map your accounts and devices, and see \
                         what breaks when one is lost. Made by Akulav.\nExec=\"{}\"\nPath={}\nIcon={}\nTerminal=false\n\
                         Categories=Utility;Security;\n", exe.display(), dir.display(), icon.display());
    let path = menu_entry().ok_or("no home folder")?;
    if let Some(p) = path.parent() {
        fs::create_dir_all(p).map_err(|e| e.to_string())?;
    }
    fs::write(&path, entry).map_err(|e| e.to_string())
}

#[cfg(all(unix, not(target_os = "macos")))]
fn remove_from_system(_dir: &Path) {
    if let Some(p) = menu_entry() {
        let _ = fs::remove_file(p);
    }
}

/// Security Modeler.app inside the install folder (found by Spotlight and Launchpad in ~/Applications): it starts
/// the program beside it. A menu bar app, no Dock icon.
#[cfg(target_os = "macos")]
fn add_to_system(exe: &Path, dir: &Path) -> Result<(), String> {
    use std::os::unix::fs::PermissionsExt;
    let contents = dir.join(format!("{NAME}.app")).join("Contents");
    let err = |e: std::io::Error| e.to_string();
    fs::create_dir_all(contents.join("MacOS")).map_err(err)?;
    fs::create_dir_all(contents.join("Resources")).map_err(err)?;
    let plist = format!(r#"<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>{NAME}</string>
<key>CFBundleDisplayName</key><string>{NAME}</string>
<key>CFBundleIdentifier</key><string>com.akulav.securitymodeler</string>
<key>CFBundleVersion</key><string>{v}</string>
<key>CFBundleShortVersionString</key><string>{v}</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleExecutable</key><string>{EXE}</string>
<key>CFBundleIconFile</key><string>icon</string>
<key>NSHumanReadableCopyright</key><string>Made by Akulav</string>
<key>LSUIElement</key><true/>
</dict></plist>
"#, v = crate::update::VERSION);
    fs::write(contents.join("Info.plist"), plist).map_err(err)?;
    fs::write(contents.join("Resources").join("icon.icns"), ICON_ICNS).map_err(err)?;
    let script = contents.join("MacOS").join(EXE);
    let quoted = exe.to_string_lossy().replace('\'', r"'\''");
    fs::write(&script, format!("#!/bin/sh\nexec '{quoted}' \"$@\"\n")).map_err(err)?;
    fs::set_permissions(&script, fs::Permissions::from_mode(0o755)).map_err(err)?;
    Ok(())
}

#[cfg(target_os = "macos")]
fn remove_from_system(dir: &Path) {
    let _ = fs::remove_dir_all(dir.join(format!("{NAME}.app")));
}

/// `--uninstall`.
pub fn uninstall(home: &Path) {
    #[cfg(windows)]
    {
        let uninstaller = std::env::current_exe().ok().and_then(|e| e.parent().map(|d| d.join("unins000.exe")));
        match uninstaller.filter(|u| u.exists()) {
            Some(u) => {
                let _ = std::process::Command::new(u).spawn();
            }
            None => crate::platform::message("Uninstall Security Modeler from Settings → Apps.", false),
        }
        let _ = home;
    }
    #[cfg(unix)]
    {
        if !crate::platform::first_instance(home) {
            crate::platform::message(&format!("{NAME} is running. Quit it from its tray icon first."), true);
            return;
        }
        remove_from_system(home);
        println!("{NAME} is removed from your app list.");
        eprint!("Also delete {} with your map, settings and the LLM runtime? [y/N] ", home.display());
        let mut line = String::new();
        if std::io::stdin().read_line(&mut line).is_ok() && matches!(line.trim().to_lowercase().as_str(), "y" | "yes") {
            let _ = fs::remove_dir_all(home);
            println!("Deleted {}", home.display());
        } else {
            println!("Kept {}: starting the program in it again brings everything back.", home.display());
        }
    }
}
