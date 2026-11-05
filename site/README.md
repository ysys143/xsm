# XSM replay and documentation site

[Live demo](https://ysys143.github.io/xsm/) · [Live documentation](https://ysys143.github.io/xsm/#guide/start)

[Design brief](../docs/design/xsm-demo/spec.md) · [Implementation record](../docs/design/xsm-demo/implementation.md) · [Terminal and English revision](../docs/design/xsm-demo/terminal-en-revision.md)

## Run locally

From the repository root:

```sh
node site/serve.mjs
```

Open the local URL printed in the terminal. No package installation or build step is required. To choose a port, use `node site/serve.mjs 4173`. Stop the preview with Ctrl+C. Verification uses Node.js 24.19.0.

## Replay and guides

- Four chapters show team setup, direct worker collaboration, Fable maintaining the plan, and coordination between independent teams.
- Eight guides cover setup, roles, DMs, boards, plans and progress, multiple teams, handover, and runtime support. The same player moves between the replay and the matching guide.
- Pause is preserved when navigating between scenes and guides. Reduced motion starts with a complete, readable still.
- Narrow screens offer Lead, Workers and Board panels. Use arrow keys, Home and End to select a panel. A full text transcript is also available.
- Session panes use monospace output, runtime-specific MCP calls, tool results and incoming XSM message headers. Output follows the end of the log unless the reader scrolls back.
- The board is a CLI/Markdown output excerpt. It does not imply a separate XSM dashboard or automatic progress estimation.
- Copyable requests include a manual-copy dialog when the Clipboard API is unavailable or denied.

The interface, replay, guides and accessibility labels support English and Korean. Selection follows an explicit `?lang=en` or `?lang=ko` URL, then a saved manual choice, then the browser's first supported preferred language. Other languages fall back to English. The header language picker saves its choice locally and preserves the current chapter, time and pause state. Runtime identifiers, command names and machine-generated protocol output retain their native spelling.

Header navigation stays in English in both locales: How it works, Docs, GitHub and Get started. This also applies to the mobile menu. The static translator respects `translate="no"` regions.

The conversations are scripted examples with abbreviated output, not live model calls or newly created XSM sessions. Claude Code and Codex appear in the main replay. Pi, OpenCode, Hermes and OpenClaw are listed with their experimental 0.6.0 support described in the runtime guide.

Scene and guide state can be linked directly:

```text
#demo/progress
#demo/teams?focus=board
#guide/start
#guide/progress?section=progress-1
```

Assets use relative paths so the site can be hosted in a subdirectory.

## Verify

```sh
node --test site/tests/player.test.mjs site/tests/site.test.mjs
node --test site/tests/i18n.test.mjs
node site/tests/red-pause.mjs
```

The second command deliberately removes the pause guard in a temporary copy and checks that the tests reject the regression. It never changes the working source.

For browser verification, provide an owned ego-browser task-space ID:

```sh
node site/tests/verify.mjs --space <space-id> --output deliverables/xsm-i18n-20261105/verified
```

The verifier starts and closes its own local server. It exercises the actual site in Chromium and in fixed-width same-origin frames at 320px, 390px, 900px and 1440px. It also emulates Korean browser language preferences and checks both locales, saved choices, query overrides, state preservation, localized copy requests and layout. Clipboard requests and rejection are checked at the API boundary without changing the OS clipboard. Output, screenshots and input hashes are retained in the selected output directory.

## Static hosting

Keep `index.html`, `styles.css`, `app.mjs`, `player.mjs`, `content.mjs`, `content.ko.mjs`, `i18n.mjs`, `favicon.svg` and `assets/` in the same relative structure. Serve `.mjs` files with a JavaScript MIME type. `serve.mjs` and `tests/` are for local development and verification.

GitHub Pages deployment is managed by [pages.yml](../.github/workflows/pages.yml). A push to `main` that changes `site/` or the workflow runs the Node checks, packages the static assets, and deploys them. The workflow can also be started manually. Development tools and tests are excluded from the published artifact.

Archivo is self-hosted. Its source and SHA-256 are in [fonts.json](assets/fonts.json); the license is [Archivo-OFL.txt](assets/Archivo-OFL.txt).
