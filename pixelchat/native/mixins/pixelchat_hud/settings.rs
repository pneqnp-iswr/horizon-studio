// Options > Mods > PixelChat HUD > Settings.
fn pixelchat_hud_settings(
    game: &mut crate::game::Game<'_>,
    mod_id: &str,
    buttons: &mut Vec<String>,
) {
    use crate::game::pixelchat_hud as m;
    if mod_id == m::ID {
        buttons.push(m::shown_label(m::shown(|| game.native_setting(m::ID, "shown"))).to_owned());
    }
}
