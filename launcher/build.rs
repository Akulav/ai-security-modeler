//! Packs the backend and the built frontend into the executable, and gives it its icon.

use sha2::{Digest, Sha256};
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use zip::write::SimpleFileOptions;

fn main() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..");
    let dist = root.join("frontend/dist/index.html");
    if !dist.exists() {
        panic!("The frontend isn't built. Run `npm ci` and `npm run build` in frontend/ first.");
    }

    // Path inside the payload, and where it comes from.
    let mut files: Vec<(String, PathBuf)> = Vec::new();
    collect(&root.join("backend/app"), "backend/app", &mut files);
    collect(&root.join("frontend/dist"), "frontend/dist", &mut files);
    for single in ["backend/requirements.txt", ".env.example", "LICENSE"] {
        files.push((single.to_string(), root.join(single)));
    }
    files.sort();

    let out = PathBuf::from(std::env::var("OUT_DIR").unwrap());
    let mut writer = zip::ZipWriter::new(fs::File::create(out.join("payload.zip")).unwrap());
    let options = SimpleFileOptions::default().compression_method(zip::CompressionMethod::Deflated);
    // Hashed from the contents, so the launcher re-extracts only when the app actually changed.
    let mut hash = Sha256::new();
    for (name, source) in &files {
        let data = fs::read(source).unwrap_or_else(|error| panic!("{}: {error}", source.display()));
        hash.update(name.as_bytes());
        hash.update((data.len() as u64).to_le_bytes());
        hash.update(&data);
        writer.start_file(name.as_str(), options).unwrap();
        writer.write_all(&data).unwrap();
    }
    writer.finish().unwrap();
    let digest: String = hash.finalize().iter().map(|byte| format!("{byte:02x}")).collect();
    println!("cargo:rustc-env=PAYLOAD_HASH={}", &digest[..16]);

    for watched in ["backend/app", "backend/requirements.txt", "frontend/dist", ".env.example", "LICENSE"] {
        println!("cargo:rerun-if-changed={}", root.join(watched).display());
    }
    println!("cargo:rerun-if-changed=assets/icon.ico");

    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("windows") {
        let mut resources = winresource::WindowsResource::new();
        resources
            .set_icon("assets/icon.ico")
            .set("ProductName", "Security Modeler")
            .set("FileDescription", "Security Modeler")
            .set("LegalCopyright", "Made by Akulav");
        resources.compile().expect("Couldn't add the icon. Is the Windows SDK installed?");
    }
}

fn collect(dir: &Path, prefix: &str, files: &mut Vec<(String, PathBuf)>) {
    for entry in fs::read_dir(dir).unwrap_or_else(|error| panic!("{}: {error}", dir.display())) {
        let path = entry.unwrap().path();
        let name = path.file_name().unwrap().to_string_lossy().to_string();
        if name == "__pycache__" || name.ends_with(".pyc") {
            continue;
        }
        let inner = format!("{prefix}/{name}");
        if path.is_dir() {
            collect(&path, &inner, files);
        } else {
            files.push((inner, path));
        }
    }
}
