#[tauri::command]
fn pick_repository_directory() -> Result<Option<String>, String> {
    let directory = rfd::FileDialog::new()
        .set_title("Select repository directory")
        .pick_folder();

    Ok(directory.map(|path| path.to_string_lossy().to_string()))
}

pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![pick_repository_directory])
        .run(tauri::generate_context!())
        .expect("failed to run SWITCH desktop shell");
}
