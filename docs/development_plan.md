# Development Plan

## Milestone 1: Read-Only Model

- Parse cached device list, DSK presence, login metadata, and maker parts.
- Keep all secret material out of logs, fixtures, tests, and commits.
- Expose a safe summary tool for development.

Status: complete.

## Milestone 2: Cloud API Probe

- Use cached token/domain metadata to test read-only API calls.
- Identify required request signing and headers.
- Fetch device list and maker parts without using desktop app cache.

Status: in progress.

## Milestone 3: MQTT Read-Only

- Connect to the correct regional MQTT broker.
- Subscribe to device status, reply, and notice topics.
- Decode status payloads into typed Python models.

Status: complete for first E1/EU live test; keep compatibility checks open.

## Milestone 4: Home Assistant Custom Integration

- Replace coordinator stub with live client data.
- Add stable read-only sensors for availability, print status, progress,
  firmware, ink levels, waste ink, and service parts.
- Keep control services out until read-only status is stable.

Status: in progress. A first custom integration package exists and uses
read-only MQTT status plus setup-export based configuration.

## Milestone 5: HACS Candidate

- Add release packaging, HACS metadata, screenshots, and user installation docs.
- Test on a clean Home Assistant instance.

Status: in progress. HACS metadata and release packaging exist; clean Home
Assistant runtime testing is still required.

## Milestone 6: Official Integration Candidate

- Extract `pyeufymake` to a standalone package.
- Add Home Assistant integration tests and fixtures.
- Meet Home Assistant Bronze quality requirements.
- Submit a small read-only core PR first.

Status: pending.
