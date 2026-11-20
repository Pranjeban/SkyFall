# v0.9.2 Table-Based UI Reconstruction (read-only)

## Sources
- `main_window_v070.bak.py` (v0.7.0 snapshot, 1780 lines) — sole snapshot with QTableWidget tables.
- `backup_v07/main_window.py` (v0.6.0, 1427 lines) — uses QListWidget, no QTableWidget.
- `backup_v05/main_window.py` (v0.4.0, 949 lines) — no tables.
- `releases/v0.9.2/README_SKYFALL_V0_9_2.md` (70 lines).
- `app/desktop/main_window.py` (current, 3358 lines) — for comparison.

## v0.9.2 README UI claims
- Slate palette; chat canvas/message contrast (`README:18`).
- Independently scrollable nav; floating assistant + local session controls anchored; session card visible (`README:19`).
- Local conversation deletion + tightened selection after deletion (`README:20`).
- PP settings around saved Microsoft accounts + persistent env selection; choosing account no longer routes through Manage (`README:21`).
- Empty draft conversations omitted from sidebar history until first message sent (`README:35`).
- Kiro-inspired rounded shell, lavender surround, graphite/plum surface, searchable session list, eased wheel scrolling, slim scrollbars (README later sections).
- Diagnostics: stable codes, permission/not-found/throttling guidance; pagination only HTTPS on expected host.

## Tables in v0.7.0 snapshot

### 1. azure_subscriptions_table (QTableWidget, 6 cols)
- Location: `main_window_v070.bak.py:990-993`, headers `["Account profile", "Subscription", "Subscription ID", "Tenant ID", "State", "Default"]`.
- Purpose: accessible Azure subscriptions per selected profile.
- Style: `_style_data_table` (lines 1080-1093): alternating rows, no edit, row selection single, stretch columns, slate palette `#101A2D`/`#142139`.
- Population: `_on_microsoft_discovery_completed` action=="azure" (lines 1215-1221): `setRowCount(len(rows))`, items via QTableWidgetItem. Values: profile, name, subscription_id, tenant_id, state, "Yes" if is_default.
- Status labels: azure_status_label, azure_tenant_label (lines 976-986).
- Current (v1.0.1): identical headers (app/desktop/main_window.py:1381-1384). Same styling but palette `#211D27`/`#28242E`.

### 2. pp_profiles_table (QTableWidget, 6 cols)
- v0.7.0: lines 1053-1056, headers `["Index", "Active", "Kind", "Profile", "Environment URL", "User"]`. MaxHeight 210.
- Purpose: registered PAC CLI profiles.
- Population: lines 1240-1246 from profiles.get("profiles").
- Current: headers changed to `["Authentication", "Selected", "Tenant ID", "Profile", "Last Environment ID", "User"]` (app/desktop/main_window.py:1553-1556). Reflects v0.9.2 shift from PAC CLI to saved Microsoft accounts with persisted env selection per profile. New columns: Tenant ID, Last Environment ID; dropped Index/Active/Kind/Environment URL.

### 3. pp_environments_table (QTableWidget, 6/7 cols)
- v0.7.0: lines 1062-1065, headers `["Environment", "Type", "Environment ID", "URL", "Organization ID", "Region"]`.
- Population: lines 1247-1254.
- Current: 7 cols `["Environment", "Type", "Environment ID", "URL", "Organization ID", "Region", "Tenant ID"]` (app/desktop/main_window.py:1562-1565). Added Tenant ID.

### 4. azure_inventory_table (current only, 8 cols)
- app/desktop/main_window.py:1451-1454: `["Profile", "Subscription", "Resource Group", "Function App", "Runtime", "Plan SKU", "Region", "State"]`.
- Purpose: Function App inventory preview (up to 100). New in current; not in v0.7.0. Populated lines 2130-2145.

### 5. pp_flow_table (current only, 5 cols)
- app/desktop/main_window.py:1734-1737: `["Flow name", "Status", "Type", "Owner", "Last modified"]`.
- Purpose: cloud flow preview with empty state card (lines 1715-1732). Hidden until data; toggled. New in current.

## v0.6.0 / v0.4.0
- No QTableWidget. Used QListWidget for history_list (line 447), workspace_list (644), workspace_results_list (683). Single selection. v0.4 likely similar. Table-based UI introduced in v0.7.0.

## Search/filter
- v0.7.0: workspace_search_input (QLineEdit) at line 685, returnPressed → _search_workspace_index (891), calls workspace_manager.search_local. No conversation search filter in v0.7.0 (grep shows none for history).
- Current: history_search_input (line 782) with textChanged → _filter_conversation_list (3255) hiding QListWidget items whose text doesn't contain needle. Plus workspace_search_input (1079) and exec_search_input (2452). Empty draft conversations omitted from sidebar (README).

## Sorting
- No QSortFilterProxyModel or setSortingEnabled in any snapshot/current. Tables are plain QTableWidget with manual population. No column sorting implemented.

## Row-level actions
- No context menus or double-click handlers on tables in v0.7.0 (grep: no cellDoubleClicked/contextMenu). Selection mode single. Tables are read-only display. Buttons around tables (Refresh profiles, Discover environments, etc.) trigger workers.
- Current: pp_profile_combo (QComboBox) change → _on_powerplatform_profile_changed; pp_resource_environment_combo change → _on_powerplatform_environment_changed. Delete chat button enabled based on history_list count.

## Loading states
- v0.7.0: status labels (azure_status_label, pp_status_label, workspace_status_label) text updates; worker.completed/failed signals. No spinners. Empty tables show 0 rows.
- Current: azure_inventory_status_label, pp_flow_status_label, pp_flow_empty_state card with title/message; pp_flow_table hidden until data; retry button. Metric cards.

## Persistence
- v0.7.0: azure profile combo currentData restored via _refresh_azure_profile_choices (findData). No column width persistence (stretch mode). No scroll/selection persistence beyond combo.
- Current: env selection persists per PP profile (README: "environment selection persists per Power Platform profile", "Last Environment ID" column). Conversation selection restored via _restore_history_selection. History search re-applied after refresh (line 3252-3253).

## Relationships
- Azure page: profile combo → subscriptions table + tenant label. PP page: profile combo → pp_profiles_table + pp_environments_table. Resources page: env combo → flow table + metrics. Tables are read-only mirrors of worker payloads.

## Regressions/changes noted
- v0.7.0 → current: PAC CLI profiles replaced by saved Microsoft accounts (columns changed). Added azure_inventory_table and pp_flow_table (new capabilities). Palette changed from navy `#101A2D` to graphite `#211D27`. Conversation search/filter and deletion added (v0.9.2). Empty-state card for flows. Persisted env selection per profile. No sorting anywhere (unchanged). No context menus (unchanged).
- v0.6.0/v0.4.0 had no tables at all — table UI is a v0.7.0+ feature.
- Potential regression: v0.7.0 pp_profiles_table showed "Index/Active/Kind" which aided PAC profile management; current dropped these in favor of account/auth status. Whether selection persistence of column widths/scroll exists: not in any snapshot (stretch mode always).
