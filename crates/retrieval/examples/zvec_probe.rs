use std::{env, process::ExitCode};

use domain::BuildId;
use retrieval::ZvecRetriever;

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("{error}");
            ExitCode::FAILURE
        }
    }
}

fn run() -> Result<(), String> {
    let path = env::args()
        .nth(1)
        .ok_or_else(|| "usage: zvec_probe <vectors-path> <build-id>".to_string())?;
    let build_id = env::args()
        .nth(2)
        .ok_or_else(|| "usage: zvec_probe <vectors-path> <build-id>".to_string())?;
    println!("open {path}");
    let retriever = ZvecRetriever::open(path, &BuildId(build_id))?;
    println!("build_id={}", retriever.build_id().0);
    Ok(())
}
