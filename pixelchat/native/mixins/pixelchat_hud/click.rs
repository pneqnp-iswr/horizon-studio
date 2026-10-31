// Settings button callback; same persisted choice as /pixelchat.
fn pixelchat_hud_settings_click(
    game: &mut crate::game::Game<'_>,
    mod_id: &str,
    button: usize,
) {
    use crate::game::pixelchat_hud as m;
    if mod_id != m::ID || button != 0 {
        return;
    }
    let next = !m::shown(|| game.native_setting(m::ID, "shown"));
    m::set_shown(next);
    game.native_set_setting(m::ID, "shown", if next { "true" } else { "false" });
}
