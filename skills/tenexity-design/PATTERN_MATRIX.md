# Pattern Matrix

This matrix helps agents understand which app examples prove which archetypes, modules, and Tenexity primitives. It is intentionally practical rather than exhaustive: update it when a route becomes a canonical example or when an app changes its main pattern.

For a larger menu of existing and candidate application examples, see `docs/APPLICATION_EXAMPLES.md`. Keep this file focused on routed or canonical examples; use the application catalog for broader ideation and future app candidates.

## App Examples

| App / Route | Source | Primary Archetypes | Modules | Key Tenexity Primitives |
| --- | --- | --- | --- | --- |
| Meridian `/app/meridian` | `src/pages/app/Meridian.tsx` | Dashboard, Agent | Search, Notifications, Activity | `AppShell`, `AppActionHeader`, `MeridianPilot`, `MetricCard`, `StatusPill`, `CategoryLabel` |
| Order Entry `/app/order-entry` | `src/pages/app/OrderEntry.tsx` | Processing Queue, Field Mapper, Record Review | Uploads, OCR, Voice Intake, Activity | `AppShell`, `PageHeader`, `ConfidencePill`, `Cascade`, `DataTable`, `VoiceIntake` |
| Counter Sales `/app/counter-sales` | `src/pages/app/CounterSales.tsx` | Counter Sales, Conversation, Catalog | Voice Intake, Search, Activity | `AppShell`, `PageHeader`, `ConfidencePill`, `AISparkle`, `Button` |
| AP Automation `/app/ap-automation` | `src/pages/app/ap/*` | Inbox Monitor, Comparator, Approval Stack, Record Detail | OCR, Doc Viewer, Email, Activity | `AppShell`, `StatusPill`, `ConfidencePill`, `DocumentViewer`, `MetricCard` |
| AR Automation `/app/ar-aging` | `src/pages/app/ar/*` | Worklist, Record Detail, Timeline, Collab | Email, Phone, SMS, Activity | `AppShell`, `AppActionHeader`, `PageHeader`, `StatusPill`, `ConfidencePill`, `Money`, `VerticalTimeline` |
| RFQ and Quoting `/app/rfq` | `src/pages/app/rfq/*` | Processing Queue, Catalog, Comparator, Approval Stack, Diff Review | Email, Search, Rich Text, Activity | `AppShell`, `PageHeader`, `StatusPill`, `ConfidencePill`, `Cascade`, `CrossAppLink` |
| Financial `/app/financial` | `src/pages/app/Financial.tsx` | Dashboard, Pivot, Lineage | Search, Activity | `AppShell`, `MetricCard`, `Money`, `Pct`, `CategoryLabel` |
| Inventory `/app/inventory` | `src/pages/app/Inventory.tsx` plus `inventory/*` | Dashboard, Worklist, Catalog, Capacity Planner | Barcode, Maps, Activity | `AppShell`, `PageHeader`, `MetricCard`, `StatusPill`, `DataTable` |
| Pricing `/app/pricing` | `src/pages/app/Pricing.tsx` plus `pricing/*` | Dashboard, Rule Builder, Approval Stack, Simulator | Activity, Search | `AppShell`, `MetricCard`, `StatusPill`, `Money`, `Pct` |
| Cost Management `/app/cost` | `src/pages/app/CostManagement.tsx` plus `cost/*` | Worklist, Negotiation Tape, Pivot | Activity, Search | `AppShell`, `PageHeader`, `MetricCard`, `StatusPill`, `Money` |
| Vendor Portal `/app/vendor-portal` | `src/pages/app/VendorPortal.tsx` plus `vendor-portal/*` | Ontology, Scorecard, Swimlane Timeline | Email, Doc Viewer, Activity | `AppShell`, `PageHeader`, `StatusPill`, `MetricCard`, `Avatar` |
| Customer BU `/app/customer-bu` | `src/pages/app/CustomerBU.tsx` plus `customer-bu/*` | Ontology, Pivot, Scorecard | Activity, Search | `AppShell`, `MetricCard`, `Money`, `Pct`, `StatusPill` |
| Employee `/app/employee` | `src/pages/app/Employee.tsx` plus `employee/*` | Dashboard, Kanban, Tree Table | Comments, Activity | `AppShell`, `PageHeader`, `Avatar`, `StatusPill`, `MetricCard` |
| Tenexity Chat `/app/chat` | `src/pages/app/Chat.tsx` | Conversation, Catalog | Voice Intake, Search, Uploads | `AppShell`, `CategoryLabel`, `Button`, `AISparkle`, `Avatar` |
| Conversation Lab `/app/librechat` | `src/pages/app/LibreChat.tsx` plus `librechat/*` | Comparator, Spreadsheet, Scorecard | Search, Activity | `AppShell`, `MetricCard`, `StatusPill`, `DataTable`, `ConfidencePill` |
| Learning `/app/lms` | `src/pages/app/LMS.tsx` plus `lms/*` | Catalog, Record Detail, Progress Dashboard | Video Preview, Activity | `AppShell`, `PageHeader`, `MetricCard`, `StatusPill`, `Button` |
| Product Configurator `/app/product-configurator` | `src/pages/app/ProductConfigurator.tsx` plus `product-configurator/*` | Configurator, Rule Builder, Catalog | Search, Activity | `AppShell`, `PageHeader`, `StatusPill`, `CategoryLabel`, `Button` |
| Wiki `/app/wiki` | `src/pages/app/Wiki.tsx` | Catalog, Record Editor, Tree Table | Rich Text, Search, Comments | `AppShell`, `PageHeader`, `CategoryLabel`, `RichTextEditor`, `Button` |
| Project Hub `/app/projects` | `src/pages/app/Projects.tsx` | Kanban, Calendar, Detail | Comments, Activity | `AppShell`, `PageHeader`, `Avatar`, `StatusPill`, `MetricCard` |
| OKRs `/app/okrs` | `src/pages/app/OKRs.tsx` | Scorecard, Tree Table | Activity | `AppShell`, `PageHeader`, `MetricCard`, `Avatar`, `CategoryLabel` |
| Meetings `/app/meetings` | `src/pages/app/Meetings.tsx` | Calendar, Record Detail, Action List | Dictation, Activity, Video Preview | `AppShell`, `PageHeader`, `MetricCard`, `Avatar`, `AISparkle` |
| Forms `/app/forms` | `src/pages/app/Forms.tsx` | Catalog, Processing Queue, Configurator | Uploads, Signature, Activity | `AppShell`, `PageHeader`, `StatusPill`, `MetricCard`, `Button` |
| Help Desk `/app/helpdesk` | `src/pages/app/Helpdesk.tsx` | Worklist, Record Detail, Inbox Monitor | Comments, Email, Activity | `AppShell`, `PageHeader`, `StatusPill`, `Avatar`, `MetricCard` |
| Integrations Hub `/app/integrations` | `src/pages/app/Integrations.tsx` | Health Monitor, Catalog, Audit Journal | Notifications, Activity | `AppShell`, `PageHeader`, `MetricCard`, `StatusPill`, `CategoryLabel` |
| PRD-backed Common Framework apps `/app/<app-id>` | `src/pages/app/blueprint/*` | Worklist, Dashboard, Agent, Data Model | Activity, Search, Audit, Notifications | `AppShell`, `AppActionHeader`, `PageHeader`, `MetricCard`, `StatusPill`, `ConfidencePill`, `Button` |
| Master Data `/app/master-data` | `src/pages/app/master-data/*` | Ontology, Catalog, Record Detail, Audit Journal | Search, Activity | `AppShell`, `PageHeader`, `DataTable`, `StatusPill`, `Money` |
| Control Room `/app/control-room` | `src/pages/app/control-room/ControlRoom.tsx` | Health Monitor, Audit Journal, Inbox Monitor | Notifications, Activity | `AppShell`, `MetricCard`, `StatusPill`, `DataTable`, `AISparkle` |
| Changelog `/app/changelog` | `src/pages/app/changelog/Changelog.tsx` | Audit Journal, Timeline | Notifications, Activity | `AppShell`, `StatusPill`, `Avatar`, `CategoryLabel`, `Button` |
| Roadmap `/app/roadmap` | `src/pages/app/roadmap/Roadmap.tsx` | Kanban, Decision Tree, Audit Journal | Comments, Activity | `AppShell`, `StatusPill`, `Avatar`, `CategoryLabel`, `Button` |
| Status `/app/status` and `/status` | `src/pages/status/*` | Health Monitor, Incident Timeline | Notifications | `StatusPill`, `MetricSpark`, `UptimeGrid`, `IncidentCard`, `CategoryLabel` |

## Archetype Library

Canonical archetype documentation lives in `src/pages/docs/archetypes/*` and renders through `src/components/docs/ArchetypeContract.tsx`.

| Archetype | Route | Canonical Page |
| --- | --- | --- |
| Record Editor | `/archetypes/library/record-editor` | `RecordEditorArchetype.tsx` |
| Configurator | `/archetypes/library/configurator` | `ConfiguratorArchetype.tsx` |
| Collab | `/archetypes/library/collab` | `CollabArchetype.tsx` |
| Inbox Monitor | `/archetypes/library/inbox-monitor` | `InboxMonitorArchetype.tsx` |
| Lineage | `/archetypes/library/lineage` | `LineageArchetype.tsx` |
| Ontology | `/archetypes/library/ontology` | `OntologyArchetype.tsx` |
| Comparator | `/archetypes/library/comparator` | `ComparatorArchetype.tsx` |
| Catalog | `/archetypes/library/catalog` | `CatalogArchetype.tsx` |
| Calendar | `/archetypes/library/calendar` | `CalendarArchetype.tsx` |
| Agent | `/archetypes/library/agent` | `AgentArchetype.tsx` |
| Field Mapper | `/archetypes/library/field-mapper` | `FieldMapperArchetype.tsx` |
| Processing Queue | `/archetypes/library/processing-queue` | `ProcessingQueueArchetype.tsx` |
| Doc Generator | `/archetypes/library/doc-generator` | `DocGeneratorArchetype.tsx` |
| Funnel | `/archetypes/library/funnel` | `FunnelArchetype.tsx` |
| Heatmap | `/archetypes/library/heatmap` | `HeatmapArchetype.tsx` |
| Kanban | `/archetypes/library/kanban` | `KanbanArchetype.tsx` |
| Pivot | `/archetypes/library/pivot` | `PivotArchetype.tsx` |
| Spreadsheet | `/archetypes/library/spreadsheet` | `SpreadsheetArchetype.tsx` |
| Swimlane Timeline | `/archetypes/library/swimlane-timeline` | `SwimlaneTimelineArchetype.tsx` |
| Tree Table | `/archetypes/library/tree-table` | `TreeTableArchetype.tsx` |
| Map | `/archetypes/library/map` | `MapArchetype.tsx` |
| Diff Reviewer | `/archetypes/library/diff-reviewer` | `DiffReviewerArchetype.tsx` |
| Decision Tree | `/archetypes/library/decision-tree` | `DecisionTreeArchetype.tsx` |
| Scorecard | `/archetypes/library/scorecard` | `ScorecardArchetype.tsx` |
| Rule Builder | `/archetypes/library/rule-builder` | `RuleBuilderArchetype.tsx` |
| Approval Stack | `/archetypes/library/approval-stack` | `ApprovalStackArchetype.tsx` |
| Reconciliation | `/archetypes/library/reconciliation` | `ReconciliationArchetype.tsx` |
| Simulator | `/archetypes/library/simulator` | `SimulatorArchetype.tsx` |
| Notification Inbox | `/archetypes/library/notification-inbox` | `NotificationInboxArchetype.tsx` |
| Audit Journal | `/archetypes/library/audit-journal` | `AuditJournalArchetype.tsx` |
| Capacity Planner | `/archetypes/library/capacity-planner` | `CapacityPlannerArchetype.tsx` |
| Negotiation Tape | `/archetypes/library/negotiation-tape` | `NegotiationTapeArchetype.tsx` |
| Health Monitor | `/archetypes/library/health-monitor` | `HealthMonitorArchetype.tsx` |
| Cohort Analyzer | `/archetypes/library/cohort-analyzer` | `CohortAnalyzerArchetype.tsx` |
| Counter Sales | `/archetypes/library/counter-sales` | `CounterSalesArchetype.tsx` |

## Cross-Cutting Modules

Canonical module documentation lives in `src/pages/docs/modules/*` and renders through `src/components/docs/ModuleContract.tsx`.

| Module | Route | Primitive / Surface |
| --- | --- | --- |
| Email | `/modules/email` | `EmailComposer` |
| Notifications | `/modules/notifications` | `NotificationCenter`, `NotificationToast` |
| SMS | `/modules/sms` | `SMSThread` |
| Phone | `/modules/phone` | Phone/call workflow components |
| Maps | `/modules/maps` | `Map` |
| Barcode | `/modules/barcode` | Barcode workflow pattern |
| Uploads | `/modules/uploads` | `FileDropzone` |
| Doc Viewer | `/modules/doc-viewer` | `DocumentViewer` |
| OCR | `/modules/ocr` | OCR review pattern |
| Print | `/modules/print` | Print/export workflow pattern |
| Signature | `/modules/signature` | Signature workflow pattern |
| Comments | `/modules/comments` | `CommentThread`, `Composer` |
| Activity | `/modules/activity` | `ActivityFeed`, timeline primitives |
| Search | `/modules/search` | `SearchSuggest`, command palette |
| Rich Text | `/modules/rich-text` | `RichTextEditor` |
| Shortcuts | `/modules/shortcuts` | `ShortcutOverlay`, `Kbd` |
| Dictation | `/modules/dictation` | `useDictation`, `MicButton`, `DictationField` |
| Voice Intake | `/modules/voice-intake` | `voice-intake.tsx` |

## Matrix Maintenance Rules

- Add a row when a live app route becomes a meaningful reference implementation.
- Update an app row when the route switches its primary archetype.
- Add broader candidate examples to `docs/APPLICATION_EXAMPLES.md` before promoting them into this canonical matrix.
- Keep modules in this matrix limited to cross-cutting capabilities that an agent should consider reusing.
- PRD-backed blueprint routes count as routed examples only when they expose command, work, data, and agent sections with scenario-specific records and fake-but-working state changes.
