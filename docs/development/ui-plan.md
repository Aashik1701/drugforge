💎 DrugForge 2.0: The "Glass Laboratory" Transformation Plan
Version: 2.0.0
Date: February 15, 2026
Objective: Consolidate the fragmented 22-page MVP into a unified, professional SaaS platform using the "Glass Laboratory" aesthetic.

📋 Executive Summary
The current DrugForge frontend suffers from Route Fragmentation. Users are forced to navigate 9 separate pages to run 9 similar predictions. This redesign consolidates all prediction tools into a single "Lab Bench" interface, reducing user clicks by 80% and creating a cohesive "World-Class Scientific Tool" experience.

Key Metrics:

Total Routes: Reduced from 22+ to 5.

Core Philosophy: "Input Once, Analyze Everything."

Visual Style: Apple-esque Glassmorphism (Translucent, Deep Blur, Airy).

🗺️ New Sitemap & Architecture
1. 🌍 Public Landing Page (Unified)
Route: /
Status: Merges 5 existing pages (Hero, Features, Services, Pricing, Contact).

Header: Floating Glass Navbar (Logo, "Login", "Get Started").

Hero Section: Huge 3D interactive molecule (RDKit) + Value Proposition.

Feature Grid: "Glass Cards" showcasing the 9 models.

Pricing Section: 3 Translucent tiers (Student, Researcher, Enterprise).

Footer: Minimalist links + Contact info.

2. 🏠 The Dashboard (Home)
Route: /app
Purpose: The "Command Center" for the logged-in researcher.

The Omnibox (Hero Element):

A large, centered search bar: "Enter SMILES, Chemical Name, or CID..."

Action: typing here and hitting Enter immediately redirects to /app/analyze with the molecule pre-loaded.

Recent Activity: A masonry layout of "Glass Tiles" showing the last 5 molecules analyzed.

System Status: A small "HUD" widget showing the health of the 9 API models (Green/Red dots).

3. 🧪 The "Lab Bench" (Core Innovation)
Route: /app/analyze
Replaces: /solubility, /toxicity, /bbbp, /cyp3a4, /half-life, /cox2, /hepg2, /ace2, /binding (9 Routes deleted).

Layout: Split-Screen "Glass Cockpit"

Left Panel (The Subject):

Input: Sticky SMILES input field.

Viewer: Large, interactive 3D RDKit viewer floating in space.

Quick Stats: Small floating tags for MW, LogP, TPSA.

Right Panel (The Analysis Modules):

A "Tabbed" Glass Card interface.

Tab 1: ADMET: Runs Solubility, Toxicity, BBB, CYP3A4, Half-life models simultaneously.

Tab 2: Targets: Runs ACE2, COX-2, Binding Score, HepG2 models.

Tab 3: Report: Generates a PDF-ready summary.

UX Magic: User pastes a SMILES once. All active tabs auto-fetch predictions. No more page reloading.

4. ⚗️ Batch Processor
Route: /app/batch
Purpose: High-throughput screening for power users.

UI: A large "Drop Zone" glass panel.

Workflow: Drag CSV → Auto-parse headers → Select Models (Checkboxes) → Run.

Result: A live-updating "Glass Table" (Data Grid) with export options.

5. ⚙️ User Settings
Route: /app/settings
Purpose: Account management.

Profile: Avatar, Name, Email.

Appearance: "Dark Mode" vs "Light Mode" toggle (affects the glass gradients).

API Keys: Manage access to the external API.

🗑️ The Cleanup List (Files to Delete)
Once the new Lab Bench is built, we will aggressively delete the legacy code to reduce technical debt.

Legacy Prediction Pages:

src/components/SolubilityChecker.jsx

src/components/BBBP.jsx

src/components/Toxicity.jsx

src/components/CYP3A4.jsx

src/components/HalfLife.jsx

src/components/COX2.jsx

src/components/HEPG2.jsx

src/components/ACE2.jsx

src/components/BindingScore.jsx

Legacy Public Pages:

src/pages/Features.jsx

src/pages/Services.jsx

src/pages/Pricing.jsx

src/pages/Contact.jsx

Broken/Unused Advanced Tools:

src/components/WorkflowBuilder.jsx

src/components/QSARModeling.jsx

🎨 Design System Specs: "Glass Laboratory"
Color Palette (Tailwind)
Background: Animated Mesh Gradient.

Light: #E0F2FE (Sky) ↔ #F3E8FF (Violet) ↔ #CCFBF1 (Teal).

Dark: #0F172A (Slate) ↔ #1E1B4B (Indigo) ↔ #064E3B (Emerald).

Glass Surface:

bg-white/10 (Light) / bg-black/20 (Dark).

backdrop-blur-xl.

border border-white/20.

shadow-2xl.

Typography
Headings: Inter (Tight tracking, Light/Thin weights).

Data: JetBrains Mono or Fira Code (For SMILES and numerical results).

Interaction
Hover: Glass panes lift (-translate-y-1) and glow (shadow-cyan-500/20).

Loading: Shimmer effects ("Skeleton Loaders") instead of spinners.