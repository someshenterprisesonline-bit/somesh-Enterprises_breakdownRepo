// Optional page: Walkthrough (also the '?' guide for staff).
"use strict";
// ---------------------------------------------------------- walkthrough
function viewGuide() {
  const st = S.meta.stages, start = S.meta.stages.find(s => s.code === S.meta.start_stage) || st[0];
  const steps = [
    ["Open the app", "On the main office PC, double-click <b>START SOMESH ENTERPRISES.bat</b>. Everyone else opens the address shown in its window (for example <span class='kbd'>http://192.168.1.25:8080</span>). Pick your name (admins also type their PIN) and click once anywhere so the browser can play the beep.", "Everyone"],
    ["Open a bill", `An admin goes to <b>New bill</b>, types the client name and presses <b>Open bill</b>. ${esc(start ? start.owners.join(", ") : "The first team")} get a double beep and a <b>New task</b> alert for ${esc(start ? start.code + " " + start.name : "the start stage")}.`, "Admin"],
    ["Start the task", "In <b>My tasks → New for you</b>, press <b>Start this task</b>. It moves to <b>Working on</b> and disappears from your teammates' lists, so two people never do the same work.", "Person doing the stage"],
    ["Do the work and save it", "Do the work as usual. Save the output file in your department's shared-drive folder (for example <span class='kbd'>G:\\Shared drives\\00 Handoff\\To_next</span>). The card shows what to deliver and what the previous team handed you.", "Person doing the stage"],
    ["Timer and lunch", "Pressing <b>Start</b> starts a timer on the task; it stops when you press <b>Done</b> (or Submit). The lunch break (1:00–2:00 PM by default) is never counted, and the app is locked for staff during it. Admins see everyone's time on the <b>Tracker</b> page and export it each day.", "Everyone"],
    ["Tasks from the admin", "Start → work → <b>Done – send for approval</b>. Once the admin approves, the documents box appears: upload the documents and press <b>End task</b>. Only then can you start your next task.", "Person doing the task"],
    ["Attach your files", "On the task card press <b>＋ Attach files</b> and pick any files your department works with: Excel, CSV, PDF, scans. The card shows which types the stage expects. The checker and the next team can open or preview them.", "Person doing the stage"],
    ["Submit for checking", "Press <b>Submit for checking</b>. Write what you delivered; attached files go with it, or paste the file path or Drive link. If the stage asks a question (for example <i>New candidates?</i>), answer it. The checker gets a <b>Please check</b> alert.", "Person doing the stage"],
    ["Check: approve or send back", "The checker opens <b>To check</b>, opens the file from the path, then presses <b>Approve &amp; hand over</b>, or <b>Send back</b> with what to fix. Sent-back work returns to the same person with the reason in red.", "Checker"],
    ["Hand-off to the next team", "On approval the next stage is created and its team gets the double beep. A stage that waits for several inputs (for example S06 waits for S03 and S04) starts only when all of them are approved.", "Automatic"],
    ["Overdue alerts", "If a task passes its time limit, the person doing it and the checker get a red <b>Overdue</b> alert. Late cards show a red edge and an 'Overdue by' label.", "Automatic"],
    ["Follow every bill", "<b>Pipeline</b> shows every bill against every stage. <b>Activity</b> lists each action with the time. <b>Alerts</b> keeps your last 40 alerts.", "Leads and CEO"],
    ["Bill complete", "When the final stage is approved, the bill is marked <b>Complete</b> and the admins get an alert.", "Automatic"],
  ];
  const adminSteps = [
    ["Get the input template", "<b>Workflow input → Download template</b>. It already contains today's stages and people."],
    ["Edit it in Excel or Google Sheets", "Stages: who does it, who checks it, time limit, next stages, what it waits for, a Yes/No question, and who else is alerted. People: names, departments, emails, admins. Bills to open: clients to open a bill for."],
    ["Load it", "Paste a Google Sheet link (shared as <i>Anyone with the link: Viewer</i>) or a file path such as <span class='kbd'>G:\\Shared drives\\Data Center\\Workflow_Input.xlsx</span>, or upload the file. Press <b>Check</b>, read the summary, then <b>Apply</b>. Optional: re-read the sheet every few minutes."],
  ];
  const table = `<div class="panel scroll"><table><thead><tr><th style="text-align:left">Stage</th><th style="text-align:left">Done by</th><th style="text-align:left">Checked by</th><th>Time limit</th><th style="text-align:left">Then</th></tr></thead><tbody>${st.map(s => `<tr><td style="text-align:left"><b>${esc(s.code)}</b> ${esc(s.name)}<div class="muted small">${esc(s.dept)}</div></td><td style="text-align:left">${esc(s.owners.join(", "))}</td><td style="text-align:left">${esc(s.validator)}</td><td>${esc(s.sla_hours)} h</td><td style="text-align:left">${esc([...(s.next || []), ...Object.entries((s.branch || {}).options || {}).filter(([, v]) => v.length).map(([k, v]) => k + " → " + v.join(", "))].join(", ") || "Done")}${(s.requires || []).length ? `<div class="muted small">waits for ${esc(s.requires.join(", "))}</div>` : ""}</td></tr>`).join("")}</tbody></table></div>`;
  return hero("Walkthrough", "How to run the Monthly Cycle by hand, one step at a time.") +
    `<div class="steps">${steps.map(([h, p, w]) => `<div class="step"><h3>${h}</h3><p>${p}</p><span class="who">${w}</span></div>`).join("")}</div>
     <h2>Who does what (current workflow)</h2>${table}
     <h2>Changing the process (admins)</h2><div class="steps">${adminSteps.map(([h, p]) => `<div class="step"><h3>${h}</h3><p>${p}</p></div>`).join("")}</div>
     <h2>Alerts at a glance</h2><div class="panel"><dl class="facts" style="font-size:14px;gap:8px 18px">
       <dt>New task</dt><dd>Everyone in <i>Done by</i>, plus anyone in <i>Also alert</i></dd><dt>Please check</dt><dd>The checker</dd>
       <dt>Approved / Sent back</dt><dd>The person who did the work</dd><dt>Overdue</dt><dd>The person doing it, the checker and <i>Also alert</i></dd><dt>Bill complete</dt><dd>Admins</dd>
       <dt>Sound</dt><dd>A short double beep for every alert. Turn it off with the speaker button at the top.</dd></dl></div>`;
}
