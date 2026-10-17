# Vera Quintero — artist showcase

Static one-page site for a fictional painter and vocalist. It lives under `uis/` so Brasaland’s corporate site (`uis/website/`) and staff console stay separate.

Agreed section order, outside in:

1. `header` — name, primary nav (About, Career, Shows), studio link
2. `hero` — statement, short introduction, two studio paintings
3. `about` — story plus where she works and what she is open for
4. `career` — selected years, newest first
5. `shows` — three upcoming rooms, with a way to write the studio
6. `footer` — name, email, the same section links

## Run

From this folder:

```bash
python3 -m http.server 8765
```

Open `http://127.0.0.1:8765/`.

Layout uses Flexbox. Class names follow BEM (`block__element--modifier`). Motion is a short rise on load and a lift on show cards, and it turns off when the visitor prefers reduced motion.

`index.html` links `styles.css`. The two paintings are SVG files with `alt` text. A JSON-LD graph in the head describes Vera as a `Person`, plus the two `VisualArtwork` pieces and the three upcoming events. Fonts are local `.woff2` files, so the page does not call Google Fonts.
