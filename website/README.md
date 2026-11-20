# Harborist website

Run `npm ci` and `npm run dev` in this directory to preview the landing page and documentation. Run `npm run build` to generate the static site in `dist/`.

Edit the public guides in the repository's `docs/` directory and the CLI reference
in `COMMANDS.md`. The build prepares the pages listed in
`scripts/prepare-docs.mjs`, including the overview from `docs/README.md`.
Restart the dev server after editing Markdown so it picks up the changes.

Set the repository's GitHub Pages source to **GitHub Actions** to enable deployment. Pull requests build the site for review. Relevant pushes to `main` rebuild and deploy it.
