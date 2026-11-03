//! The few Linux calls the launcher needs, matching win.rs.

use std::fs::{self, File, OpenOptions};
use std::os::fd::AsRawFd;
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::Duration;

/// Everything the app starts, so all of it ends together. Each child leads its own process
/// group, so ending the group also ends what it started. If the launcher dies instead, the
/// kernel stops the backend (see `prepare_child`), whose own shutdown then stops Ollama.
pub struct Job(Mutex<Vec<i32>>);

impl Job {
    pub fn new() -> Option<Job> {
        Some(Job(Mutex::new(Vec::new())))
    }

    pub fn add(&self, child: &Child) -> bool {
        self.0.lock().unwrap().push(child.id() as i32);
        true
    }

    pub fn terminate(&self) {
        for group in self.0.lock().unwrap().drain(..) {
            unsafe {
                libc::killpg(group, libc::SIGKILL);
            }
        }
    }
}

/// Starts a child in its own process group, and has the kernel stop it if the launcher dies.
pub fn prepare_child(command: &mut Command) {
    command.process_group(0);
    unsafe {
        command.pre_exec(|| {
            libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGTERM);
            Ok(())
        });
    }
}

pub fn home() -> PathBuf {
    if let Some(custom) = std::env::var_os("SECURITY_MODELER_HOME") {
        return PathBuf::from(custom);
    }
    let data = std::env::var_os("XDG_DATA_HOME")
        .map(PathBuf::from)
        .filter(|path| path.is_absolute())
        .or_else(|| std::env::var_os("HOME").map(|home| PathBuf::from(home).join(".local").join("share")))
        .unwrap_or_else(std::env::temp_dir);
    data.join("SecurityModeler")
}

/// False if another copy of the launcher is already running for this data folder.
pub fn first_instance(home: &Path) -> bool {
    let Ok(file) = OpenOptions::new().create(true).truncate(false).write(true).open(home.join("launcher.lock")) else {
        return true;
    };
    let locked = unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } == 0;
    if locked {
        // Held until this process exits, when the kernel releases it.
        Box::leak(Box::new(file));
    }
    locked
}

static SIGNALLED: AtomicBool = AtomicBool::new(false);

/// Blocks until `SecurityModeler --quit`, Ctrl+C or a termination signal asks this copy to quit.
pub fn wait_for_quit_request(home: &Path) {
    let request = home.join("launcher.quit");
    let _ = fs::remove_file(&request);
    let _ = ctrlc::set_handler(|| SIGNALLED.store(true, Ordering::SeqCst));
    while !SIGNALLED.load(Ordering::SeqCst) {
        if fs::remove_file(&request).is_ok() {
            return;
        }
        std::thread::sleep(Duration::from_millis(400));
    }
}

/// Asks the running copy to quit, as its tray menu's Quit does.
pub fn request_quit(home: &Path) {
    let _ = File::create(home.join("launcher.quit"));
}

/// Shows a dialog where the desktop has a tool for it, and always prints the message.
pub fn message(text: &str, error: bool) {
    if error {
        eprintln!("{text}");
    } else {
        println!("{text}");
    }
    let shown = |program: &str, args: &[&str]| {
        Command::new(program)
            .args(args)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .is_ok_and(|status| status.success() || status.code() == Some(1))
    };
    let kind = if error { "--error" } else { "--info" };
    if !shown("zenity", &[kind, "--title=Security Modeler", "--width=420", &format!("--text={text}")]) {
        let kind = if error { "--error" } else { "--msgbox" };
        if !shown("kdialog", &["--title", "Security Modeler", kind, text]) {
            shown("notify-send", &["Security Modeler", text]);
        }
    }
}

/// Opens a URL in the default browser, or a folder or file in its default program.
pub fn open(target: &str) {
    let _ = Command::new("xdg-open")
        .arg(target)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn();
}

/// True when there's a desktop to show a tray icon on.
pub fn has_desktop() -> bool {
    std::env::var_os("DISPLAY").is_some() || std::env::var_os("WAYLAND_DISPLAY").is_some()
}
