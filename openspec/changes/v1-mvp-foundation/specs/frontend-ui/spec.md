## ADDED Requirements

### Requirement: Single-page application layout
The frontend SHALL be a single HTML page that integrates all functionality: device information display, connection test, VLAN data table, and operation forms. The page SHALL use Bootstrap CDN for styling and be served by Nginx.

#### Scenario: Page loads correctly
- **WHEN** user accesses the frontend URL in a browser
- **THEN** the page renders with device info section, VLAN table, and action buttons visible

### Requirement: Device information display
The frontend SHALL display the current device configuration (name, host, port, username) and provide a "Test Connection" button. Password SHALL NOT be displayed.

#### Scenario: Device info shown when configured
- **WHEN** the page loads and a device is configured
- **THEN** device name, host, port, and username are displayed

#### Scenario: No device configured
- **WHEN** the page loads and no device is configured
- **THEN** a prompt to add device information is shown

#### Scenario: Connection test button
- **WHEN** user clicks "Test Connection" button
- **THEN** a request is sent to POST /api/device/test and the result (success/failure with message) is displayed on the page

### Requirement: VLAN data table
The frontend SHALL display VLAN data in a table with columns: VLAN ID, VLAN Name, and Actions (Edit, Delete). The table SHALL be populated by fetching GET /api/vlans.

#### Scenario: VLAN table populated
- **WHEN** the page loads and VLANs exist on the device
- **THEN** the table shows all VLANs with their ID, name, and action buttons

#### Scenario: Empty VLAN list
- **WHEN** the page loads and no VLANs are returned
- **THEN** the table shows an empty state message "暂无VLAN数据"

#### Scenario: VLAN list refresh
- **WHEN** user clicks a refresh button or after a VLAN operation completes
- **THEN** the VLAN table is re-fetched and updated

### Requirement: VLAN creation form
The frontend SHALL provide a modal/dialog form for creating a new VLAN with fields: VLAN ID (number input, 1-4094) and VLAN Name (text input). The form SHALL validate inputs before submission.

#### Scenario: Open creation form
- **WHEN** user clicks "Add VLAN" button
- **THEN** a modal appears with VLAN ID and Name input fields

#### Scenario: Submit valid VLAN creation
- **WHEN** user fills in VLAN ID 100 and Name "Office" and clicks submit
- **THEN** POST /api/vlans is called, the modal closes, and the VLAN table refreshes

#### Scenario: Submit invalid VLAN ID
- **WHEN** user enters VLAN ID 5000 or a non-numeric value
- **THEN** the form shows an inline validation error and does not submit

#### Scenario: Creation fails with error
- **WHEN** the API returns `{success: false, error: "VLAN 100已存在"}`
- **THEN** the error message is displayed in the global error area and the modal stays open

### Requirement: VLAN edit form
The frontend SHALL provide a modal/dialog form for editing an existing VLAN's name. The VLAN ID SHALL be displayed but not editable.

#### Scenario: Open edit form
- **WHEN** user clicks the Edit button on a VLAN row
- **THEN** a modal appears with VLAN ID (read-only) and Name (editable) fields pre-filled

#### Scenario: Submit valid VLAN edit
- **WHEN** user changes the name and clicks submit
- **THEN** PUT /api/vlans/{vlan_id} is called, the modal closes, and the VLAN table refreshes

### Requirement: VLAN deletion with confirmation
The frontend SHALL prompt the user for confirmation before deleting a VLAN. The confirmation SHALL display the VLAN ID being deleted.

#### Scenario: Confirm deletion
- **WHEN** user clicks the Delete button on VLAN 100
- **THEN** a confirmation dialog appears asking "确认删除VLAN 100？"

#### Scenario: Deletion confirmed
- **WHEN** user confirms the deletion
- **THEN** DELETE /api/vlans/100 is called and the VLAN table refreshes

#### Scenario: Deletion cancelled
- **WHEN** user cancels the confirmation
- **THEN** no API call is made and the VLAN table remains unchanged

### Requirement: Global error display
The frontend SHALL display API errors in a visible error area at the top of the page with red text. The error SHALL auto-dismiss after 5 seconds or be manually dismissible.

#### Scenario: Error displayed on API failure
- **WHEN** any API call returns `{success: false, error: "message"}`
- **THEN** the error message appears in the error area with red styling

#### Scenario: Error auto-dismisses
- **WHEN** an error message has been displayed for 5 seconds
- **THEN** the error message is automatically removed

### Requirement: Loading state
The frontend SHALL show a loading indicator during API calls and disable action buttons to prevent duplicate submissions.

#### Scenario: Loading during VLAN fetch
- **WHEN** the page is fetching VLAN data
- **THEN** a loading spinner is shown in the VLAN table area and the refresh button is disabled

#### Scenario: Loading during VLAN operation
- **WHEN** a create/edit/delete operation is in progress
- **THEN** the submit button shows loading state and is disabled until the operation completes
