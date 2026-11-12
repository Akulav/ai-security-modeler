//! The few Linux and macOS calls the launcher needs, matching win.rs.

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
/// kernel stops the backend on Linux (see `prepare_child`), whose own shutdown then stops Ollama.
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

/// Starts a child in its own process group, and on Linux has the kernel stop it if the launcher dies.
pub fn prepare_child(command: &mut Command) {
    command.process_group(0);
    #[cfg(target_os = "linux")]
    unsafe {
        command.pre_exec(|| {
            libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGTERM);
            Ok(())
        });
    }
}

/// Starts a program that outlives the launcher (the installed copy, or the new version after an update).
pub fn detach(command: &mut Command) {
    command.stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null());
    unsafe {
        command.pre_exec(|| {
            libc::setsid();
            Ok(())
        });
    }
}

pub fn home() -> PathBuf {
    if let Some(custom) = std::env::var_os("SECURITY_MODELER_HOME") {
        return PathBuf::from(custom);
    }
    // An install keeps everything next to the program; so does `--here` (a portable copy).
    if let Some(dir) = std::env::current_exe().ok().and_then(|exe| exe.parent().map(Path::to_path_buf))
        && (crate::install::is_install(&dir) || std::env::args().any(|a| a == "--here"))
    {
        return dir;
    }
    crate::install::usual_dir().unwrap_or_else(|| std::env::temp_dir().join("SecurityModeler"))
}

static LOCK: Mutex<Option<File>> = Mutex::new(None);

/// False if another copy of the launcher is already running for this data folder.
pub fn first_instance(home: &Path) -> bool {
    let _ = fs::create_dir_all(home);
    let Ok(file) = OpenOptions::new().create(true).truncate(false).write(true).open(home.join("launcher.lock")) else {
        return true;
    };
    let locked = unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } == 0;
    if locked {
        // Held until this process exits (or release_instance), when the kernel releases it.
        *LOCK.lock().unwrap() = Some(file);
    }
    locked
}

/// Lets go of the lock first_instance took, so another copy can run in this folder.
pub fn release_instance(_home: &Path) {
    LOCK.lock().unwrap().take();
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

fn shown(program: &str, args: &[&str]) -> bool {
    Command::new(program)
        .args(args)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .is_ok_and(|status| status.success() || status.code() == Some(1))
}

/// Shows a dialog where the desktop has a tool for it, and always prints the message.
pub fn message(text: &str, error: bool) {
    if error {
        eprintln!("{text}");
    } else {
        println!("{text}");
    }
    if cfg!(target_os = "macos") {
        let quoted = text.replace('\\', "\\\\").replace('"', "\\\"");
        let icon = if error { "stop" } else { "note" };
        shown("osascript", &["-e", &format!(
            "display dialog \"{quoted}\" with title \"Security Modeler\" buttons {{\"OK\"}} default button 1 with icon {icon}")]);
        return;
    }
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
    let opener = if cfg!(target_os = "macos") { "open" } else { "xdg-open" };
    let _ = Command::new(opener)
        .arg(target)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn();
}

/// True when there's a desktop to show a tray icon on (a Mac always has its menu bar).
pub fn has_desktop() -> bool {
    cfg!(target_os = "macos") || std::env::var_os("DISPLAY").is_some() || std::env::var_os("WAYLAND_DISPLAY").is_some()
}
