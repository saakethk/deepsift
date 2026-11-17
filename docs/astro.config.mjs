// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

export default defineConfig({
  site: 'https://saakethk.github.io',
  base: '/deepsift',
  integrations: [
    starlight({
      title: 'DeepSift',
      description: 'High-performance Python library for researchers to scrape and curate historical Reddit data at large scale',
      social: [
        {
          icon: 'github',
          label: 'GitHub',
          href: 'https://github.com/saakethk/deepsift',
        },
      ],
      sidebar: [
        {
          label: 'Getting Started',
          items: [
            { label: 'Overview', slug: 'index' },
            { label: 'Architecture & Pipeline', slug: 'architecture' },
            { label: 'Quickstart Guide', slug: 'quickstart' },
          ],
        },
        {
          label: 'Reference',
          items: [
            { label: 'Python API Reference', slug: 'api' },
            { label: 'CLI Reference', slug: 'cli' },
            { label: 'Benchmarks & Scaling', slug: 'benchmarks' },
          ],
        },
      ],
    }),
  ],
});
