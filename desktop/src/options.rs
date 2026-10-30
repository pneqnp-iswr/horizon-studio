//! Command-line options. Normal launches take none; CI uses the smoke options to start the
//! real application, wait until the editor reports ready, then exit with a JSON report.

use std::path::PathBuf;
use std::time::Duration;

#[derive(Debug, Clone, PartialEq)]
pub struct Options {
    pub smoke_report: Option<PathBuf>,
    pub smoke_timeout: Duration,
    /// Keep the window open this long after the editor is ready (for screenshots).
    pub smoke_hold: Duration,
    pub window_size: (f64, f64),
}

impl Default for Options {
    fn default() -> Self {
        Options {
            smoke_report: None,
            smoke_timeout: Duration::from_secs(120),
            smoke_hold: Duration::ZERO,
            window_size: (1440.0, 900.0),
        }
    }
}

impl Options {
    pub fn smoke(&self) -> bool {
        self.smoke_report.is_some()
    }

    pub fn parse<I: IntoIterator<Item = String>>(args: I) -> Result<Options, String> {
        let mut options = Options::default();
        let mut args = args.into_iter();
        while let Some(arg) = args.next() {
            let mut value = |flag: &str| args.next().ok_or_else(|| format!("{flag} needs a value"));
            match arg.as_str() {
                "--smoke-report" => options.smoke_report = Some(PathBuf::from(value("--smoke-report")?)),
                "--smoke-timeout" => options.smoke_timeout = seconds(&value("--smoke-timeout")?)?,
                "--smoke-hold" => options.smoke_hold = seconds(&value("--smoke-hold")?)?,
                "--window-size" => options.window_size = size(&value("--window-size")?)?,
                // Ignore anything else (e.g. arguments Windows adds for file associations).
                _ => {}
            }
        }
        Ok(options)
    }
}

fn seconds(text: &str) -> Result<Duration, String> {
    match text.parse::<u64>() {
        Ok(value) if value <= 3600 => Ok(Duration::from_secs(value)),
        _ => Err(format!("Expected seconds (0-3600), got {text}")),
    }
}

fn size(text: &str) -> Result<(f64, f64), String> {
    let (w, h) = text.split_once('x').ok_or_else(|| format!("Expected WIDTHxHEIGHT, got {text}"))?;
    match (w.parse::<u32>(), h.parse::<u32>()) {
        (Ok(w), Ok(h)) if (640..=7680).contains(&w) && (480..=4320).contains(&h) => Ok((w as f64, h as f64)),
        _ => Err(format!("Window size out of range: {text}")),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn parse(args: &[&str]) -> Result<Options, String> {
        Options::parse(args.iter().map(|s| s.to_string()))
    }

    #[test]
    fn defaults_and_smoke_flags() {
        assert_eq!(parse(&[]).unwrap(), Options::default());
        let options = parse(&["--smoke-report", "r.json", "--smoke-hold", "5", "--window-size", "1280x800"]).unwrap();
        assert!(options.smoke());
        assert_eq!(options.smoke_hold, Duration::from_secs(5));
        assert_eq!(options.window_size, (1280.0, 800.0));
    }

    #[test]
    fn rejects_bad_values() {
        assert!(parse(&["--smoke-report"]).is_err());
        assert!(parse(&["--smoke-timeout", "-1"]).is_err());
        assert!(parse(&["--window-size", "100x100"]).is_err());
        assert!(parse(&["--window-size", "wide"]).is_err());
    }
}
