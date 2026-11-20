import { cp, mkdir, readFile, writeFile } from 'node:fs/promises';
import { posix } from 'node:path';
import { fileURLToPath } from 'node:url';

const docs = new Map([
  ['docs/README.md', 'index'],
  ['docs/quickstart.md', 'quickstart'],
  ['docs/usage.md', 'usage'],
  ['docs/configuration.md', 'configuration'],
  ['docs/storage-and-recovery.md', 'storage-and-recovery'],
  ['docs/architecture.md', 'architecture'],
  ['docs/methodology.md', 'methodology'],
  ['docs/background-control-plane.md', 'background-control-plane'],
  ['COMMANDS.md', 'cli'],
]);
const repository = new URL('../../', import.meta.url);
const repo = 'https://github.com/maciejgos/harborist/blob/main/';
const base = (process.env.PAGES_BASE ?? '').replace(/\/$/, '');
const output = new URL('../src/content/docs/docs/', import.meta.url);
await mkdir(output, { recursive: true });
await cp(
  fileURLToPath(new URL('docs/diagrams/', repository)),
  fileURLToPath(new URL('diagrams/', output)),
  { recursive: true },
);

for (const [file, slug] of docs) {
  const source = await readFile(new URL(file, repository), 'utf8');
  const [, title] = source.match(/^# (.+)\r?\n/) ?? [];
  if (!title) throw new Error(`Missing title at the start of ${file}`);

  const body = source.replace(/^# .+\r?\n/, '').replace(
    /\]\((?!\/)([^\s():]+\.md)(#[^\s)]*)?\)/g,
    (_, path, anchor = '') => {
      const normalized = posix.join(posix.dirname(file), path);
      const target = docs.get(normalized);
      if (!target) return `](${repo}${normalized}${anchor})`;
      const route = target === 'index' ? '/docs/' : `/docs/${target}/`;
      return `](${base}${route}${anchor})`;
    },
  );

  const editUrl = `https://github.com/maciejgos/harborist/edit/main/${file}`;
  const frontmatter = `title: ${JSON.stringify(title)}\neditUrl: ${JSON.stringify(editUrl)}`;
  await writeFile(new URL(`${slug}.md`, output), `---\n${frontmatter}\n---\n${body}`);
}
