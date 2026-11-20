# Harborist website

Run `npm ci` and `npm run dev` in this directory to preview the landing page and documentation. Run `npm run build` to generate the static site in `dist/`.

Edit the public guides in the repository's `docs/` directory and the CLI reference
in `COMMANDS.md`. The build prepares the pages listed in
`scripts/prepare-docs.mjs`, including the overview from `docs/README.md`.
Restart the dev server after editing Markdown so it picks up the changes.

## Cloudflare Workers hosting

The Worker serves the static output using `website/wrangler.jsonc`. In
Cloudflare Workers Builds, connect `maciejgos/harborist` and use the website
branch (`codex/website-and-docs`) while the site lives there. Select `main`
after the website is merged.

Use the repository root as the build directory so Astro can read
`docs/` and `COMMANDS.md`. Configure these settings:

| Setting | Value |
| --- | --- |
| Worker name | `harborist` |
| Build command | `npm ci --prefix website && npm run build --prefix website` |
| Deploy command | `npx --yes wrangler@4.165.0 deploy --config website/wrangler.jsonc` |
| Build watch paths | `website/**`, `docs/**`, `COMMANDS.md` |
| Node version | `NODE_VERSION=24` |
| Site origin | `PAGES_ORIGIN` set to the Worker URL, then updated to the custom origin after it is connected |

The site is served at the root URL. Leave `PAGES_BASE` unset for Cloudflare.

## GitHub Pages

For GitHub Pages hosting, set the repository's Pages source to **GitHub
Actions**. Pull requests build the site for review. Relevant pushes to
`main` rebuild and deploy it.
