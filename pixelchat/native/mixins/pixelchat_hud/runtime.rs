// Original PixelChat HUD: pure pixel geometry and transient in-game visibility.
// This source is also compiled as a standalone Cargo library for unit tests.
// No game files, assets, chat messages, authentication or network hooks are modified.

pub const ID: &str = "pixelchat_hud";
pub const NAME: &str = "PixelChat HUD";
pub const VERSION: &str = "0.1.0";
pub const DESCRIPTION: &str = "Original pixel-art emoji HUD proof. /pixelchat toggles; multiplayer GIF is not supported.";
pub const BACKGROUND: u32 = 0xB0_10_19_2B;
pub const WHITE: u32 = 0xFF_EC_F4_FF;
pub const COLORS: [u32; 4] = [0xFF_FF_75_9C, 0xFF_FF_E1_80, 0xFF_80_E7_C0, 0xFF_8D_BB_FF];
pub const NAMES: [&str; 4] = ["heart", "star", "smile", "spark"];

// Five 5-bit rows; bit 4 is the leftmost pixel.
// The shapes are intentionally original and ship as code, not Minecraft assets.
pub const GLYPHS: [[u8; 5]; 4] = [
    [0b01010, 0b11111, 0b11111, 0b01110, 0b00100],
    [0b00100, 0b10101, 0b01110, 0b11111, 0b10101],
    [0b00000, 0b01010, 0b00000, 0b10001, 0b01110],
    [0b00100, 0b01110, 0b11111, 0b01110, 0b00100],
];

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct PixelRun {
    pub x: u8,
    pub y: u8,
    pub width: u8,
}

/// Merge consecutive set pixels of the same row to reduce native HUD draw calls.
pub fn runs(icon: usize) -> Vec<PixelRun> {
    let Some(rows) = GLYPHS.get(icon) else {
        return Vec::new();
    };
    let mut out = Vec::with_capacity(20);
    for (y, row) in rows.iter().copied().enumerate() {
        let mut x = 0_u8;
        while x < 5 {
            if row & (1 << (4 - x)) == 0 {
                x += 1;
                continue;
            }
            let first = x;
            while x < 5 && row & (1 << (4 - x)) != 0 {
                x += 1;
            }
            out.push(PixelRun { x: first, y: y as u8, width: x - first });
        }
    }
    out
}

pub fn count_pixels(icon: usize) -> usize {
    GLYPHS.get(icon).map_or(0, |rows| rows.iter().map(|r| r.count_ones() as usize).sum())
}

pub fn read_shown(value: Option<String>) -> bool {
    value.is_none_or(|text| text.trim() != "false")
}

pub fn shown_label(visible: bool) -> &'static str {
    if visible { "Emoji preview: ON" } else { "Emoji preview: OFF" }
}

thread_local! {
    static SHOWN: std::cell::Cell<Option<bool>> = const { std::cell::Cell::new(None) };
}

pub fn shown(get: impl FnOnce() -> Option<String>) -> bool {
    SHOWN.with(|cell| {
        let visible = cell.get().unwrap_or_else(|| read_shown(get()));
        cell.set(Some(visible));
        visible
    })
}

pub fn set_shown(visible: bool) {
    SHOWN.with(|cell| cell.set(Some(visible)));
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn icons_are_bounded_nonempty_and_have_no_unused_bits() {
        for (icon, rows) in GLYPHS.iter().enumerate() {
            assert!(count_pixels(icon) > 0);
            for row in rows {
                assert_eq!(row & !0b11111, 0);
            }
        }
        assert!(runs(900).is_empty());
    }

    #[test]
    fn runs_cover_exactly_the_original_pixels() {
        for icon in 0..GLYPHS.len() {
            let run_list = runs(icon);
            assert!(run_list.len() <= count_pixels(icon));
            let mut pixels = [[false; 5]; 5];
            for run in run_list {
                assert!((run.x as usize) < 5 && (run.y as usize) < 5);
                assert!(run.width > 0 && run.x + run.width <= 5);
                for x in run.x..run.x + run.width {
                    assert!(!pixels[run.y as usize][x as usize], "overlapping rectangles");
                    pixels[run.y as usize][x as usize] = true;
                }
            }
            for (y, row) in pixels.iter().enumerate() {
                for (x, painted) in row.iter().enumerate() {
                    assert_eq!(*painted, GLYPHS[icon][y] & (1 << (4 - x)) != 0);
                }
            }
        }
    }

    #[test]
    fn pixel_art_matches_documented_five_by_five_pack() {
        assert_eq!(NAMES, ["heart", "star", "smile", "spark"]);
        assert_eq!(count_pixels(0), 16);
        assert_eq!(count_pixels(2), 7);
    }

    #[test]
    fn reads_and_formats_visibility() {
        assert!(read_shown(None));
        assert!(read_shown(Some("true".into())));
        assert!(!read_shown(Some("false\n".into())));
        assert_eq!(shown_label(true), "Emoji preview: ON");
        assert_eq!(shown_label(false), "Emoji preview: OFF");
    }

    #[test]
    fn visibility_can_be_toggled_deterministically() {
        set_shown(false);
        assert!(!shown(|| Some("true".into())));
        set_shown(true);
        assert!(shown(|| Some("false".into())));
    }
}
