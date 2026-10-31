// /pixelchat toggles the experimental native HUD and persists user choice.
fn pixelchat_hud_command(game: &mut crate::game::Game<'_>, command: &str, ran: &mut bool) {
    use crate::game::pixelchat_hud as m;
    if !game.native_on(m::ID) || command.trim() != "pixelchat" {
        return;
    }
    *ran = true;
    let next = !m::shown(|| game.native_setting(m::ID, "shown"));
    m::set_shown(next);
    game.native_set_setting(m::ID, "shown", if next { "true" } else { "false" });
    game.native_chat(if next { "PixelChat HUD enabled" } else { "PixelChat HUD disabled" });
}
