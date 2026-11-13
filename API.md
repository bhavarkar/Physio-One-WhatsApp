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
| `POST` | `/api/v1/auth/login` | Authenticate user and issue JWT token in HTTP-only cookie | Public |
| `POST` | `/api/v1/auth/logout` | Revoke session and clear cookies | Authenticated |
| `POST` | `/api/v1/auth/refresh` | Rotate access token using refresh token | Authenticated |
| `GET` | `/api/v1/auth/me` | Return profile and permissions of current user | Authenticated |
| `GET` | `/api/v1/users` | List all staff users | `Admin`, `Super Admin` |
| `POST` | `/api/v1/users` | Create a new staff user | `Admin`, `Super Admin` |
| `PUT` | `/api/v1/users/{id}` | Update staff user details or status | `Admin`, `Super Admin` |
| `DELETE` | `/api/v1/users/{id}` | Deactivate staff user | `Super Admin` |
| `GET` | `/api/v1/roles` | List available system roles and permissions | `Admin`, `Super Admin` |

---

### B. WhatsApp Ingress & Messaging Adapters
| Method | Endpoint | Description | Role Required |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/whatsapp/webhook` | Meta Webhook challenge verification (`hub.challenge`) | Public |
| `POST` | `/api/v1/whatsapp/webhook` | Inbound message and delivery status webhook receiver | Public (HMAC verified) |
| `GET` | `/api/v1/whatsapp/templates`| List approved WhatsApp message templates from Meta | `Operator`+ |
| `POST` | `/api/v1/whatsapp/templates/sync`| Trigger sync of Meta Cloud API templates | `Manager`+ |
| `POST` | `/api/v1/whatsapp/send-template`| Send an outbound template message to a contact | `Operator`+ |

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

### E. Appointments & Availability Engine
| Method | Endpoint | Description | Role Required |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/appointments/availability`| Query available time slots for a given date range. Enforces Sunday closure. | `Operator`+ / Tool |
| `GET` | `/api/v1/appointments` | List appointments with filters (date range, status, practitioner) | `Operator`+ |
| `POST` | `/api/v1/appointments` | Book appointment (ACID locked; rejects Sunday bookings) | `Operator`+ / Tool |
| `GET` | `/api/v1/appointments/{id}`| Fetch appointment details | `Operator`+ |
| `PUT` | `/api/v1/appointments/{id}/reschedule`| Reschedule appointment to a new slot (rejects Sunday) | `Operator`+ / Tool |
| `POST` | `/api/v1/appointments/{id}/cancel`| Cancel appointment with reason code | `Operator`+ / Tool |

---

### F. AI Agents, LLM Providers & Tools
| Method | Endpoint | Description | Role Required |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/agents` | List configured AI agents (Deepti, Follow-up, Campaign) | `Admin`+ |
| `GET` | `/api/v1/agents/{id}` | Get agent detail, system prompt, model configurations | `Admin`+ |
| `PUT` | `/api/v1/agents/{id}` | Update agent prompt, temperature, model assignment | `Admin`+ |
| `GET` | `/api/v1/agents/{id}/versions`| View version history of an agent's prompt | `Admin`+ |
| `GET` | `/api/v1/providers` | List configured LLM providers (Muse, OpenAI, Anthropic) | `Super Admin` |
| `PUT` | `/api/v1/providers/{id}` | Update provider API keys, base URLs, and active status | `Super Admin` |
| `GET` | `/api/v1/tools` | List registered AI tools and execution schemas | `Admin`+ |
| `PUT` | `/api/v1/tools/{id}` | Toggle tool availability or update execution parameters | `Admin`+ |

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
