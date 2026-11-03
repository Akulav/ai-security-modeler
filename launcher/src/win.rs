//! The few Windows calls the launcher needs.

use std::os::windows::io::AsRawHandle;
use std::process::Child;
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

/// False if another copy of the launcher is already running for this user.
pub fn first_instance() -> bool {
    let name = wide("Local\\SecurityModeler.Launcher");
    unsafe {
        // Never closed: Windows releases it when this process exits.
        let mutex = CreateMutexW(null(), 0, name.as_ptr());
        !mutex.is_null() && GetLastError() != ERROR_ALREADY_EXISTS
    }
}

const QUIT_EVENT: &str = "Local\\SecurityModeler.Quit";

/// Blocks until `SecurityModeler.exe --quit` asks this copy to quit.
pub fn wait_for_quit_request() {
    let name = wide(QUIT_EVENT);
    unsafe {
        let event = CreateEventW(null(), 0, 0, name.as_ptr());
        if !event.is_null() {
            WaitForSingleObject(event, INFINITE);
        }
    }
}

/// Asks the running copy to quit, as its tray menu's Quit does.
pub fn request_quit() {
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
