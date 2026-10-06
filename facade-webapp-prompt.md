# Parametric facade webapp + Archicad (Tapir) — one-shot prompt

Fill in every `[[ ... ]]` block, attach the reference pictures, then paste everything below the line into Claude Code.

---

Here are reference pictures of a facade design: [[ATTACH PICTURES — and/or list file paths, e.g. D:\refs\facade1.jpg ]]

Build a local webapp that is an interactive parametric model of this facade's design logic, and a button that builds the model in the running Archicad through the Tapir add-on.

## 1. The facade (what I see and how I read its logic)

[[ DESCRIBE THE FACADE IN YOUR OWN WORDS. For example:
- Main element families (e.g. vertical fins, horizontal louvres, perforated panels, bricks, frames, glazing).
- How each family is arranged (regular grid, rhythm, random, gradient, rotation, offsets).
- What changes across the facade (density bottom→top, depth, angle, colour, opening size).
- Edges, cuts and boundaries (curved bottom edge, sloped top, openings, corners).
- Context worth showing but not building (glazing, canopy, backing wall, ground floor).
]]

## 2. Parameters I want as sliders / inputs

[[ LIST THEM, grouped. Give units and sensible ranges if you know them. For example:
Facade: length (m), height (m)
Family A: spacing, thickness, depth, rhythm pattern (text like "1 1 2"), jitter %, depth pattern (constant / random / wave)
Family B: row module, thickness, depth, setback, density at bottom %, density at top %, falloff exponent, per-bay variation %
Randomness: seed + "new random pattern" button
Materials: colour per family
]]

Default values: [[ VALUES THAT REPRODUCE THE PICTURE AS CLOSELY AS POSSIBLE — or write "choose them from the pictures" ]]

## 3. How I want to edit things directly

[[ DESCRIBE THE EDITING METHODS. For example:
- Draw or edit cut curves (bottom / top) in a 2D front elevation: drag points, click the curve to add, double-click to delete, freehand draw, Shift to snap, undo.
- Paint a density / attractor mask on the elevation.
- Place attractor points that change depth or rotation.
- Draw opening outlines that remove elements.
]]

## 4. Archicad mapping

[[ FOR EACH ELEMENT FAMILY, THE ARCHICAD ELEMENT TYPE TO USE — or write "choose the best fit". For example:
fins → Columns, horizontals → Beams, panels → Slabs or Morphs, glazing → not built.
Layer names: e.g. "Facade - Fins", "Facade - Horizontals".
Placement: facade along +X from the origin, facing −Y, on the Ground Floor (story 0).
]]

Project folder: [[ e.g. D:\workflow_test\my-facade ]]

---

## Requirements (keep these as they are)

### Webapp
- A plain static site that runs on **localhost** and can later be deployed to Vercel from GitHub with no build step. It is not a claude.ai artifact.
  - A full HTML document: `index.html` plus `generator.js`, plus CSS/JS inline or as separate files.
  - Libraries come from cdnjs or jsdelivr, with pinned versions. Three.js r128 (UMD) plus `examples/js/controls/OrbitControls.js` is a known-good pair.
- **Generator in its own file, `generator.js`.** It holds the pure functions: params + curves → element list. It is loaded by the page and also `require`-able from Node, with no DOM access. The page, the exporter and Archicad must all use exactly the same geometry.
- **Deterministic randomness.** Use a hash per cell (element index, row index, seed) rather than a sequential random number generator. Then changing a density only adds or removes elements and does not reshuffle the whole pattern.
- **Views, switchable as Split / 3D / Front:**
  - **3D view:** orbit controls, shadows, context elements, and "Perspective" and "Front" camera buttons. Use `InstancedMesh` for repeated elements, with `frustumCulled = false`, and re-render on demand.
  - **2D front elevation (Canvas 2D):** for the direct editing in section 3. It needs a metre grid, dimension strings for length and height, pan, zoom at the cursor, a Fit button and a coordinate readout.
- **Parameter panel:**
  - Build it from a schema. Each parameter gets a label, a number field with its unit, and a slider.
  - Group parameters into collapsible sections.
  - Show a small live preview chart wherever a parameter is a curve, e.g. a density profile.
- **Live updates:** any change regenerates the model, coalesced to one update per animation frame.
- **Stats line:** element count per family, total lengths and clad area.
- **Persistence and export:**
  - Settings are kept in `localStorage`, with every access wrapped in try/catch.
  - Export: Copy JSON, Save .json, Import, Reset all.
  - The JSON holds the params, the curves and the full element schedule: positions and sizes of every element, in metres. Axes: x along the facade, y up, z outward.
- **Look and behaviour:**
  - Light and dark theme through CSS tokens.
  - Works at phone width.
  - No `alert` / `confirm`.

### Archicad through Tapir (always)
- **Connection:** Archicad's JSON API is at `http://127.0.0.1:19723`; if that fails, scan ports 19723–19744. The request is `POST {"command":"API.ExecuteAddOnCommand","parameters":{"addOnCommandId":{"commandNamespace":"TapirCommand","commandName":"<Name>"},"addOnCommandParameters":{...}}}`.
- **Before writing any code:**
  - Call `GetAddOnVersion`.
  - Download that exact version's schemas: `https://raw.githubusercontent.com/ENZYME-APD/tapir-archicad-automation/<version>/docs/archicad-addon/command_definitions.js`.
  - Use only commands and fields that exist in that version.
- **Known gotchas:**
  - Element lists are `[{"elementId": {"guid": ...}}]`, with the wrapper.
  - Passing `floorIndex: 0` keeps Z absolute.
  - Column anchors are inconsistent with `TopCenter`. Use `coreAnchor: "Center"` and offset the coordinate by half the depth.
  - Set `isWidthAndHeightLinked: false` when width and depth differ.
  - Tapir cannot create curtain walls. Map to Columns, Beams, Slabs, Walls or Morphs instead.
- **First a test placement:** create one element of each type, read it back with `GetDetailsOfElements` and `API.Get3DBoundingBoxes`, fix the anchors and offsets, then delete the test elements.
- **`archicad/build_facade.py`** (standard-library Python):
  - Expose a `build(model, origin, keep, log)` function.
  - Create elements in batches of about 300.
  - Put each family on its own layer: `CreateLayers`, then `SetDetailsOfElements` with `layerIndex`.
  - Save the created GUIDs to `last_build.json`. Unless `keep` is set, delete the previous build's GUIDs first.
  - CLI: `python build_facade.py --settings file.json [--origin X Y] [--keep]`. It uses Node and `generator.js` to turn the settings into elements.
- **`serve.py` bridge** (Archicad's API sends no CORS headers, so the browser cannot talk to it directly):
  - Serves the site on `http://localhost:8000`.
  - `GET /api/status` returns the Tapir version, or a clear error.
  - `POST /api/build` takes `{elements…, origin, keep, settings}` and calls `build()`. It also saves the settings to `archicad/<name>.json`.
  - Only allow origins on localhost / 127.0.0.1, plus any passed with `--allow-origin https://…vercel.app`. Answer preflight requests with `Access-Control-Allow-Private-Network: true`.
  - Lock so that only one build runs at a time.
- **"Archicad" section in the webapp:**
  - Connection status plus a "Check connection" button.
  - Origin x / y.
  - A **"Keep the previous build"** checkbox, unticked by default, which means replace.
  - A **"Build in Archicad"** button. It is disabled until the connection check passes, and it shows the result, e.g. "Built 42 columns and 207 beams, replaced 249 old elements."
  - On localhost it calls the same origin. Anywhere else it calls `http://127.0.0.1:8000`.
- `.gitignore` the local build state (`facade_model.json`, `last_build.json`, `__pycache__/`).

### Finish and verify
1. Syntax-check the page script with `node --check` and the Python with `py_compile`.
2. Start `python serve.py` in the background and give me the localhost URL.
3. Run one real build through `/api/build` with the default design. Verify the element counts in Archicad with `API.GetElementsByType` and check a few bounding boxes against the model.
4. Tell me what you verified and what you could not. List the Archicad mapping, and how to deploy to Vercel later.
