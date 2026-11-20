# Harborist website

Run `npm ci` and `npm run dev` in this directory to preview the landing page and documentation. Run `npm run build` to generate the static site in `dist/`.

Edit the public guides in the repository's `docs/` directory and the CLI reference
in `COMMANDS.md`. The build prepares the pages listed in
`scripts/prepare-docs.mjs`, including the overview from `docs/README.md`.
Restart the dev server after editing Markdown so it picks up the changes.

## Cloudflare Pages hosting

The [Harborist Pages project](https://harborist.pages.dev/) builds the static
site from GitHub. It reads the landing page from `website/` and renders the
Markdown guides from `docs/` and `COMMANDS.md`.

| Setting | Value |
| --- | --- |
| Git repository | `maciejgos/harborist` |
| Production branch | `codex/website-and-docs` until the website is merged into `main` |
| Root directory | Repository root |
| Build command | `npm ci --prefix website && npm run build --prefix website` |
| Build output directory | `website/dist` |
| Build watch paths | `website/**`, `docs/**`, `COMMANDS.md` |
| Node version | `NODE_VERSION=24` |
| Site origin | `PAGES_ORIGIN=https://harborist.pages.dev` |

Cloudflare automatically builds matching pushes to the production branch.
After connecting a custom domain in the Pages dashboard, update
`PAGES_ORIGIN` to its HTTPS origin and redeploy. Leave `PAGES_BASE` unset
to serve the site at the root URL.

## GitHub Pages

For GitHub Pages hosting, set the repository's Pages source to **GitHub
Actions**. Pull requests build the site for review. Relevant pushes to
`main` rebuild and deploy it.
