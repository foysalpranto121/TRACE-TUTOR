---
name: TRACE Tutor
colors:
  surface: '#0b1326'
  surface-dim: '#0b1326'
  surface-bright: '#31394d'
  surface-container-lowest: '#060e20'
  surface-container-low: '#131b2e'
  surface-container: '#171f33'
  surface-container-high: '#222a3d'
  surface-container-highest: '#2d3449'
  on-surface: '#dae2fd'
  on-surface-variant: '#bcc9cd'
  inverse-surface: '#dae2fd'
  inverse-on-surface: '#283044'
  outline: '#869397'
  outline-variant: '#3d494c'
  surface-tint: '#4cd7f6'
  primary: '#4cd7f6'
  on-primary: '#003640'
  primary-container: '#06b6d4'
  on-primary-container: '#00424f'
  inverse-primary: '#00687a'
  secondary: '#c0c1ff'
  on-secondary: '#1000a9'
  secondary-container: '#3131c0'
  on-secondary-container: '#b0b2ff'
  tertiary: '#bcc7de'
  on-tertiary: '#263143'
  tertiary-container: '#9ca7be'
  on-tertiary-container: '#313c4f'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#acedff'
  primary-fixed-dim: '#4cd7f6'
  on-primary-fixed: '#001f26'
  on-primary-fixed-variant: '#004e5c'
  secondary-fixed: '#e1e0ff'
  secondary-fixed-dim: '#c0c1ff'
  on-secondary-fixed: '#07006c'
  on-secondary-fixed-variant: '#2f2ebe'
  tertiary-fixed: '#d8e3fb'
  tertiary-fixed-dim: '#bcc7de'
  on-tertiary-fixed: '#111c2d'
  on-tertiary-fixed-variant: '#3c475a'
  background: '#0b1326'
  on-background: '#dae2fd'
  surface-variant: '#2d3449'
typography:
  headline-xl:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.01em
  headline-md:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '500'
    lineHeight: 28px
    letterSpacing: -0.01em
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-sm:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
  code-md:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 20px
  code-sm:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  label-md:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.02em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 1rem
  margin: 1.5rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2rem
---

## Brand & Style

TRACE Tutor is a research-oriented AI coding tutor for university programming education. The brand personality is scholarly, cutting-edge, reliable, and precise, evoking the focused environment of advanced computer science laboratories. 

The visual style embraces a high-end developer-tool aesthetic inspired by Linear, Vercel, and GitHub. It relies on a dark-mode-first paradigm characterized by deep charcoal and slate backgrounds, restrained cyan and indigo lighting accents, fine low-contrast borders, and absolute typographic clarity. The interface communicates technical competence and removes visual noise to keep students immersed in complex algorithmic problem-solving.

## Colors

The palette establishes a deep nocturnal baseline using charcoal (#0F172A) for the foundational canvas and slate (#1E293B) for elevated surfaces and interactive containers. 

The primary accent is a luminous cyan (#06B6D4), reserved for primary actions, active states, and code syntax highlights. The secondary accent is a rich indigo (#6366F1), applied to secondary actions, AI assistant highlights, and badge backgrounds. Text utilizes high-contrast white (#F8FAFC) for primary reading and muted slate-gray (#94A3B8) for secondary metadata. Semantic indicators rely on precise tokens: success green, amber warning, and crisp red error.

## Typography

Typography prioritizes extreme legibility for code-heavy reading environments. Interface text uses Inter, providing a neutral, systematic, and utilitarian framework. Code blocks, terminal outputs, and inline variables use JetBrains Mono for strict character alignment and unmistakable syntax differentiation. 

On mobile viewports, scale down headline sizes proportionally (e.g., `headline-xl` drops to 24px) to prevent wrapping anomalies within compact code review panels.

## Layout & Spacing

The layout is structured on an 8px grid system, ensuring mathematical harmony across complex split-pane interfaces (code editor, AI chat, test runner). 

The application uses a fluid 12-column grid for dashboard views and a fixed-header, multi-column workspace layout for the core IDE environment. Margins and gutters scale down to 12px on mobile devices, collapsing secondary navigation drawers into slide-over panels while keeping the primary code editing canvas fully accessible.

## Elevation & Depth

Depth is achieved primarily through low-contrast outlines ("ghost borders") rather than heavy shadows, adhering to the precision aesthetic of modern developer tooling. 

Surfaces stack subtly using tonal layering: the foundational canvas sits at deep charcoal (#0F172A), cards and panels occupy slate (#1E293B), and floating popovers or active modals use lighter slate tiers with ultra-subtle, diffused ambient shadows tinted in black (e.g., `0 4px 20px -2px rgba(0, 0, 0, 0.5)`). Borders use a 1px stroke of muted slate (#334155) to delineate interactive boundaries cleanly.

## Shapes

The design system employs a soft shape language (`roundedness` level 1), favoring precise, understated geometry over bubbly or aggressive forms. 

Inputs, buttons, and badges use a 0.25rem border-radius (`rounded-sm`), while major cards, modal containers, and code editor windows use 0.5rem (`rounded-lg`). This restraint maintains a clean, professional interface suitable for academic computer science research.

## Components

### Buttons
Primary buttons feature a solid cyan background (#06B6D4) with dark slate text for maximum contrast, shifting to a brighter cyan hue on hover. Secondary buttons use transparent backgrounds with subtle slate borders and white text. Ghost variants remove the border entirely, revealing a slate background only on hover.

### Chips & Badges
Compact pill or rounded-sm indicators used for file extensions, difficulty ratings, and test status. They feature low-opacity background tints matching their semantic color (e.g., transparent green for passed tests, transparent amber for warnings).

### Input Fields & Code Editors
Inputs feature a deep slate background, 1px slate-700 borders, and cyan focus rings. Code editor containers integrate seamlessly with the background, utilizing gutter line-number styling in muted gray and subtle active-line highlights.

### Cards & Containers
Contained surfaces use the slate-800 background color, bounded by a 1px low-contrast border. They house discrete blocks of evaluation data, AI feedback summaries, or assignment instructions.

### Checkboxes & Radio Buttons
Built with crisp 1px borders, adopting the cyan accent color and a clean white checkmark or dot when selected.

### Additional Components: Terminal / Output Console
A dedicated mono-font component styled like a classic IDE terminal, featuring instantaneous log streaming, collapsible stack traces, and color-coded stdout/stderr indicators.