//! The few Windows calls the launcher needs.

use std::os::windows::io::AsRawHandle;
use std::os::windows::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command};
use std::ptr::{null, null_mut};
use windows_sys::Win32::Foundation::{CloseHandle, ERROR_ALREADY_EXISTS, GetLastError, HANDLE};
use windows_sys::Win32::System::JobObjects::{
    AssignProcessToJobObject, CreateJobObjectW, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JobObjectExtendedLimitInformation, SetInformationJobObject,
    TerminateJobObject,
};
use windows_sys::Win32::System::Threading::{CreateEventW, CreateMutexW, INFINITE, SetEvent, WaitForSingleObject};
use windows_sys::Win32::UI::Shell::ShellExecuteW;
use windows_sys::Win32::UI::WindowsAndMessaging::{
    MB_ICONERROR, MB_ICONINFORMATION, MB_OK, MB_SETFOREGROUND, MessageBoxW, SW_SHOWNORMAL,
};

fn wide(text: &str) -> Vec<u16> {
    text.encode_utf16().chain(Some(0)).collect()
}

/// Everything the app starts, so all of it ends together: when the launcher quits, crashes or
/// is killed, Windows closes this handle and ends the backend, Ollama and its model runners.
pub struct Job(HANDLE);

// The handle is only passed to thread-safe kernel calls.
unsafe impl Send for Job {}
unsafe impl Sync for Job {}

impl Job {
    pub fn new() -> Option<Job> {
        unsafe {
            let job = CreateJobObjectW(null(), null());
            if job.is_null() {
                return None;
            }
            let mut limits: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
            limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            let ok = SetInformationJobObject(
                job,
                JobObjectExtendedLimitInformation,
                &limits as *const _ as *const _,
                size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
            );
            if ok == 0 {
                CloseHandle(job);
                return None;
            }
            Some(Job(job))
        }
    }

    /// Processes the child starts afterwards join the job too.
    pub fn add(&self, child: &Child) -> bool {
        unsafe { AssignProcessToJobObject(self.0, child.as_raw_handle() as HANDLE) != 0 }
    }

    /// Ends every process in the job at once, which frees all the memory they held.
    pub fn terminate(&self) {
        unsafe {
            TerminateJobObject(self.0, 0);
        }
    }
}

const NO_WINDOW: u32 = 0x0800_0000;

/// Starts a child without a console window. The job ends it with the launcher.
pub fn prepare_child(command: &mut Command) {
    command.creation_flags(NO_WINDOW);
}

/// Starts a program that outlives the launcher (the update's setup), without a console window.
pub fn detach(command: &mut Command) {
    command.creation_flags(0x0000_0008 | 0x0000_0200); // DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
}

/// The folder the setup installed into (it holds the setup's uninstaller), or the usual one.
pub fn home() -> PathBuf {
    if let Some(custom) = std::env::var_os("SECURITY_MODELER_HOME") {
        return PathBuf::from(custom);
    }
    if let Some(dir) = std::env::current_exe().ok().and_then(|exe| exe.parent().map(Path::to_path_buf))
        && dir.join("unins000.exe").exists()
    {
        return dir;
    }
    let local = std::env::var_os("LOCALAPPDATA").map(PathBuf::from).unwrap_or_else(std::env::temp_dir);
    local.join("SecurityModeler")
}

/// Windows always has a desktop for the tray.
pub fn has_desktop() -> bool {
    true
}

/// False if another copy of the launcher is already running for this user.
pub fn first_instance(_home: &Path) -> bool {
    let name = wide("Local\\SecurityModeler.Launcher");
    unsafe {
        // Never closed: Windows releases it when this process exits.
        let mutex = CreateMutexW(null(), 0, name.as_ptr());
        if mutex.is_null() {
            return false;
        }
        if GetLastError() == ERROR_ALREADY_EXISTS {
            // Not ours: let go of it, or it would outlive the copy that made it.
            CloseHandle(mutex);
            return false;
        }
        true
    }
}

const QUIT_EVENT: &str = "Local\\SecurityModeler.Quit";

/// Blocks until `SecurityModeler.exe --quit` asks this copy to quit.
pub fn wait_for_quit_request(_home: &Path) {
    let name = wide(QUIT_EVENT);
    unsafe {
        let event = CreateEventW(null(), 0, 0, name.as_ptr());
        if !event.is_null() {
            WaitForSingleObject(event, INFINITE);
        }
    }
}

/// Asks the running copy to quit, as its tray menu's Quit does.
pub fn request_quit(_home: &Path) {
    let name = wide(QUIT_EVENT);
    unsafe {
        let event = CreateEventW(null(), 0, 0, name.as_ptr());
        if !event.is_null() {
            SetEvent(event);
            CloseHandle(event);
        }
    }
}

pub fn message(text: &str, error: bool) {
    let (text, title) = (wide(text), wide("Security Modeler"));
    let icon = if error { MB_ICONERROR } else { MB_ICONINFORMATION };
    unsafe {
        MessageBoxW(null_mut(), text.as_ptr(), title.as_ptr(), MB_OK | MB_SETFOREGROUND | icon);
    }
}

/// Opens a URL in the default browser, or a folder or file in its default program.
pub fn open(target: &str) {
    let (verb, target) = (wide("open"), wide(target));
    unsafe {
        ShellExecuteW(null_mut(), verb.as_ptr(), target.as_ptr(), null(), null(), SW_SHOWNORMAL);
    }
}
