//! Security Modeler's desktop launcher: sets the app up, runs it in the background, and puts it in
//! the system tray. The app itself is the web page it opens.

#![windows_subsystem = "windows"]

#[cfg_attr(windows, path = "win.rs")]
#[cfg_attr(unix, path = "unix.rs")]
mod platform;
mod server;
mod setup;

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
    // Without a desktop, such as on a server, there's no tray: it runs in the terminal instead.
    let headless = flag("--headless") || !platform::has_desktop();
    let background = flag("--background") || headless;

    if !platform::first_instance(&home) {
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

    let mut tray: Option<TrayIcon> = None;
    let mut menu = Some(menu);
    let mut opened_once = background;
    event_loop.run(move |event, _, control_flow| {
        *control_flow = ControlFlow::Wait;
        match event {
            Event::NewEvents(StartCause::Init) => {
                let icon = tray_icon();
                let mut builder = TrayIconBuilder::new()
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
