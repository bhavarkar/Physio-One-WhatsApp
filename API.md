# API SPECIFICATION: WhatsApp AI Agent (Single Organization Edition)

## 1. Global API Standards
- **Base URL**: `/api/v1`
- **Protocol**: HTTPS / JSON
- **Authentication**: JWT Bearer token in secure `Authorization: Bearer <token>` header or HTTP-only `access_token` cookie.
- **Error Format**:
  ```json
  {
    "error": {
      "code": "VALIDATION_ERROR",
      "message": "Appointments cannot be scheduled on Sundays. Physio One is closed.",
      "details": { "field": "start_time", "weekday": "Sunday" }
    }
  }
  ```

---

## 2. API Endpoints by Subsystem

### A. Authentication & User Management
| Method | Endpoint | Description | Role Required |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/auth/setup-status` | Check if initial clinic Owner has been created | Public |
| `POST` | `/api/v1/auth/setup` | One-time setup: initialize master Owner account | Public (Blocked once initialized) |
| `POST` | `/api/v1/auth/login` | Authenticate staff user, issue HttpOnly `session_id` & `csrf_token` cookies | Public |
| `POST` | `/api/v1/auth/logout` | Revoke current session and clear auth cookies | Authenticated |
| `GET` | `/api/v1/auth/me` | Return profile and role of current authenticated staff user | Authenticated |
| `GET` | `/api/v1/auth/sessions` | List all active sessions for current user | Authenticated |
| `POST` | `/api/v1/auth/sessions/{id}/revoke` | Revoke a specific active session | Authenticated |
| `POST` | `/api/v1/auth/sessions/revoke-all` | Revoke all sessions except current one | Authenticated |
| `POST` | `/api/v1/auth/change-password` | Update user password with optional multi-session revocation | Authenticated |
| `GET` | `/api/v1/users` | List staff users with pagination and search | `Owner`, `Admin` |
| `POST` | `/api/v1/users` | Provision a new staff user account (Admins cannot create Owners) | `Owner`, `Admin` |
| `GET` | `/api/v1/users/{id}` | Retrieve profile and role details of a specific user | `Owner`, `Admin` |
| `PUT` | `/api/v1/users/{id}` | Update staff user details (Protected against last Owner demotion) | `Owner`, `Admin` |
| `DELETE` | `/api/v1/users/{id}` | Deactivate staff user and terminate all active sessions | `Owner`, `Admin` |
| `POST` | `/api/v1/users/{id}/revoke-sessions` | Force terminate all active sessions for a staff member | `Owner`, `Admin` |
| `GET` | `/api/v1/users/roles` | List all available system roles and permissions | `Owner`, `Admin` |

---

### B. WhatsApp Ingress & Provider Integration (Task 5)
| Method | Endpoint | Description | Role Required |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/whatsapp/connections` | List configured WhatsApp connections with masked secrets | `Owner`, `Admin` |
| `POST` | `/api/v1/whatsapp/connections` | Register a new Meta Cloud or YCloud provider connection | `Owner`, `Admin` |
| `GET` | `/api/v1/whatsapp/connections/{id}` | Retrieve connection details with masked secrets | `Owner`, `Admin` |
| `PUT` | `/api/v1/whatsapp/connections/{id}` | Update connection parameters or replace encrypted secrets | `Owner`, `Admin` |
| `POST` | `/api/v1/whatsapp/connections/{id}/test` | Perform live provider handshake and connection validation | `Owner`, `Admin` |
| `POST` | `/api/v1/whatsapp/connections/{id}/send-test` | Dispatch a live outbound test message to a recipient | `Owner`, `Admin` |
| `GET` | `/api/v1/webhooks/whatsapp/meta` | Meta Webhook subscription verification (`hub.challenge`) | Public |
| `POST` | `/api/v1/webhooks/whatsapp/meta` | Meta Cloud API inbound message and status receiver (`X-Hub-Signature-256`) | Public (HMAC verified) |
| `POST` | `/api/v1/webhooks/whatsapp/ycloud` | YCloud inbound message and status update receiver (`YCloud-Signature`) | Public (HMAC verified) |

---

### C. Live WhatsApp Inbox & Conversations
| Method | Endpoint | Description | Role Required |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/conversations` | List conversation threads with pagination, status, and search filters | `Operator`+ |
| `GET` | `/api/v1/conversations/{id}`| Retrieve single conversation metadata and linked patient profile | `Operator`+ |
| `GET` | `/api/v1/conversations/{id}/messages`| Fetch paginated message history of a conversation | `Operator`+ |
| `POST` | `/api/v1/conversations/{id}/messages`| Send human operator reply via WhatsApp | `Operator`+ |
| `POST` | `/api/v1/conversations/{id}/takeover`| Toggle human takeover mode (`is_human_takeover: true/false`) | `Operator`+ |
| `POST` | `/api/v1/conversations/{id}/assign`| Assign conversation to specific staff operator | `Manager`+ |
| `POST` | `/api/v1/conversations/{id}/resolve`| Mark conversation as resolved / closed | `Operator`+ |

---

### D. Patients & Consents
| Method | Endpoint | Description | Role Required |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/patients` | Paginated search of patients (filter by name, phone, complaint) | `Operator`+ |
| `POST` | `/api/v1/patients` | Register new patient manually | `Operator`+ |
| `GET` | `/api/v1/patients/{id}` | Retrieve comprehensive patient profile with clinical history | `Operator`+ |
| `PUT` | `/api/v1/patients/{id}` | Update patient details or medical notes | `Operator`+ |
| `GET` | `/api/v1/patients/{id}/consents`| List patient consent status | `Operator`+ |
| `PUT` | `/api/v1/patients/{id}/consents`| Update marketing or communication consent preferences | `Operator`+ |

---

### E. Appointments & Availability Engine (Task 6)
| Method | Endpoint | Description | Role Required |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/appointments/availability`| Query available time slots for a given date (`date=YYYY-MM-DD`, `duration_minutes=45`). Enforces hard Sunday closure. | `Viewer`+ (`appointments:read`) |
| `GET` | `/api/v1/appointments` | List appointments with pagination, date range, status, patient ID, and text search | `Viewer`+ (`appointments:read`) |
| `POST` | `/api/v1/appointments` | Create appointment (ACID locked; enforces Sunday restriction and working hours) | `Operator`+ (`appointments:create`) |
| `GET` | `/api/v1/appointments/{id}`| Fetch full appointment details including patient and chronological history timeline | `Viewer`+ (`appointments:read`) |
| `PATCH` | `/api/v1/appointments/{id}`| Update appointment metadata, notes, practitioner, or service type | `Operator`+ (`appointments:update`) |
| `POST` | `/api/v1/appointments/{id}/reschedule`| Reschedule appointment to a new slot (enforces Sunday restriction & overlap check) | `Operator`+ (`appointments:update`) |
| `POST` | `/api/v1/appointments/{id}/cancel`| Cancel appointment with cancellation reason and notes (record preserved) | `Operator`+ (`appointments:cancel`) |
| `POST` | `/api/v1/appointments/{id}/complete`| Mark confirmed/scheduled appointment as completed with optional clinical notes | `Operator`+ (`appointments:complete`) |
| `POST` | `/api/v1/appointments/{id}/no-show`| Mark appointment as no-show with optional operational notes | `Operator`+ (`appointments:no_show`) |

#### Appointment Specific Error Codes
| Code | HTTP Status | Description |
| :--- | :--- | :--- |
| `SUNDAY_RESTRICTION` | 422 Unprocessable Entity | Attempted booking or rescheduling on Sunday (clinic closed). |
| `OPERATING_HOURS_VIOLATION` | 422 Unprocessable Entity | Attempted appointment outside operating hours (09:00 - 20:00 IST). |
| `PAST_APPOINTMENT` | 422 Unprocessable Entity | Attempted booking or rescheduling in the past. |
| `APPOINTMENT_CONFLICT` | 409 Conflict | Requested time slot overlaps with an existing active booking. |
| `INVALID_STATUS_TRANSITION` | 400 Bad Request | Invalid lifecycle transition (e.g. rescheduling cancelled/completed appointment). |
| `NOT_FOUND` | 404 Not Found | Specified appointment or patient does not exist. |

---

### F. AI Agents, LLM Providers & Tools (Task 7 Implementation)
| Method | Endpoint | Description | Role Required |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/llm/providers` | List all configured LLM providers with masked credentials | `Owner`, `Admin`, `Operator`, `Viewer` |
| `POST` | `/api/v1/llm/providers` | Create a new LLM provider configuration | `Owner`, `Admin` |
| `PUT` | `/api/v1/llm/providers/{id}` | Update provider base URL, enabled state, timeout, and API key | `Owner`, `Admin` |
| `POST` | `/api/v1/llm/providers/{id}/test` | Perform diagnostic connection handshake test | `Owner`, `Admin` |
| `GET` | `/api/v1/llm/models` | List all active models across providers with token costs | `Owner`, `Admin`, `Operator`, `Viewer` |
| `GET` | `/api/v1/agents` | List configured AI agents (including Deepti receptionist) | `Owner`, `Admin`, `Operator`, `Viewer` |
| `POST` | `/api/v1/agents` | Create a new AI agent with baseline version snapshot | `Owner`, `Admin` |
| `GET` | `/api/v1/agents/{id}` | Get agent details, models, tools, and system prompt | `Owner`, `Admin`, `Operator`, `Viewer` |
| `PUT` | `/api/v1/agents/{id}` | Update agent configuration and save immutable version snapshot | `Owner`, `Admin` |
| `GET` | `/api/v1/agents/{id}/versions` | List immutable version history snapshots for an agent | `Owner`, `Admin`, `Operator`, `Viewer` |
| `GET` | `/api/v1/agents/{id}/executions` | List chronological execution sessions and step details | `Owner`, `Admin`, `Operator`, `Viewer` |
| `POST` | `/api/v1/agents/{id}/test` | Execute isolated agent test console prompt (safe dry run) | `Owner`, `Admin` |
| `GET` | `/api/v1/tools` | List registered tools, Pydantic schemas, and mutation flags | `Owner`, `Admin`, `Operator`, `Viewer` |

---

### G. Knowledge Base & Vector Ingestion
| Method | Endpoint | Description | Role Required |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/knowledge-bases` | List knowledge bases | `Manager`+ |
| `POST` | `/api/v1/knowledge-bases` | Create a new knowledge base collection | `Admin`+ |
| `POST` | `/api/v1/knowledge-bases/{id}/upload`| Upload document (PDF/DOCX) for chunking and embedding | `Admin`+ |
| `GET` | `/api/v1/knowledge-bases/{id}/documents`| List ingested documents and chunk counts | `Manager`+ |
| `DELETE`| `/api/v1/knowledge-bases/documents/{id}`| Remove document and delete its vector chunks | `Admin`+ |
| `POST` | `/api/v1/knowledge-bases/test-query`| Test semantic retrieval score against vector index | `Admin`+ |

---

### H. 3-Touch Follow-ups & Automations
| Method | Endpoint | Description | Role Required |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/followups` | List queued and completed follow-up jobs with status | `Manager`+ |
| `POST` | `/api/v1/followups/{id}/cancel`| Manually suppress or cancel a scheduled follow-up touch | `Operator`+ |
| `GET` | `/api/v1/automations` | List active automation rules | `Admin`+ |
| `PUT` | `/api/v1/automations/{id}` | Update trigger intervals or conditions | `Admin`+ |

---

### I. Instagram Re-engagement Campaigns
| Method | Endpoint | Description | Role Required |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/campaigns` | List all broadcast campaigns and conversion metrics | `Manager`+ |
| `POST` | `/api/v1/campaigns` | Create new campaign (Reel URL, thumbnail, audience criteria) | `Manager`+ |
| `GET` | `/api/v1/campaigns/{id}` | Campaign details, audience size, delivery breakdown | `Manager`+ |
| `POST` | `/api/v1/campaigns/{id}/launch`| Launch or schedule campaign dispatch | `Manager`+ |
| `POST` | `/api/v1/campaigns/{id}/pause` | Pause active campaign | `Manager`+ |
| `GET` | `/api/v1/campaigns/{id}/deliveries`| Paginated delivery records and recipient response states | `Manager`+ |

---

### J. Analytics & Execution Logs
| Method | Endpoint | Description | Role Required |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/analytics/overview` | KPI summaries (messages, bookings, conversion rates, response latency) | `Manager`+ |
| `GET` | `/api/v1/analytics/conversions`| Appointment booking funnel analysis | `Manager`+ |
| `GET` | `/api/v1/logs/executions` | Searchable execution logs of tool runs and webhook events | `Admin`+ |
| `GET` | `/api/v1/logs/audit` | Filterable administrative audit trail | `Admin`+ |

---

### K. System Settings & Update Manager
| Method | Endpoint | Description | Role Required |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/settings` | Retrieve clinic profile, hours, and operational configs | `Admin`+ |
| `PUT` | `/api/v1/settings` | Save clinic settings and operational rules | `Admin`+ |
| `GET` | `/api/v1/updates/status` | Check installed version, latest version, and release notes | `Admin`+ |
| `POST` | `/api/v1/updates/check` | Probe remote registry for newer release tags | `Admin`+ |
| `POST` | `/api/v1/updates/backup` | Trigger manual pre-update database snapshot | `Super Admin` |
| `POST` | `/api/v1/updates/apply` | Execute automated upgrade pipeline | `Super Admin` |

---

### L. Knowledge Base & Semantic Retrieval (RAG)
| Method | Endpoint | Description | Role Required |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/knowledge/bases` | List all knowledge base collections with document counts | `Viewer`+ |
| `POST` | `/api/v1/knowledge/bases` | Create new knowledge base collection | `Admin`+ |
| `GET` | `/api/v1/knowledge/bases/{id}` | Retrieve knowledge base details | `Viewer`+ |
| `PATCH` | `/api/v1/knowledge/bases/{id}` | Update knowledge base details | `Admin`+ |
| `DELETE` | `/api/v1/knowledge/bases/{id}` | Delete knowledge base and documents | `Admin`+ |
| `GET` | `/api/v1/knowledge/bases/{id}/documents` | List documents in knowledge base | `Viewer`+ |
| `POST` | `/api/v1/knowledge/documents/upload` | Upload and ingest document (PDF, DOCX, TXT, MD) | `Admin`+ |
| `GET` | `/api/v1/knowledge/documents/{id}` | Retrieve document details and chunk counts | `Viewer`+ |
| `POST` | `/api/v1/knowledge/documents/{id}/reprocess` | Re-extract, normalize, chunk, and embed document | `Admin`+ |
| `POST` | `/api/v1/knowledge/documents/{id}/archive` | Archive document (exclude chunks from semantic search) | `Admin`+ |
| `DELETE` | `/api/v1/knowledge/documents/{id}` | Delete document, vector chunks, and physical file | `Admin`+ |
| `POST` | `/api/v1/knowledge/search` | Search knowledge chunks with cosine similarity | `Operator`+ |
| `POST` | `/api/v1/knowledge/test-retrieval` | Test retrieval console with latency tracking | `Operator`+ |
| `GET` | `/api/v1/knowledge/contacts/{id}/memories` | List persistent memories for a contact | `Operator`+ |
| `POST` | `/api/v1/knowledge/contacts/{id}/memories` | Store durable contact memory | `Operator`+ |
| `DELETE` | `/api/v1/knowledge/contacts/{id}/memories/{mem_id}` | Delete contact memory | `Admin`+ |

