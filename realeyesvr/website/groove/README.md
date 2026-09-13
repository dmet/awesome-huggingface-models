# Groove visual prototype

Open `index.html` in a modern browser. No installation or server is required.

The lamp starts with four choices: Upload track, Style, Storyboard, and Motion. Its shaded canvas metaballs drift, cross, merge, and separate automatically. The photographic scene and preview artwork come from the reference image. This is an organic motion approximation, not a 3D fluid simulation.

## JSON menus

Click **Load menu JSON** below the lamp to import a menu. `menu.json` contains the default configuration and can be copied and edited. Importing is local to the current page; reloading restores the default. The startup configuration is embedded in the `lamp-menu` application/json script in `index.html`, so double-clicking the HTML works without a server. To permanently change startup, replace that script's JSON with your configuration.

Example:

```json
{
  "name": "My studio",
  "children": [
    { "id": "music", "name": "Music", "color": "amber", "action": { "type": "upload" } },
    { "id": "worlds", "name": "Worlds", "color": "pink", "children": [
      { "name": "Desert", "action": { "type": "style", "value": "Desert" } },
      { "id": "custom-world", "name": "My world" }
    ] },
    { "name": "Help", "color": "purple", "action": { "type": "dialog", "text": "Choose a song and a visual direction." } }
  ]
}
```

Groups accept 1–8 buttons, with up to eight nested levels and 200 total nodes. Five or more choices use a two-column grid, and wax size adjusts with the count. For larger menus, organize choices into child groups. Names are limited to 40 characters. Colors are `amber`, `pink`, `purple`, or `coral`; omitted colors are assigned from the Groove palette within each group, reserving explicit sibling colors first and cycling the palette after all four colors are used. A button can contain either `children` or an `action`.

Supported actions:

- `upload`: opens the audio picker.
- `style`: selects a `value` of Desert, Dreamlike, Neon, or Cinematic.
- `motion`: sets motion using a boolean `value`.
- `dialog`: displays the button name and supplied `text` as plain text.
- `event`: emits a bubbling `groove:select` event with `detail.id` and `detail.name`. This is also the default when an action is omitted. Connect custom product behavior to this event in JavaScript.

Applications can replace the menu with `window.GrooveLamp.setMenu(objectOrJsonString)`. Invalid input throws before replacing the current menu. JSON supplies data, never executable code. File imports are limited to 100 KB and show validation errors without replacing the working menu.

Back, Escape, or double-clicking empty liquid returns one level to the parent group. Double-clicking buttons does not trigger this back gesture; touch users can use Back. Pointer activity steadies choices for 2.4 seconds; actual keyboard navigation keeps focused choices steady. Programmatic focus after clicking a submenu does not indefinitely pause motion. A parked mouse does not stop idle movement indefinitely. Pause and reduced-motion preferences remain supported. The effects boundary is feathered into the lamp glass.

Audio playback, style selection, motion selection, queue removal, and style filtering work locally. Storyboard choices show scene suggestions. There is no backend, persistence, scene editor, or video generation.

Validation: JavaScript syntax, default configuration, 1/4/6/8-choice menus, and invalid configuration rejection were checked. Browser visual verification and hosted deployment have not been completed.

The scene now uses `assets/lamp-liquid.png`, a clean background edited with the built-in image_gen tool. Original baked-in wax and queue blobs were removed while preserving the glass, room, and small bubbles. The original `reference.png` remains available for the unchanged preview card crops. The exact image-edit prompt is recorded in `assets/lamp-liquid.prompt.txt`.

Both effects layers have transparent backgrounds: CSS bubbles rise behind the canvas metaballs, over the clean photographic liquid. The bubbles in the background image itself are static; CSS supplies the additional moving bubbles. The feathered vessel mask remains in place. Pause motion stops both wax and CSS bubble/heat animations. The generated plate was visually inspected, and its dimensions match the original; browser compositing has not been visually verified.

Wax movement now covers more of the vessel. Collision boundaries follow the same eight-sided glass outline as the feathered mask, with distances corrected for the canvas aspect ratio. Soft rebounds retain tangential movement so blobs slide along the glass; temporary compression follows the contact normal and relaxes after impact. Pointer/keyboard settling, pause, and reduced motion remain in place. Three-minute numerical simulations of 1/2/4/8 blobs stayed within the wall constraints, with repeated wall contacts for the multi-blob cases. Browser appearance has not been visually verified for this change.
