import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

export default defineConfig({
  site: process.env.PAGES_ORIGIN || 'http://localhost:4321',
  base: process.env.PAGES_BASE || '/',
  integrations: [
    starlight({
      title: 'Harborist',
      favicon: '/harborist-mark.png',
      social: [{ icon: 'github', label: 'GitHub', href: 'https://github.com/maciejgos/harborist' }],
      customCss: ['./src/styles/docs.css'],
      editLink: { baseUrl: 'https://github.com/maciejgos/harborist/edit/main/' },
      sidebar: [
        {
          label: 'Get started',
          items: [{ label: 'Overview', slug: 'docs' }, { label: 'Quickstart', slug: 'docs/quickstart' }],
        },
        {
          label: 'Guides',
          items: ['docs/usage', 'docs/configuration', 'docs/background-control-plane'],
        },
        {
          label: 'Reference',
          items: ['docs/architecture', 'docs/methodology', 'docs/storage-and-recovery', 'docs/cli'],
        },
      ],
    }),
  ],
});
