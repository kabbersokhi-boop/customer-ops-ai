# Interview demo script

## Before the interview

```bash
git switch presentation-reset-clean-demo
make demo-reset
make demo-ready
make orchestration-eval
```

Open the customer experience, manager dashboard, n8n workflow list, and Airtable Appointments view in separate tabs.

## Five-minute golden path

1. Start at `/customer`. Say: “This is a synthetic dealership, but the control and integration paths are real.”
2. Enter `Kabir` as the customer name.
3. Send: `My car needs its 40,000 km service. Can I come Saturday?`
4. Point out that Gurugram is full and every alternative shown came from `service_slots` in PostgreSQL.
5. Send: `Actually, Monday works.`
6. Choose `10:00`. Explain that conversation state carried the service request, branch, and changed date forward.
7. In the confirmation card enter `+91 99999 01099` and `kabir@example.com`.
8. Before clicking confirm, say: “No appointment exists yet. This is the consequential-action boundary.”
9. Click **Confirm service appointment**.
10. Show the confirmed response, then switch to `/` and refresh.
11. Show Kabir under current customer activity, the service appointment, meaningful KPIs, and no duplicate if the same command is replayed.
12. Open **Technical details**. Walk through Browser → n8n → FastAPI → PostgreSQL/NIM/Airtable → n8n → Browser, plus audit and CRM state.
13. Switch to Airtable Appointments and show the customer, service request, branch, scheduled time, status, and next action.

## Controlled failure and recovery

1. Start a new customer conversation and select the other Monday slot.
2. On `/`, open **Technical details** and click **Simulate scheduler timeout**.
3. Confirm the service appointment in the customer UI.
4. Point out the exact result: the booking is **not confirmed**, the customer details are preserved, and duplicate protection remains active.
5. Refresh `/`. Show **Booking confirmation required** under **Needs your attention**.
6. Click **Restore scheduler**.
7. Click **Retry booking** on the recovery item.
8. Show that one appointment is created, the recovery item resolves, and another retry returns the same appointment rather than duplicating it.

## Safety escalation

1. Start a new conversation and send: `My brakes are making a grinding noise.`
2. Point out that the system does not diagnose the issue or treat it as routine scheduling.
3. Show the bounded safety language and the priority service case.
4. Refresh the manager dashboard and show the safety case at the top of **Needs your attention**.

## Screenshot set

- customer response showing Saturday unavailable and grounded alternatives
- explicit service confirmation card before mutation
- confirmed booking message
- manager dashboard with attention-first KPIs and current activity
- Technical details drawer with n8n execution link, CRM sync, and audit events
- Airtable Appointments business fields after the booking
- failure response stating that the booking is not confirmed
- manager recovery item with the retry action
- n8n canvas for Customer Enquiry Intake and Service Booking & Confirmation
