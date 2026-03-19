import { defineConfig } from 'vitepress'

export default defineConfig({
  // Hosted under https://docs.a2w.io/lucas/
  base: '/lucas/',
  title: 'A2W: Lucas',
  description: 'Kubernetes-native agent for pod health checks and hotfixes.',
  lang: 'en-US',
  lastUpdated: true,
  themeConfig: {
    logo: {
      light: '/logo-dark.png',
      dark: '/logo-dark.png'
    },
    nav: [
      { text: 'Guide', link: '/guide/getting-started' },
      { text: 'Current State', link: '/specs/current-platform-state' },
      { text: 'Runtime Settings', link: '/ops/current-runtime-settings' },
      { text: 'Ops', link: '/ops/deployment' },
      { text: 'Specs', link: '/specs/index' }
    ],
    search: {
      provider: 'local'
    },
    sidebar: {
      '/guide/': [
        {
          text: 'Introduction',
          collapsed: false,
          items: [
            { text: 'Getting Started', link: '/guide/getting-started' },
            { text: 'Architecture', link: '/guide/architecture' }
          ]
        },
        {
          text: 'Functionality',
          collapsed: false,
          items: [
            { text: 'Configuration', link: '/guide/configuration' },
            { text: 'Slack Usage', link: '/guide/slack' }
          ]
        },
        {
          text: 'Deployment',
          collapsed: false,
          items: [
            { text: 'Build Images', link: '/guide/build' }
          ]
        }
      ],
      '/ops/': [
        {
          text: 'Deployment',
          collapsed: false,
          items: [
            { text: 'Overview', link: '/ops/deployment' },
            { text: 'ArgoCD', link: '/ops/deployment-argocd' },
            { text: 'Plain YAML', link: '/ops/deployment-yaml' },
            { text: 'CronJob Mode', link: '/ops/cronjob' }
          ]
        },
        {
          text: 'Operations',
          collapsed: false,
          items: [
            { text: 'Dashboard', link: '/ops/dashboard' },
            { text: 'Current Runtime Settings', link: '/ops/current-runtime-settings' },
            { text: 'Docs Hosting', link: '/ops/docs-hosting' },
            { text: 'Operations', link: '/ops/operations' },
            { text: 'Runbooks', link: '/ops/runbooks' },
            { text: 'Troubleshooting', link: '/ops/troubleshooting' }
          ]
        }
      ],
      '/specs/': [
        {
          text: 'Provider Refactor',
          collapsed: false,
          items: [
            { text: 'Overview', link: '/specs/index' },
            { text: 'Current Platform State', link: '/specs/current-platform-state' },
            { text: 'PRD', link: '/specs/prd-provider-agnostic-backend' },
            { text: 'TRD', link: '/specs/trd-provider-agnostic-backend' },
            { text: 'Implementation Plan', link: '/specs/implementation-plan-provider-backends' },
            { text: 'QA and Rollout', link: '/specs/qa-rollout-provider-backends' },
            { text: 'Status-First Reporting', link: '/specs/status-first-reporting' },
            { text: 'Production Transition', link: '/specs/prod-transition' },
            { text: 'Gemini Flash Draft', link: '/specs/gemini-flash-dev-backend' }
          ]
        }
      ]
    },
    footer: {
      message: 'Short docs. Clear actions.',
      copyright: 'A2W: Lucas'
    }
  }
})
