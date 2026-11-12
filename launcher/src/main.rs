//! Security Modeler's desktop launcher: sets the app up, runs it in the background, and puts it in
//! the system tray. The app itself is the web page it opens. It also installs itself on Linux and
//! macOS (install.rs) and updates itself from GitHub releases on every system (update.rs).

#![windows_subsystem = "windows"]

#[cfg(any(unix, test))]
mod folder;
mod install;
#[cfg_attr(windows, path = "win.rs")]
#[cfg_attr(unix, path = "unix.rs")]
mod platform;
mod server;
mod setup;
mod update;

use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::PathBuf;
use std::process::Child;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tao::event::{Event, StartCause};
use tao::event_loop::{ControlFlow, EventLoopBuilder, EventLoopProxy};
use tray_icon::menu::{Menu, MenuEvent, MenuItem, PredefinedMenuItem};
use tray_icon::{Icon, MouseButton, MouseButtonState, TrayIcon, TrayIconBuilder, TrayIconEvent};

const VERSION: &str = env!("CARGO_PKG_VERSION");
const REPOSITORY: &str = "https://github.com/Akulav/ai-security-modeler";
/// The tray icon on Linux, as 64×64 RGBA pixels drawn by assets/make_icon.py. Windows uses the
/// icon resource that build.rs embeds.
#[cfg(unix)]
static ICON_RGBA: &[u8] = include_bytes!("../assets/icon-64.rgba");
const STATUS_EVERY: Duration = Duration::from_secs(3);

enum UserEvent {
    Tray(TrayIconEvent),
    Menu(MenuEvent),
    Status(Status),
    Update(update::Found),
    UpdateFailed(String),
    Exit,
}

enum Status {
    Preparing(String),
    Running,
    Llm(String),
    Failed(String),
    Quitting,
}

/// What the tray and the worker thread share.
struct App {
    home: PathBuf,
    token: String,
    job: Option<platform::Job>,
    url: Mutex<Option<String>>,
    backend: Mutex<Option<Child>>,
    quitting: AtomicBool,
    /// A newer release, once the update check found one.
    release: Mutex<Option<update::Release>>,
    updating: AtomicBool,
}

impl App {
    fn url(&self) -> Option<String> {
        self.url.lock().unwrap().clone()
    }

    fn log(&self, line: &str) {
        let seconds = SystemTime::now().duration_since(UNIX_EPOCH).map_or(0, |time| time.as_secs());
        if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(self.home.join("logs").join("launcher.log")) {
            let _ = writeln!(file, "[{seconds}] {line}");
        }
    }
}

fn main() {
    let home: PathBuf = platform::home();
    let _ = fs::create_dir_all(home.join("logs"));
    let url_file = home.join("launcher.url");
    let flag = |name: &str| std::env::args().any(|arg| arg == name);
    if flag("--version") {
        println!("Security Modeler {VERSION}, made by Akulav");
        return;
    }
    // For scripts and shortcuts: quit the running copy, or start without opening the browser.
    if flag("--quit") {
        platform::request_quit(&home);
        return;
    }
    if flag("--uninstall") {
        install::uninstall(&home);
        return;
    }
    if flag("--check-update") {
        match update::latest() {
            Ok(r) if update::newer(&r.version, VERSION) => println!("Security Modeler {} is out (this is {VERSION}): {}", r.version, r.page),
            Ok(r) => println!("Security Modeler {VERSION} is up to date (latest release: {})", r.version),
            Err(e) => println!("Couldn't check: {e}"),
        }
        return;
    }
    // Without a desktop, such as on a server, there's no tray: it runs in the terminal instead.
    let headless = flag("--headless") || !platform::has_desktop();
    let background = flag("--background") || headless;

    // Linux and macOS: a downloaded program installs itself and starts the installed copy.
    #[cfg(unix)]
    if !headless && !flag("--here") {
        let args: Vec<String> = std::env::args().skip(1).filter(|a| a != "--after-update").collect();
        match install::install_if_needed(&args) {
            Ok(true) => return,
            Ok(false) => {}
            Err(e) => platform::message(&format!("Couldn't install Security Modeler: {e}\n\nIt runs from here instead."), true),
        }
    }
    if let Ok(exe) = std::env::current_exe() {
        update::clean_up(&exe, &home);
    }
    let mut first = platform::first_instance(&home);
    // Just updated: the old copy may still be letting go of the folder.
    if !first && (flag("--after-update") || flag("--updated")) {
        for _ in 0..60 {
            std::thread::sleep(Duration::from_millis(500));
            if platform::first_instance(&home) {
                first = true;
                break;
            }
        }
    }

    if !first {
        // Already running: just show it.
        match fs::read_to_string(&url_file) {
            Ok(url) if headless => println!("Security Modeler is already running at {}", url.trim()),
            Ok(url) if !url.trim().is_empty() => platform::open(url.trim()),
            _ => platform::message("Security Modeler is still starting. It opens in your browser when it's ready.", false),
        }
        return;
    }
    let _ = fs::remove_file(&url_file);
    let first_run = !home.join("packages").exists();

    let mut secret = [0u8; 24];
    let _ = getrandom::fill(&mut secret);
    let app = Arc::new(App {
        home: home.clone(),
        token: setup::hex(&secret),
        job: platform::Job::new(),
        url: Mutex::new(None),
        backend: Mutex::new(None),
        quitting: AtomicBool::new(false),
        release: Mutex::new(None),
        updating: AtomicBool::new(false),
    });
    app.log(&format!("Starting version {VERSION}"));
    if headless {
        run_headless(app);
        return;
    }

    let event_loop = EventLoopBuilder::<UserEvent>::with_user_event().build();
    let proxy = event_loop.create_proxy();
    {
        let proxy = proxy.clone();
        TrayIconEvent::set_event_handler(Some(move |event| {
            let _ = proxy.send_event(UserEvent::Tray(event));
        }));
    }
    {
        let proxy = proxy.clone();
        MenuEvent::set_event_handler(Some(move |event| {
            let _ = proxy.send_event(UserEvent::Menu(event));
        }));
    }

    let status = MenuItem::new("Starting", false, None);
    let open = MenuItem::new("Open Security Modeler", false, None);
    let unload = MenuItem::new("Unload the model now", false, None);
    let retry = MenuItem::new("Try again", false, None);
    let update_item = MenuItem::new("Check for updates", update::managed(), None);
    let folder = MenuItem::new("Open data folder", true, None);
    let logs = MenuItem::new("Open logs", true, None);
    let quit = MenuItem::new("Quit", true, None);
    let menu = Menu::new();
    let version = MenuItem::new(format!("Security Modeler {VERSION}"), false, None);
    let author = MenuItem::new("Made by Akulav", true, None);
    let _ = menu.append_items(&[
        &version,
        &author,
        &status,
        &PredefinedMenuItem::separator(),
        &open,
        &unload,
        &retry,
        &PredefinedMenuItem::separator(),
        &update_item,
        &folder,
        &logs,
        &PredefinedMenuItem::separator(),
        &quit,
    ]);

    {
        let (app, proxy) = (app.clone(), proxy.clone());
        std::thread::spawn(move || {
            platform::wait_for_quit_request(&app.home);
            begin_quit(app, proxy);
        });
    }
    if update::managed() {
        let proxy = proxy.clone();
        update::watch(home.clone(), move |found| {
            let _ = proxy.send_event(UserEvent::Update(found));
        });
    } else {
        update::write_state(&home, None, "", "built from source");
    }

    let mut tray: Option<TrayIcon> = None;
    let mut menu = Some(menu);
    let mut opened_once = background;
    event_loop.run(move |event, _, control_flow| {
        *control_flow = ControlFlow::Wait;
        match event {
            Event::NewEvents(StartCause::Init) => {
                let icon = tray_icon();
                let mut builder = TrayIconBuilder::new()
                    // (Linux: the icon file the tray reads stays in the home folder, not in /tmp)
                    .with_temp_dir_path(app.home.join("cache").join("tray"))
                    .with_tooltip("Security Modeler: starting")
                    .with_menu(Box::new(menu.take().unwrap()))
                    // Left click opens the app; right click shows the menu.
                    .with_menu_on_left_click(false);
                if let Some(icon) = icon {
                    builder = builder.with_icon(icon);
                }
                tray = builder.build().ok();
                if first_run {
                    std::thread::spawn(|| {
                        platform::message(
                            "Setting up Security Modeler for its first start. This downloads Python and a few \
                             packages, which takes a minute or two.\n\nIt opens in your browser when it's ready. \
                             Its icon is in the system tray: right-click it to quit.",
                            false,
                        )
                    });
                }
                spawn_worker(app.clone(), proxy.clone());
            }
            Event::UserEvent(UserEvent::Tray(TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            }))
            | Event::UserEvent(UserEvent::Tray(TrayIconEvent::DoubleClick { button: MouseButton::Left, .. })) => {
                if let Some(url) = app.url() {
                    platform::open(&url);
                }
            }
            Event::UserEvent(UserEvent::Menu(event)) => {
                if event.id == open.id() {
                    if let Some(url) = app.url() {
                        platform::open(&url);
                    }
                } else if event.id == unload.id() {
                    if let Some(url) = app.url() {
                        std::thread::spawn(move || server::unload_model(&url));
                    }
                } else if event.id == retry.id() {
                    retry.set_enabled(false);
                    spawn_worker(app.clone(), proxy.clone());
                } else if event.id == folder.id() {
                    platform::open(&app.home.to_string_lossy());
                } else if event.id == logs.id() {
                    platform::open(&app.home.join("logs").to_string_lossy());
                } else if event.id == update_item.id() {
                    if app.release.lock().unwrap().is_some() {
                        update_item.set_enabled(false);
                        begin_update(app.clone(), proxy.clone());
                    } else {
                        update_item.set_text("Checking for updates…");
                        let _ = fs::write(update::request_file(&app.home), b"");
                    }
                } else if event.id == author.id() {
                    platform::open(REPOSITORY);
                } else if event.id == quit.id() {
                    begin_quit(app.clone(), proxy.clone());
                }
            }
            Event::UserEvent(UserEvent::Status(update)) => {
                let (line, running) = match update {
                    Status::Preparing(step) => (format!("{step}…"), false),
                    Status::Running => ("Running".to_string(), true),
                    Status::Llm(summary) => (summary, true),
                    Status::Failed(reason) => {
                        retry.set_enabled(true);
                        (format!("Stopped: {}", reason.lines().next().unwrap_or("see the logs")), false)
                    }
                    Status::Quitting => ("Quitting…".to_string(), false),
                };
                status.set_text(&line);
                open.set_enabled(running);
                unload.set_enabled(running);
                if let Some(tray) = &tray {
                    let _ = tray.set_tooltip(Some(format!("Security Modeler: {line}")));
                }
                if running && !opened_once {
                    opened_once = true;
                    if let Some(url) = app.url() {
                        platform::open(&url);
                    }
                }
            }
            Event::UserEvent(UserEvent::Update(found)) => match found {
                update::Found::Newer(release) => {
                    update_item.set_text(format!("Update to {}", release.version));
                    if let Some(tray) = &tray {
                        let _ = tray.set_tooltip(Some(format!("Security Modeler: version {} is available", release.version)));
                    }
                    *app.release.lock().unwrap() = Some(release);
                }
                update::Found::Nothing => {
                    if app.release.lock().unwrap().is_none() {
                        update_item.set_text("Check for updates (up to date)");
                    }
                }
                update::Found::Apply => {
                    if app.release.lock().unwrap().is_some() {
                        update_item.set_enabled(false);
                        begin_update(app.clone(), proxy.clone());
                    } else {
                        let _ = fs::write(update::request_file(&app.home), b"");
                    }
                }
            },
            Event::UserEvent(UserEvent::UpdateFailed(reason)) => {
                update_item.set_enabled(true);
                status.set_text("Update failed: see the message");
                std::thread::spawn(move || platform::message(&format!("Security Modeler couldn't update.\n\n{reason}"), true));
            }
            Event::UserEvent(UserEvent::Exit) => {
                // Removing the icon first, so no stale icon is left in the tray.
                tray.take();
                *control_flow = ControlFlow::Exit;
            }
            _ => {}
        }
    });
}

/// Sets the app up, runs it, then keeps the tray's status line current until it stops.
fn spawn_worker(app: Arc<App>, proxy: EventLoopProxy<UserEvent>) {
    std::thread::spawn(move || {
        let send = |status| {
            let _ = proxy.send_event(UserEvent::Status(status));
        };
        if let Err(reason) = run(&app, &|step| send(Status::Preparing(step.to_string()))) {
            if app.quitting.load(Ordering::SeqCst) {
                return;
            }
            app.log(&format!("Failed: {reason}"));
            send(Status::Failed(reason.clone()));
            platform::message(
                &format!("Security Modeler couldn't start.\n\n{reason}\n\nThe logs are in {}", app.home.join("logs").display()),
                true,
            );
            return;
        }
        send(Status::Running);
        let url = app.url().unwrap_or_default();
        let mut last = String::new();
        while !app.quitting.load(Ordering::SeqCst) {
            let exited = app.backend.lock().unwrap().as_mut().is_none_or(|child| !matches!(child.try_wait(), Ok(None)));
            if exited {
                if !app.quitting.load(Ordering::SeqCst) {
                    *app.url.lock().unwrap() = None;
                    let _ = fs::remove_file(app.home.join("launcher.url"));
                    app.log("The backend stopped unexpectedly");
                    send(Status::Failed("the app stopped unexpectedly. See the logs.".into()));
                }
                return;
            }
            if let Some(summary) = server::llm_summary(&url)
                && summary != last
            {
                last = summary.clone();
                send(Status::Llm(summary));
            }
            std::thread::sleep(STATUS_EVERY);
        }
    });
}

fn run(app: &App, report: &dyn Fn(&str)) -> Result<(), String> {
    let runtime = setup::prepare(&app.home, report)?;
    report("Starting");
    let port = server::pick_port();
    let url = format!("http://127.0.0.1:{port}");
    let mut child = server::start(&app.home, &runtime, port, &app.token)?;
    if let Some(job) = &app.job
        && !job.add(&child)
    {
        app.log("Couldn't add the backend to the job; it relies on its own cleanup");
    }
    let ready = server::wait_until_ready(&url, &mut child);
    *app.backend.lock().unwrap() = Some(child);
    ready?;
    app.log(&format!("Running at {url}"));
    let _ = fs::write(app.home.join("launcher.url"), &url);
    *app.url.lock().unwrap() = Some(url);
    Ok(())
}

#[cfg(windows)]
fn tray_icon() -> Option<Icon> {
    Icon::from_resource(1, Some((32, 32))).ok()
}

#[cfg(unix)]
fn tray_icon() -> Option<Icon> {
    Icon::from_rgba(ICON_RGBA.to_vec(), 64, 64).ok()
}

fn begin_quit(app: Arc<App>, proxy: EventLoopProxy<UserEvent>) {
    if app.quitting.swap(true, Ordering::SeqCst) {
        return;
    }
    let _ = proxy.send_event(UserEvent::Status(Status::Quitting));
    std::thread::spawn(move || {
        shutdown(&app);
        let _ = proxy.send_event(UserEvent::Exit);
    });
}

/// Downloads and checks the newer release while the app keeps running, then quits the app and hands over to the
/// setup (Windows) or the new program (Linux, macOS), which starts the app again.
fn begin_update(app: Arc<App>, proxy: EventLoopProxy<UserEvent>) {
    let Some(release) = app.release.lock().unwrap().clone() else { return };
    if app.updating.swap(true, Ordering::SeqCst) || app.quitting.load(Ordering::SeqCst) {
        return;
    }
    std::thread::spawn(move || {
        let say = |text: &str| {
            let _ = proxy.send_event(UserEvent::Status(Status::Preparing(text.to_string())));
        };
        say(&format!("Downloading {}", release.version));
        let next = match update::prepare(&app.home, &release, &|text| say(text)) {
            Ok(next) => next,
            Err(reason) => {
                app.log(&format!("Update failed: {reason}"));
                update::write_state(&app.home, Some(&release), &reason, "update failed");
                app.updating.store(false, Ordering::SeqCst);
                let _ = proxy.send_event(UserEvent::Status(if app.url().is_some() { Status::Running } else { Status::Preparing("Starting".into()) }));
                let _ = proxy.send_event(UserEvent::UpdateFailed(reason));
                return;
            }
        };
        app.log(&format!("Updating from {VERSION} to {}", release.version));
        update::write_state(&app.home, Some(&release), "", "installing");
        app.quitting.store(true, Ordering::SeqCst);
        let _ = proxy.send_event(UserEvent::Status(Status::Preparing(format!("Installing {}", release.version))));
        shutdown(&app);
        #[cfg(unix)]
        platform::release_instance(&app.home);
        if let Err(reason) = update::finish(&app.home, &next) {
            app.log(&format!("Update failed: {reason}"));
            platform::message(&format!("Security Modeler couldn't update: {reason}\n\nStart it again to carry on."), true);
        }
        let _ = proxy.send_event(UserEvent::Exit);
    });
}

/// Stops Ollama through the backend, then ends every process the app started, which frees all
/// the RAM and VRAM they held.
fn shutdown(app: &App) {
    app.log("Quitting");
    if let Some(url) = app.url() {
        server::request_quit(&url, &app.token);
    }
    if let Some(job) = &app.job {
        job.terminate();
    }
    if let Some(mut child) = app.backend.lock().unwrap().take() {
        let _ = child.kill();
        let _ = child.wait();
    }
    let _ = fs::remove_file(app.home.join("launcher.url"));
}

/// Without a desktop: runs in the terminal until Ctrl+C or `SecurityModeler --quit`.
fn run_headless(app: Arc<App>) {
    println!("Security Modeler {VERSION}, made by Akulav");
    println!("Data folder: {}", app.home.display());
    if let Err(reason) = run(&app, &|step| println!("{step}…")) {
        app.log(&format!("Failed: {reason}"));
        eprintln!("Security Modeler couldn't start.\n\n{reason}\n\nThe logs are in {}", app.home.join("logs").display());
        shutdown(&app);
        std::process::exit(1);
    }
    println!("Running at {}. Open it in a browser. Press Ctrl+C to quit.", app.url().unwrap_or_default());

    let (sender, quit_requested) = std::sync::mpsc::channel();
    {
        let home = app.home.clone();
        std::thread::spawn(move || {
            platform::wait_for_quit_request(&home);
            let _ = sender.send(());
        });
    }
    let mut code = 0;
    loop {
        if quit_requested.recv_timeout(Duration::from_secs(1)).is_ok() {
            break;
        }
        let exited = app.backend.lock().unwrap().as_mut().is_none_or(|child| !matches!(child.try_wait(), Ok(None)));
        if exited {
            app.log("The backend stopped unexpectedly");
            eprintln!("The app stopped unexpectedly. The logs are in {}", app.home.join("logs").display());
            code = 1;
            break;
        }
    }
    println!("Quitting…");
    shutdown(&app);
    std::process::exit(code);
}
