use std::path::PathBuf;

use excel_id_card_rust::app::MigrationApp;

fn main() -> eframe::Result<()> {
    // Initialize development logging.
    // If RUST_LOG is not explicitly set, default to debug for our crate and info for dependencies,
    // ensuring all user actions and engine pipelines are logged with timestamps in terminal.
    env_logger::Builder::from_env(
        env_logger::Env::default().default_filter_or("excel_id_card_rust=debug,info"),
    )
    .format_timestamp_millis()
    .init();

    log::info!("Starting CardForge application (debug logging active)");
    let project_path = std::env::args_os().nth(1).map(PathBuf::from);
    let options = eframe::NativeOptions {
        viewport: eframe::egui::ViewportBuilder::default()
            .with_title("CardForge — Excel ID Card Generator")
            .with_inner_size([1280.0, 850.0])
            .with_min_inner_size([960.0, 600.0])
            .with_maximized(true),
        ..Default::default()
    };

    eframe::run_native(
        "CardForge — Excel ID Card Generator",
        options,
        Box::new(move |creation_context| {
            Ok(Box::new(MigrationApp::new(
                creation_context,
                project_path.clone(),
            )))
        }),
    )
}
