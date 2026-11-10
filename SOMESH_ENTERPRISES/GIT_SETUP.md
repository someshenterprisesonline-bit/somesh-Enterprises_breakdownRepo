# Git setup: new repository, cloning, and working on it together

Commands are for **Windows** (Command Prompt or Git Bash). They're the same on Mac and Linux.
Replace `YOUR-GITHUB-NAME` with your GitHub username or organisation.

For an existing clone, keep its current remote and history. Start with `git status`, `git branch -vv`, and `git remote -v`; skip Part A. The app in this repository lives under `SOMESH_ENTERPRISES/`.

---

## Part A · Owner (Somesh): put this code in a new repository, once

**1. Install Git** from https://git-scm.com/download/win, keeping the default options. Then tell Git who you are, once per PC:
```
git config --global user.name "Somesh"
git config --global user.email "you@example.com"
```

**2. Create the empty repository on GitHub.** Go to https://github.com/new and fill it in:
- Repository name: `somesh-enterprises`
- **Private**. The repo contains staff names and the admin PIN setting.
- **Leave "Add a README", ".gitignore" and "license" unticked.** The repository must be empty.
- Click **Create repository**.

**3. Push the code.** Unzip `SOMESH_ENTERPRISES_v2_split_2026-11-05.zip`, open a terminal **inside** the `SOMESH_ENTERPRISES` folder (the one with the .bat file), then run:
```
git init
git add .
git commit -m "SOMESH ENTERPRISES v2: backend/frontend split"
git branch -M main
git remote add origin https://github.com/YOUR-GITHUB-NAME/somesh-enterprises.git
git push -u origin main
```
The first push opens a browser window to sign in to GitHub.
`data/` and `storage/` are left out automatically by `.gitignore`.

**4. Invite the new team member.** On GitHub, go to the repo → **Settings** → **Collaborators** → **Add people**, then enter their GitHub username. They accept the email invite.

**5. Recommended: protect `main`,** so nobody pushes to it directly and every change goes through a pull request. Go to Settings → **Branches** → Add branch protection rule → Branch name pattern `main` → tick **Require a pull request before merging** → Save.

> **Updating an existing repository?** Keep the working tree and history intact. Review `git status` and `git diff`, apply only intended changes, test them, and stage explicit source paths on a feature branch. Do not remove the old tree wholesale or commit local databases, credentials, or private profile changes.

---

## Part B · New team member: get the code and run it

```
git clone https://github.com/YOUR-GITHUB-NAME/somesh-enterprises.git
cd somesh-enterprises
```
Then open the application folder and double-click **`START SOMESH ENTERPRISES.bat`**. It checks Python, `openpyxl` and ReportLab, and opens http://localhost:8080.
For isolated automated test data, follow README.md. Admins use the existing deployment's configured PIN; do not publish or overwrite credentials.

Read **README.md**, then **CODE_MAP.md**, which shows which file draws which page.

A good editor is **VS Code** (https://code.visualstudio.com). Use File → Open Folder → the cloned folder.

---

## Part C · Daily routine for BOTH people (so you can push at the same time)

Each task gets its **own branch**. Nobody works on `main` directly.

```
git checkout main
git pull                                  # 1. get everyone's latest work
git checkout -b dashboard-export-pdf      # 2. new branch named after the task

   ... edit, refresh the browser, test ...

git status                                # 3. see what changed
git add frontend/js/pages/dashboard.js    #    add the files you meant to change
git commit -m "Dashboard: add PDF export"
git push -u origin dashboard-export-pdf   # 4. upload the branch
```

5. On GitHub, click **Compare & pull request** → write what changed → **Create pull request**.
6. The other person reviews it, opens it on their PC if needed, and clicks **Merge pull request**. Then both run:
```
git checkout main
git pull
```

**Rules that prevent clashes:**
- Give the two people tasks in **different rows of CODE_MAP.md**. Different files never conflict.
- Files marked ⚠ in CODE_MAP.md (`shell.js`, `live-and-load.js`, `app.css`, `index.html`, `app.py` routes) can be changed by both, but keep those edits small. Add new CSS at the end of `app.css` under a comment with your page name.
- **Pull often.** Run `git pull` on `main` before starting a branch. On a long task, bring in main's latest changes with `git merge main` while on your branch.
- **Never commit** `data/`, `storage/`, or test edits to `backend/config.json`, `users.json` or `workflow.json`. Undo a config edit with `git checkout -- backend/config.json`.
- Keep pull requests small, one task each. Small pull requests merge cleanly.

**If Git reports a conflict** while you run `git pull` or `git merge main`:
1. Open the files it lists. Git marks the clash like this:
   ```
   <<<<<<< HEAD
   your version
   =======
   their version
   >>>>>>> main
   ```
2. Keep the right lines (often both) and delete the three marker lines.
3. Run `git add <file>`, then `git commit`, then `git push`.
VS Code shows **Accept Current / Accept Incoming / Accept Both** buttons over each conflict, which is easier.

**Undo local mistakes:**

| Situation | Command |
|---|---|
| Throw away changes to one file | `git checkout -- path/to/file` |
| See what you changed | `git diff` |
| Forgot to make a branch and edited on main (not committed yet) | `git checkout -b my-task`. Your changes come with you. |

---

## Part D · Releasing to the office PC

On the PC that runs the app for everyone:
```
git pull
```
Then close the black window and double-click **`START SOMESH ENTERPRISES.bat`** again. The office data in `data/` and `storage/` is untouched by `git pull`, because those folders are not in git.

**Back up `data/` and `storage/` separately**, for example by copying them to the shared drive weekly. Git does not store them.
