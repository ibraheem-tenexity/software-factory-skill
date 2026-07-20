// recipedata.jsx — Recipes data. A recipe is a reusable build blueprint the
// internal Tenexity team curates: a customer-facing summary of what it produces,
// plus internal build assets (linked GitHub repos + image artifacts) that seed
// the factory. The customer only ever sees the light, customer-facing fields
// (name / tagline / category / "what you get"); the repos, images and internal
// notes stay OS-side. Each recipe's description is registered into the artifact
// registry (type 'md') so operators can open it in the Artifact Viewer.
// Shared by recipes.jsx (the OS editor + the customer picker) and ArtifactViewer.html.

const RECIPE_CATEGORIES = ['Sales & Quoting', 'Integrations', 'Inventory', 'Customer', 'Finance', 'Operations'];

const RECIPES = [
  {
    id: 'recipe-quote-erp',
    name: 'Quote-to-ERP Automation',
    tagline: 'Build quotes against live ERP pricing and write won quotes back as orders.',
    category: 'Sales & Quoting',
    status: 'published',
    builds: 12, updated: '2h ago', owner: 'TENDER',
    // customer-facing
    includes: ['Line-item quote builder', 'Tiered & contract pricing', 'Discount-approval gate', 'ERP order write-back', 'Manager pipeline view'],
    systems: ['Epicor', 'SAP B1', 'NetSuite'],
    // internal build assets (never shown to the customer)
    repos: [
      { name: 'tenexity/quote-erp-core', url: 'github.com/tenexity/quote-erp-core', desc: 'Quote builder + pricing engine reference implementation' },
      { name: 'tenexity/erp-connectors', url: 'github.com/tenexity/erp-connectors', desc: 'Epicor / SAP / NetSuite order write-back adapters' },
    ],
    images: [
      { name: 'quote-builder.png', note: 'Reference quote-builder screen' },
      { name: 'approval-queue.png', note: 'Manager discount-approval queue' },
      { name: 'architecture.png', note: 'System architecture diagram' },
    ],
    content: `# Recipe — Quote-to-ERP Automation

A reusable blueprint for pricing-and-quoting projects that terminate in an ERP order.

## What it produces
- A line-item **quote builder** that searches live ERP SKUs and prices against the standard book.
- Tiered + contract pricing with margin rules.
- A **discount-approval gate** (default > 15%) routing to a manager queue.
- **Order write-back** into the connected ERP once a quote is won.

## Build assets
- Seeds from \`quote-erp-core\` (builder + pricing) and \`erp-connectors\` (write-back adapters).
- Ships with reference screen designs and an architecture diagram.

## Good fit when
The customer re-keys quotes into their ERP by hand and wants a pricing-approval workflow.
`,
  },
  {
    id: 'recipe-edi',
    name: 'EDI Trading-Partner Gateway',
    tagline: 'Stand up resilient X12 mappings with acknowledgements and an exception queue.',
    category: 'Integrations',
    status: 'published',
    builds: 7, updated: '1d ago', owner: 'LEDGER',
    includes: ['850 / 855 / 856 / 810 mappings', '997 acknowledgements', 'Operator exception queue', 'Partner onboarding flow'],
    systems: ['SPS Commerce', 'TrueCommerce', 'Epicor'],
    repos: [
      { name: 'tenexity/edi-gateway', url: 'github.com/tenexity/edi-gateway', desc: 'X12 parser, mapping engine, ack generation' },
      { name: 'tenexity/edi-exception-tool', url: 'github.com/tenexity/edi-exception-tool', desc: 'Operator review + replay UI' },
    ],
    images: [
      { name: 'exception-queue.png', note: 'Operator exception-review screen' },
      { name: 'mapping-editor.png', note: 'Segment mapping editor' },
    ],
    content: `# Recipe — EDI Trading-Partner Gateway

Clear a trading-partner EDI backlog and stand up durable X12 document flows.

## What it produces
- Inbound/outbound mappings for **850, 855, 856, 810** and **997** acknowledgements.
- An **exception queue** so no segment is ever silently dropped — everything is queued and replayable.
- A repeatable partner-onboarding flow.

## Build assets
- Seeds from \`edi-gateway\` (mapping engine) and \`edi-exception-tool\` (operator UI).

## Good fit when
The customer has a growing document backlog and partner specs that keep drifting.
`,
  },
  {
    id: 'recipe-inventory',
    name: 'Inventory Sync & Reorder',
    tagline: 'Keep stock counts live across systems and automate reorder points.',
    category: 'Inventory',
    status: 'published',
    builds: 4, updated: '3d ago', owner: 'CARGO',
    includes: ['Multi-location stock view', 'Reorder-point automation', 'Cycle-count workflow', 'Low-stock alerts'],
    systems: ['Epicor', 'Fishbowl', 'ShipStation'],
    repos: [
      { name: 'tenexity/inventory-core', url: 'github.com/tenexity/inventory-core', desc: 'Stock ledger + reorder engine' },
    ],
    images: [
      { name: 'stock-board.png', note: 'Multi-location stock board' },
    ],
    content: `# Recipe — Inventory Sync & Reorder

A blueprint for real-time stock visibility and automated replenishment.

## What it produces
- A **multi-location stock board** synced from the ERP/WMS.
- **Reorder-point automation** with configurable safety stock.
- A cycle-count workflow and low-stock alerts.

## Good fit when
Stock counts live in more than one system and reorders are managed on a spreadsheet.
`,
  },
  {
    id: 'recipe-portal',
    name: 'Customer Self-Service Portal',
    tagline: 'Give customers accounts, order history, reorders and document access.',
    category: 'Customer',
    status: 'published',
    builds: 5, updated: '5d ago', owner: 'TENDER',
    includes: ['Customer accounts & auth', 'Order history & reorder', 'Invoice / document access', 'Support requests'],
    systems: ['Epicor', 'Stripe', 'Auth0'],
    repos: [
      { name: 'tenexity/portal-shell', url: 'github.com/tenexity/portal-shell', desc: 'Auth + account + order-history shell' },
    ],
    images: [
      { name: 'portal-home.png', note: 'Customer portal home' },
      { name: 'reorder-flow.png', note: 'One-click reorder flow' },
    ],
    content: `# Recipe — Customer Self-Service Portal

A member/customer portal that offloads routine requests from the sales desk.

## What it produces
- Customer **accounts** with household/company linking.
- **Order history** with one-click reorder.
- Invoice + document access and a lightweight support inbox.

## Good fit when
The sales team fields repetitive "where's my order / can I reorder" calls.
`,
  },
  {
    id: 'recipe-apar',
    name: 'AP / AR Automation',
    tagline: 'Automate invoice capture, matching and approval routing.',
    category: 'Finance',
    status: 'draft',
    builds: 0, updated: '1w ago', owner: 'MATRIX',
    includes: ['Invoice capture (OCR)', '3-way match', 'Approval routing', 'ERP posting'],
    systems: ['Epicor', 'Bill.com'],
    repos: [
      { name: 'tenexity/apar-core', url: 'github.com/tenexity/apar-core', desc: 'Capture + matching engine (WIP)' },
    ],
    images: [],
    content: `# Recipe — AP / AR Automation  *(draft)*

Blueprint for accounts-payable / receivable automation. **Not yet published** — repos and
screen designs are still being finalized.

## Intended output
- OCR invoice capture, 3-way match against POs/receipts, approval routing, and ERP posting.
`,
  },
];

const RECIPE_STATUS = {
  draft: { label: 'Draft', tone: 'neutral' },
  published: { label: 'Published', tone: 'success' },
  archived: { label: 'Archived', tone: 'neutral' },
};

// Register every recipe description into the shared artifact registry.
if (typeof registerArtifacts === 'function') {
  const map = {};
  RECIPES.forEach((r) => { map[r.id] = { id: r.id, name: r.id + '.md', type: 'md', node: r.category, agent: 'Proposal Lead · ' + r.owner, project: 'Recipes', updated: r.updated, content: r.content }; });
  registerArtifacts(map);
}

Object.assign(window, { RECIPES, RECIPE_STATUS, RECIPE_CATEGORIES });
