# Showing SOMESH ENTERPRISES alerts inside your Gather office (Gather 2.0)

Your office is on **Gather 2.0** (the menu has *Edit the office* and *Decorate desk*). In Gather 2.0 you don't
upload anything. Instead you place **Smart Objects** (an *Inbox* tray or a *Signal* light) at each team's desks.
This app then updates them live:

| Object | What people see in Gather |
|---|---|
| **Inbox** for a department | A count badge = that team's open tasks. Click it to see the list: `NEW · S03 Prepare worksheet · BILL-2611-004 · Rupashri`, `TO CHECK · …`, `⚠ LATE · …` |
| **Inbox** for one person | Only that person's own tasks: new for them, being done by them, or waiting for their check |
| **Signal light** for a department | off = nothing open · on = work open · **alert** = something is overdue |

When a team approves its work, its entry disappears from its inbox and appears in the **next team's** inbox, so
you can watch a bill travel across the office. The popup and sound still come from the app in each person's browser.

Nothing has to be uploaded to Gather, and you don't need an https address for the app. The app sends the updates
**out** to Gather, so the PC running it only needs normal internet access.

---

## Step 1 - Name the team areas (5 min, optional but nice)
Gather logo menu → **Edit the office** (Gather Studio). Click each team area and rename it to a department:
*Operations · Data Center · Finance, Contracts & Vault · Payroll · Legal & Compliance · Executive Office*. **Publish**.

## Step 2 - Place the Smart Objects (10 min)
For each department (sit at a desk in that team's area):
1. Gather logo menu → **Decorate desk** → choose an **Inbox** Smart Object → place it on the desk → name it,
   for example `Operations inbox`.
2. Optional: also place a **Signal** light (for example by the Operations area) and name it `Operations alarm light`.
3. Open the object's **⋮ menu** → copy the **Webhook URL** and the **secret** (starts with `whsec_`).

Only Members and Admins can add Smart Objects. Guests can't.

## Step 3 - Paste them into the app (5 min)
Open `config.json` in Notepad. In the `"gather"` section:
- set `"enabled": true`
- for each object, paste its **url** and **secret** over `PASTE-WEBHOOK-URL` / `whsec_PASTE`
- keep `"dept"` matching the department exactly, or use `"person": "Ramya"` for a personal desk inbox
- delete the example entries you don't use

Example:
```json
{"name": "Operations inbox", "kind": "inbox", "dept": "Operations",
 "url": "https://…gather…/webhook/…", "secret": "whsec_…"}
```
Kinds: `inbox`, `signal` (off / on / alert), `status`, `switch` (on when something is overdue).

## Step 4 - Test and start (2 min)
In the app folder, open a command prompt and run:
```
py -3 app.py --gather-test
```
Each object should print **OK**. Then start the app as usual (`START SOMESH ENTERPRISES.bat`). Within a few seconds the inboxes in
Gather fill with the open tasks and the count badges appear.

## Step 5 - The demo
1. Open Gather and stand where everyone can see the Operations, Data Center and Finance desks.
2. On another screen, open the app (`http://localhost:8080`) as **Somesh** → **New bill & demo** → open a bill.
   The **Operations inbox** count goes up, and Ramya's browser double-beeps.
3. Press **Auto-play**. The task moves from the Operations inbox to Data Center, then Finance and Payroll, and so on.
   Click an inbox to show the list. Let one task run late (demo mode makes 1 hour = 1 minute) and the
   **Operations alarm light** turns to alert.

## Good to know
- **Visibility:** everyone in the office, guests included, can open an object's feed. The feed shows stage, bill number and
  name only (no amounts). Don't put sensitive details in bill or client names.
- **Limits:** Gather rate-limits Smart Objects per space. The app sends only changes, at most once a second, plus a refresh
  every minute.
- **Gather Classic (1.0):** if you ever use Classic instead, `Monthly_Cycle_Gather_Background.png` is a ready-made map
  for its Mapmaker, and the older guide in the Gather pack still applies.
