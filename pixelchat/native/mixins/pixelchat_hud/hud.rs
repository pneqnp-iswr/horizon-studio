// Proof of a native, pixel-perfect HUD surface. It does NOT replace vanilla chat.
fn pixelchat_hud_overlay(
    game: &mut crate::game::Game<'_>,
    batch: &mut horizon_client::hud::HudBatch,
    corners: &mut horizon_client::extras_hud::Corners,
) {
    use crate::game::pixelchat_hud as m;
    use horizon_client::extras::Corner;

    if !game.native_on(m::ID) || !game.native_corner_shown(Corner::TopRight) {
        return;
    }
    if !m::shown(|| game.native_setting(m::ID, "shown")) {
        return;
    }
    let title = "PIXEL CHAT   /pixelchat";
    let width = game.native_text_width(title).max(132.0) + 12.0;
    let height = 36.0;
    let (x, y) = corners.place(Corner::TopRight, width, height);
    game.native_fill(batch, [x, y, width, height], m::BACKGROUND);
    game.native_text(batch, title, [x + 6.0, y + 4.0], m::WHITE, true);
    let scale = 2.0_f32;
    for icon in 0..m::GLYPHS.len() {
        let base_x = x + 7.0 + icon as f32 * 27.0;
        let base_y = y + 18.0;
        for r in m::runs(icon) {
            game.native_fill(
                batch,
                [
                    base_x + r.x as f32 * scale,
                    base_y + r.y as f32 * scale,
                    r.width as f32 * scale,
                    scale,
                ],
                m::COLORS[icon],
            );
        }
    }
}
