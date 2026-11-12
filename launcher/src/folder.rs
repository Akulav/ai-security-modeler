//! Asking where to install, on Linux and macOS (Windows' setup asks itself). The same in all of Akulav's apps: a
//! dialog offers the usual folder, or another one picked in the system's folder chooser. Whatever is chosen, the app
//! keeps everything in that one folder.
#![cfg_attr(not(unix), allow(dead_code))]

use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

/// What the dialogs say, in the app's language.
pub struct Texts<'a> {
    pub title: &'a str,
    /// "{dir}" is replaced by the usual folder.
    pub question: &'a str,
    pub install: &'a str,
    pub choose: &'a str,
    pub cancel: &'a str,
    pub prompt: &'a str,
}

enum Choice {
    Usual,
    Other,
    Cancel,
}

fn output(program: &str, args: &[&str]) -> Option<(i32, String)> {
    let out = Command::new(program).args(args).stdin(Stdio::null()).stderr(Stdio::null()).output().ok()?;
    Some((out.status.code().unwrap_or(-1), String::from_utf8_lossy(&out.stdout).trim().to_string()))
}

fn quote(s: &str) -> String {
    s.replace('\\', "\\\\").replace('"', "\\\"")
}

fn ask(t: &Texts, question: &str) -> Choice {
    if cfg!(target_os = "macos") {
        let script = format!(
            "display dialog \"{}\" with title \"{}\" buttons {{\"{}\", \"{}\", \"{}\"}} default button \"{}\" cancel button \"{}\"",
            quote(question), quote(t.title), quote(t.cancel), quote(t.choose), quote(t.install), quote(t.install), quote(t.cancel));
        return match output("osascript", &["-e", &script]) {
            None => Choice::Usual,
            Some((0, out)) if out.ends_with(t.choose) => Choice::Other,
            Some((0, _)) => Choice::Usual,
            Some(_) => Choice::Cancel,
        };
    }
    let (ok, cancel, extra) = (format!("--ok-label={}", t.install), format!("--cancel-label={}", t.cancel),
                               format!("--extra-button={}", t.choose));
    let title = format!("--title={}", t.title);
    let text = format!("--text={question}");
    if let Some((code, out)) = output("zenity", &["--question", &title, &text, &ok, &cancel, &extra, "--width=480"]) {
        return match code {
            0 => Choice::Usual,
            1 if out == t.choose => Choice::Other,
            _ => Choice::Cancel,
        };
    }
    match output("kdialog", &["--title", t.title, "--yesnocancel", question, "--yes-label", t.install,
                              "--no-label", t.choose, "--cancel-label", t.cancel]) {
        Some((0, _)) | None => Choice::Usual,
        Some((1, _)) => Choice::Other,
        Some(_) => Choice::Cancel,
    }
}

/// The nearest folder that exists, for the chooser to open at.
fn existing(start: &Path) -> PathBuf {
    let mut p = start.to_path_buf();
    while !p.is_dir() {
        match p.parent() {
            Some(up) => p = up.to_path_buf(),
            None => return PathBuf::from("/"),
        }
    }
    p
}

fn pick(t: &Texts, usual: &Path) -> Option<PathBuf> {
    let start = existing(usual);
    let picked = if cfg!(target_os = "macos") {
        let script = format!("POSIX path of (choose folder with prompt \"{}\" default location (POSIX file \"{}\"))",
                             quote(t.prompt), quote(&start.to_string_lossy()));
        output("osascript", &["-e", &script])
    } else {
        let title = format!("--title={}", t.prompt);
        let filename = format!("--filename={}/", start.display());
        output("zenity", &["--file-selection", "--directory", &title, &filename])
            .or_else(|| output("kdialog", &["--getexistingdirectory", &start.to_string_lossy(), "--title", t.prompt]))
    };
    match picked {
        Some((0, path)) if !path.is_empty() => Some(PathBuf::from(path.trim_end_matches('/'))),
        _ => None,
    }
}

/// The folder to install into: the picked folder itself when it's empty, already this app's, or named like it;
/// otherwise a folder named `dir_name` inside it.
pub fn resolve(picked: &Path, dir_name: &str, is_install: impl Fn(&Path) -> bool) -> PathBuf {
    let empty = std::fs::read_dir(picked).map(|mut d| d.next().is_none()).unwrap_or(true);
    if empty || is_install(picked) || picked.file_name().is_some_and(|n| n == dir_name) {
        picked.to_path_buf()
    } else {
        picked.join(dir_name)
    }
}

/// Asks where to install. None means the person cancelled.
pub fn choose(t: &Texts, usual: &Path, dir_name: &str, is_install: impl Fn(&Path) -> bool) -> Option<PathBuf> {
    let question = t.question.replace("{dir}", &usual.display().to_string());
    match ask(t, &question) {
        Choice::Usual => Some(usual.to_path_buf()),
        Choice::Cancel => None,
        Choice::Other => pick(t, usual).map(|p| resolve(&p, dir_name, is_install)),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_busy_folder_gets_a_folder_of_its_own() {
        let dir = std::env::temp_dir().join(format!("akulav-folder-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        assert_eq!(resolve(&dir, "App", |_| false), dir, "an empty folder is used as it is");
        std::fs::write(dir.join("other.txt"), b"x").unwrap();
        assert_eq!(resolve(&dir, "App", |_| false), dir.join("App"));
        assert_eq!(resolve(&dir, "App", |_| true), dir, "an install of this app is used as it is");
        let _ = std::fs::remove_dir_all(&dir);
    }
}
