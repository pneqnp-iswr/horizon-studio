// Register a row under Options > Mods.
fn pixelchat_hud_list(mods: &mut Vec<crate::game::native_hooks::NativeMod>) {
    use crate::game::pixelchat_hud as m;
    mods.push(crate::game::native_hooks::NativeMod {
        id: m::ID.into(),
        title: format!("{} {}", m::NAME, m::VERSION),
        description: m::DESCRIPTION.into(),
        keys: Vec::new(),
    });
}
