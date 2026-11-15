# Incident Response Playbook: WhatsApp AI Platform

**Single Organization Edition:** Physio One Clinic  
**Severity Levels:** P0 (Critical / Outage / Uncontrolled Send), P1 (Degraded / Service Impact), P2 (Minor / Internal), P3 (Cosmetic).

---

## 1. Emergency Kill Switches (Immediate Mitigation)

If an automated messaging loop, hallucination, or unintended outbound sending occurs:

### 1.1 Global Outbound Kill Switch
Deactivates ALL automated scheduled follow-ups, appointment reminders, and inactivity check-ins clinic-wide immediately.

- **Via Dashboard:** Navigate to `Automations` -> Toggle `Outbound Sending` to **Disabled**.
- **Via SQL CLI:**
  ```sql
  UPDATE automation_settings SET outbound_enabled = false, updated_at = NOW();
  ```
- **Via API (Owner/Admin only):**
  ```bash
  curl -X PATCH "https://api.physioone.in/api/v1/automations/settings" \
    -H "Cookie: session_id=${ADMIN_SESSION_TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{"outbound_enabled": false}'
  ```

### 1.2 Deepti AI Inbound Receptionist Kill Switch
Disables autonomous AI responses on WhatsApp. Incoming messages remain queued in the database and visible in Live Inbox for human receptionist takeover.

- **Via Dashboard:** Navigate to `Inbox` -> AI Settings -> Set AI Mode to **Disabled** (or **Shadow Mode**).
- **Via SQL CLI:**
  ```sql
  UPDATE ai_inbound_settings SET ai_mode = 'disabled', updated_at = NOW();
  ```

### 1.3 Campaign Manager Emergency Pause
Pauses any running Instagram re-engagement or promotional campaign immediately:

- **Via Dashboard:** Navigate to `Campaigns` -> Click **Pause Campaign** on active campaigns.
- **Via SQL CLI:**
  ```sql
  UPDATE campaigns SET status = 'paused', updated_at = NOW() WHERE status = 'running';
  ```

---

## 2. Playbook A: WhatsApp Outbound Message Storm / Runaway Loop

**Symptoms:** Alert triggers on excessive outbound messages per minute; patients reporting repeated messages.

**Immediate Action (0–2 mins):**
1. Engage **Global Outbound Kill Switch** (Section 1.1) and **AI Inbound Kill Switch** (Section 1.2).
2. Stop the Cloud Run worker service or pause the Cloud Tasks outbound queue:
   ```bash
   gcloud tasks queues pause physio-outbound-queue --location asia-south1
   ```
3. Purge queued outbound tasks:
   ```bash
   gcloud tasks queues purge physio-outbound-queue --location asia-south1
   ```

**Root Cause Investigation (2–15 mins):**
1. Inspect `automation_execution_logs` and `whatsapp_messages` for identical `conversation_id` or `idempotency_key`:
   ```sql
   SELECT conversation_id, COUNT(*) 
   FROM whatsapp_messages 
   WHERE created_at > NOW() - INTERVAL '15 minutes' AND direction = 'outbound'
   GROUP BY conversation_id 
   HAVING COUNT(*) > 3;
   ```
2. Verify idempotency table: `outbound_idempotency_keys`. Check if database transaction rollbacks allowed duplicate attempts.

---

## 3. Playbook B: Meta Cloud API Webhook Failure / Provider Outage

**Symptoms:** Webhook delivery success rate drops below 95%; Meta Developer Dashboard flags webhook failure warnings.

**Immediate Action (0–5 mins):**
1. Check Cloud Run API service health:
   ```bash
   curl -I https://api.physioone.in/health
   ```
2. Verify Meta Webhook Verification Token & App Secret:
   - Check if Meta rotated the secret or access token.
   - Test HMAC signature computation with test payload.
3. If Cloud Run is undergoing restart or scaling issues, inspect container logs:
   ```bash
   gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=physio-one-api AND severity>=WARNING" --limit 50
   ```

---

## 4. Playbook C: Patient Safety / Medical Escalation Trigger

**Symptoms:** Patient reports acute neurological deficits, cardiac chest pain, severe trauma, or asks for emergency triage.

**Expected Automation Behavior:**
- Deepti AI safety filter detects medical emergency keywords (e.g., "chest pain", "short of breath", "unconscious", "numbness in arm", "stroke").
- Automatic human takeover is activated (`Conversation.is_human_takeover = true`).
- AI automated responses are strictly suppressed.
- Standard emergency advisory message is presented: *"If this is a medical emergency, please call 112 or visit the nearest emergency department immediately."*
- Desktop alert badge is surfaced in the Live Inbox for immediate clinician triage.

---

## 5. Playbook D: Legacy n8n / YCloud Conflict During Cutover

**Symptoms:** Patient receives duplicate re-engagement messages from both old n8n workflow and new Campaign Manager.

**Immediate Action:**
1. Execute emergency rollback of cutover state machine:
   ```bash
   curl -X POST "https://api.physioone.in/api/v1/campaigns/legacy-migration/cutover" \
     -H "Cookie: session_id=${ADMIN_SESSION_TOKEN}" \
     -H "Content-Type: application/json" \
     -d '{"target_state": "rolled_back", "notes": "Emergency rollback due to dual delivery"}'
   ```
2. In `rolled_back` state, the new campaign engine is hard-blocked from dispatching messages, allowing legacy n8n to operate until reconciliation is complete.
