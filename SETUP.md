# Setting up Lead Desk on a new laptop

This guide takes you from a fresh Windows or Mac laptop to a working Lead Desk dashboard
at `http://127.0.0.1:8765`, with the Claude Code CLI set up to run the `/find-leads` workflow.

- [What you need](#what-you-need)
- [Part 1 — Copy the project to the laptop](#part-1--copy-the-project-to-the-laptop-both)
- [Part 2 — Install and start Lead Desk](#part-2--install-and-start-lead-desk)
  - [Windows](#windows)
  - [macOS](#macos)
- [Part 3 — Set up the Claude Code CLI](#part-3--set-up-the-claude-code-cli-both)
- [Part 4 — Check that everything works](#part-4--check-that-everything-works-both)
- [Troubleshooting](#troubleshooting)

---

## What you need

| Item | Required? | Why |
|------|-----------|-----|
| **Python 3.10 or newer** | Required | Runs the dashboard and every script. The project uses only Python's standard library, so there is no `requirements.txt`. |
| **certifi** (a small Python package) | Strongly recommended | Lets the Apify and website-scraping scripts check HTTPS certificates. Without it they still run, but with certificate checks switched off. |
| **curl** | Required for sending email | Emails go to Mailtrap through `curl`. It is already built into Windows 10/11 and macOS. |
| **`.env` file with API keys** | Required | `APIFY_API_KEY` for lead search, `MAILTRAP_API_KEY` and `MAIL_FROM_ADDRESS` for sending. |
| **Claude Code CLI** | Required for `/find-leads` | Researches each company and writes the outreach emails. Needed both for typing `/find-leads` and for the dashboard's **Run the full workflow** button. See [Part 3](#part-3--set-up-the-claude-code-cli-both). |
| **Claude account** | Required for `/find-leads` | A paid Claude plan (Pro, Max, Team or Enterprise) or a Claude Console account. The free Claude.ai plan doesn't include Claude Code. |
| **Git for Windows** | Recommended, Windows only | Gives Claude Code a Bash shell, which is what the `/find-leads` steps are written for. |

Before you start, have your API keys to hand. The easiest source is the `.env` file on the
Mac that already runs this project. Otherwise:

- **Apify:** Apify Console → Settings → API & Integrations → copy your API token.
- **Mailtrap:** Mailtrap → Settings → API Tokens. `MAIL_FROM_ADDRESS` must be on a domain
  you have verified in Mailtrap (currently `info@krediview.com`).

---

## Part 1 — Copy the project to the laptop (both)

The project isn't on GitHub or any other remote, so copy the folder across.

1. **On the Mac that already has the project**, open Terminal and run:

   ```bash
   cd ~/Development
   zip -r lead-desk.zip "Lead Scraper Apify" -x "*/__pycache__/*" "*.DS_Store"
   ```

   This creates `~/Development/lead-desk.zip`. It includes the hidden `.env` file, the hidden
   `.claude/` folder (where `/find-leads` is defined) and the `leads/` folder.

2. Move `lead-desk.zip` to the new laptop by USB drive, AirDrop, Google Drive or OneDrive.

   > **Keep this zip private.** `.env` holds live Apify and Mailtrap keys. Don't post the zip
   > or push the folder to a public GitHub repo.

3. Unzip it to a folder you'll remember:
   - **Windows:** right-click → **Extract All** → `C:\Users\<your-name>\Development\`
   - **Mac:** double-click the zip, then move the folder to `~/Development/`

4. Open the folder and check that these are all there:
   - `.env`
   - `.claude/commands/find-leads.md`
   - `leads/`, `scripts/` and `ui/`

   Both `.env` and `.claude` are hidden. To see them:
   - **Windows Explorer:** turn on **View → Show → Hidden items** and **File name extensions**.
   - **Mac Finder:** press **Cmd + Shift + .** to show hidden files.

> **About your lead data:** the CSV files in `leads/` *are* the database. If you use both
> laptops, each copy changes independently and the two will drift apart. Choose one laptop
> as your main copy, or copy the `leads/` folder across each time you switch.

---

## Part 2 — Install and start Lead Desk

Follow the section for your operating system, then go on to Part 3.

### Windows

Use **PowerShell** for every command below. To open it, click Start, type `PowerShell` and
press Enter. You don't need to run it as Administrator.

#### W1. Install Python

1. Open the **Microsoft Store**, search for **Python Install Manager** and click **Install**.
   (You can also download it from [python.org/downloads](https://www.python.org/downloads/).)
2. **Close PowerShell and open a new window**, then run:

   ```powershell
   python --version
   ```

   The first time you run this, it may offer to download the latest Python and to add a
   folder to your PATH. Answer **yes** to both. It should end by printing something like
   `Python 3.14.x`.

   > If you already have Python 3.10 or newer from the older python.org installer, you can
   > keep it. Just make sure `python --version` works.

#### W2. Turn on UTF-8 mode (don't skip this)

```powershell
setx PYTHONUTF8 1
```

**Close every PowerShell window, and VS Code if it's open, then reopen them.** Check it worked:

```powershell
python -c "import sys; print(sys.flags.utf8_mode)"
```

It should print `1`.

**Why:** Windows doesn't use UTF-8 by default. Company names, the ₦ sign and Claude's progress
output include characters that encoding can't handle. Without this setting, **Enrich**
silently reports "nothing new found", and `/find-leads` runs started from the dashboard can
crash near the end.

#### W3. Install certifi

```powershell
python -m pip install certifi
```

#### W4. Check curl

```powershell
curl.exe --version
```

Type `curl.exe`, not `curl`. In older PowerShell, plain `curl` is a different command. If you
get a version number, you're done. If not, your Windows 10 is too old, so run Windows Update.

#### W5. Check the `.env` file

If you copied the folder in Part 1, `.env` is already in place. Skip to W6.

To create it by hand, open the project folder in **VS Code**, create a new file called `.env`
in the top-level folder and paste:

```
APIFY_API_KEY=your-apify-token
MAILTRAP_API_KEY=your-mailtrap-token
MAIL_FROM_ADDRESS=info@krediview.com
```

> Don't use Notepad for this. It often saves the file as `.env.txt`, and the dashboard won't
> find it.

#### W6. Start Lead Desk

`start-ui.sh` only works on macOS and Linux. On Windows, start the server directly:

```powershell
cd "$HOME\Development\Lead Scraper Apify"
python ui\server.py
```

Your browser opens at `http://127.0.0.1:8765`. Leave the PowerShell window open while you
use the dashboard. Press **Ctrl + C** in it to stop the server.

Options: `python ui\server.py --port 9000` uses a different port, and `--no-browser` stops
it opening a browser.

**Optional: a double-click launcher.** Create a file called `start-ui.bat` in the project
folder containing:

```bat
@echo off
cd /d "%~dp0"
set PYTHONUTF8=1
python ui\server.py %*
pause
```

Double-click it any time to start Lead Desk.

Now go to [Part 3](#part-3--set-up-the-claude-code-cli-both).

### macOS

Use **Terminal** for every command below (Cmd + Space, type `Terminal`, press Enter).

#### M1. Install Python

1. Download the latest **macOS installer** from [python.org/downloads](https://www.python.org/downloads/)
   and run the `.pkg`.
2. When it finishes, a Finder window opens at **Applications → Python 3.x**. Double-click
   **Install Certificates.command**.
3. **Open a new Terminal window** and check:

   ```bash
   python3 --version
   ```

   You should see `Python 3.14.x` or similar.

> **Why python.org and not Homebrew?** Homebrew's Python blocks `pip install` outside a
> virtual environment, which makes the next step fiddly. If you already use Homebrew Python
> for other work, the python.org installer can sit alongside it.

#### M2. Install certifi

```bash
python3 -m pip install certifi
```

(Install Certificates.command has usually done this already. Running it again does no harm.)

#### M3. Check curl

```bash
curl --version
```

macOS includes curl, so this should just print a version.

#### M4. Check the `.env` file

If you copied the folder in Part 1, `.env` is already there. Skip to M5.

To create it by hand, open the project folder in VS Code, create a file called `.env` in the
top-level folder and paste:

```
APIFY_API_KEY=your-apify-token
MAILTRAP_API_KEY=your-mailtrap-token
MAIL_FROM_ADDRESS=info@krediview.com
```

#### M5. Start Lead Desk

```bash
cd ~/Development/"Lead Scraper Apify"
./start-ui.sh
```

Your browser opens at `http://127.0.0.1:8765`. Leave Terminal open while you use it, and press
**Ctrl + C** to stop.

- If you get `permission denied`, run `chmod +x start-ui.sh` once, then try again.
- Options: `./start-ui.sh --port 9000` or `./start-ui.sh --no-browser`.
- `python3 ui/server.py` does the same thing as `./start-ui.sh`.

---

## Part 3 — Set up the Claude Code CLI (both)

The `/find-leads` workflow runs inside **Claude Code**, Anthropic's command-line tool. You
can start it in two ways, and both need the CLI installed and logged in on this laptop:

| Where you start it | What happens |
|--------------------|--------------|
| **In a terminal:** type `/find-leads` in Claude Code | Claude asks for the location and lead count. It asks your permission before it runs scripts or edits files, and shows each step as it works. |
| **In Lead Desk:** Discover → **Run the full workflow** | The dashboard runs Claude Code in the background (`claude -p`) with permission to use Bash, Read, Write and Edit. Progress streams to the Activity tab. |

Claude Code finds `/find-leads` in `.claude/commands/find-leads.md`, so always start
Claude Code **from the project folder**.

### C1. Check your Claude account

You need one of these:

- a **Claude Pro, Max, Team or Enterprise** plan (claude.ai), or
- a **Claude Console** account (pay-as-you-go API billing).

The free Claude.ai plan doesn't include Claude Code. Each `/find-leads` run uses your
plan's usage allowance, or Console credits, and takes about 15–40 minutes.

### C2. Windows only: install Git for Windows

Download it from [git-scm.com/downloads/win](https://git-scm.com/downloads/win) and install with
the default options. Claude Code then uses Git Bash for shell commands, which is what the
`/find-leads` steps are written for. Without Git for Windows, Claude Code falls back to
PowerShell.

### C3. Install the Claude Code CLI

**Windows (PowerShell):**

```powershell
irm https://claude.ai/install.ps1 | iex
```

**macOS (Terminal):**

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

> **Windows: use this installer, or `winget install Anthropic.ClaudeCode`, not npm.** The
> dashboard starts `claude` directly and needs the real `claude.exe`. An npm install can leave
> only a `claude.cmd` shortcut, which the dashboard can't start.

> **The VS Code extension alone is not enough.** The Claude Code extension for VS Code comes
> with its own built-in copy of Claude Code, which the dashboard can't use. Install the CLI
> above even if you also use the extension.

### C4. Check that it installed

**Close the terminal and open a new one**, then run:

```
claude --version
```

You should see a version number such as `2.1.x (Claude Code)`. For a fuller health check, run:

```
claude doctor
```

If you get `claude is not recognized` (Windows) or `command not found` (Mac):

- **Windows:** make sure `%USERPROFILE%\.local\bin` is on your PATH. Click Start, search
  **Edit environment variables for your account**, edit **Path** and add
  `C:\Users\<your-name>\.local\bin`. Then open a new PowerShell window.
- **Mac:** the installer printed a line that adds `~/.local/bin` to your PATH. Run that line,
  then open a new Terminal window.

### C5. Log in and trust the project folder

Start Claude Code from the project folder:

**Windows:**

```powershell
cd "$HOME\Development\Lead Scraper Apify"
claude
```

**Mac:**

```bash
cd ~/Development/"Lead Scraper Apify"
claude
```

1. A browser window opens. Sign in with your Claude or Console account. If the browser doesn't
   open, press **c** to copy the login link and paste it into your browser.
2. The terminal shows **Login successful**. Press **Enter**.
3. When Claude Code asks whether you trust the files in this folder, choose **Yes**.
4. Type `/status` to confirm which account you're logged in with.
5. Type `/exit` to leave, or carry straight on to C7.

To switch accounts later, type `/login`. To sign out, type `/logout`.

> **Check for a stray API key.** If an `ANTHROPIC_API_KEY` environment variable is set on this
> laptop, Claude Code uses that key instead of your subscription. Runs started from the
> dashboard always use it. Remove the variable unless you mean to pay through it.

### C6. Test the background mode the dashboard uses

From the project folder, run:

```
claude -p "Reply with the single word: ready"
```

It should print `ready`. If it prints a login error instead, repeat C5.

If Lead Desk is already running, stop it (**Ctrl + C**) and start it again **from a new
terminal window** so it can find `claude`.

### C7. Run `/find-leads`

**Option A: in the terminal**

1. From the project folder, run `claude`.
2. Type `/find-leads` and press Enter.
3. Answer the two questions: location (for example `Lagos, Nigeria`) and how many leads.
4. Claude asks before running each kind of command or editing a file. Approve each one, or
   choose the option that stops it asking again for that command in this project.

> **This sends real emails.** Typed in the terminal, `/find-leads` runs every step, including
> Step 6, which emails every lead marked "Ready to Send". To research and draft only, add an
> instruction after the command:
>
> ```
> /find-leads Stop after Step 5 and don't send any emails.
> ```
>
> Then read the drafts in Lead Desk and send from there.

**Option B: from Lead Desk**

1. Open the **Discover** tab. **Run the full workflow** should be enabled, with no red "The
   claude CLI was not found on PATH" note.
2. Enter the location and lead count.
3. Choose a scope:
   - **Research & draft only** (default): stops before sending. Leads end up as
     `Ready to Send` for you to review.
   - **Research, draft and send**: sends emails at the end, without asking again.
4. Watch progress on the **Activity** tab. When the run finishes, the last line shows how
   many turns it took and what it cost.

> **Windows limitation:** the **Stop run** button doesn't stop a run on Windows, because the
> server sends a stop signal that only works on Mac and Linux. To stop a run, end
> **claude.exe** in Task Manager, or close Lead Desk's PowerShell window.

**Option C: in VS Code (optional)**

1. In VS Code, open the Extensions view, search for **Claude Code** (publisher: Anthropic) and
   install it.
2. Choose **File → Open Folder** and open the project folder.
3. Click the Claude Code spark icon, sign in if asked, and type `/find-leads`.

### C8. Keep Claude Code up to date

Installs from the native installer update themselves in the background. To update right
away, run `claude update`. If you installed with WinGet, run
`winget upgrade Anthropic.ClaudeCode` from time to time.

---

## Part 4 — Check that everything works (both)

Run these checks with Lead Desk open in your browser.

1. **Keys found:** at the bottom of the sidebar, the **Apify key** and **Mailtrap key**
   dots are both **green**. A red dot means that key is missing from `.env`.
2. **Leads load:** the **Leads** tab shows your existing leads, and you can switch between
   the lead files (for example Lagos and Abuja).
3. **Scraper works:** in a *second* terminal window, in the project folder, run:

   ```
   python  scripts/scrape_website.py https://example.com     # Windows
   python3 scripts/scrape_website.py https://example.com     # Mac
   ```

   It should print a block of JSON rather than an error.
4. **Sending path works, without sending anything:** open any lead that has an email
   address and click **Dry run**. It reports what *would* be sent.
   Don't test with a real send, because these are real businesses.
5. **Claude Code logged in:** `claude -p "Reply with the single word: ready"` prints `ready`.
6. **Claude Code found by Lead Desk:** on the **Discover** tab, **Run the full workflow** is
   enabled and there's no red "The claude CLI was not found on PATH" note.

If all six pass, the laptop is ready.

---

## Troubleshooting

### Lead Desk

| Problem | Fix |
|---------|-----|
| `python` is not recognized, or it opens the Microsoft Store (Windows) | Open a *new* PowerShell window. If it still fails, click Start, open **Manage app execution aliases** and make sure the **Python** entries are on (switch them off and on again to refresh). |
| `python3: command not found` (Mac) | Open a new Terminal window after installing. If it still fails, reinstall from python.org. |
| Apify or Mailtrap dot is red | `.env` is missing, in the wrong folder (it must sit next to `start-ui.sh`), saved as `.env.txt`, or a key name is misspelled. Fix it, then reload the page. |
| The browser says it can't connect, or the terminal shows `Address already in use` / `WinError 10048` | Another program is using port 8765. Start with `--port 9000` and open `http://127.0.0.1:9000`. |
| **Enrich** says "nothing new found" for every lead (Windows) | UTF-8 mode is off. Redo step W2 and reopen your terminal. |
| `CERTIFICATE_VERIFY_FAILED` or other SSL errors | Mac: run **Install Certificates.command** from Applications → Python 3.x. Both: run the certifi install step again. |
| Sends fail with `curl not found — install curl to send emails` | Windows: run Windows Update; curl ships with Windows 10 (version 1803 and later) and Windows 11. |
| Sends fail with a Mailtrap domain or sender error | `MAIL_FROM_ADDRESS` must be on a domain verified in your Mailtrap account. |
| `./start-ui.sh: Permission denied` (Mac) | Run `chmod +x start-ui.sh`, or start with `python3 ui/server.py`. |

### Claude Code

| Problem | Fix |
|---------|-----|
| `claude` is not recognized / `command not found` | Open a new terminal. If it still fails, add the install folder to your PATH (see C4), then run `claude doctor`. |
| **Run the full workflow** is disabled with "The claude CLI was not found on PATH" | The CLI isn't installed, or Lead Desk was started from a terminal opened *before* you installed it. Check `claude --version` in a new terminal, then restart Lead Desk from that terminal. Windows: make sure you used the native installer, not npm. Installing only the VS Code extension doesn't count. |
| Claude says `/find-leads` is an unknown command | You started `claude` outside the project folder, or `.claude/commands/find-leads.md` didn't come across. `cd` into the project folder and start again. On Windows, check the hidden `.claude` folder is there. |
| A dashboard run fails straight away with `claude exited 1` | Claude Code usually isn't logged in. Run `claude -p "Reply with the single word: ready"` in a terminal; if you see a login error, run `claude` and log in (C5). |
| `Login expired · Please run /login` | Run `claude` in a terminal, type `/login` and sign in again. |
| Runs are billed to an API key instead of your Claude plan | An `ANTHROPIC_API_KEY` environment variable is set. Remove it, open a new terminal, and check `/status` inside Claude Code. |
| Claude Code can't find Git Bash (Windows) | Open (or create) `%USERPROFILE%\.claude\settings.json` and add the snippet below, pointing at your Git install. Then restart Claude Code. |
| A `/find-leads` run from the dashboard ends with an error (Windows) | Check that UTF-8 mode is on (W2), then confirm you're logged in with the `claude -p` test (C6). |
| **Stop run** does nothing (Windows) | Known limitation: end **claude.exe** in Task Manager, or close Lead Desk's PowerShell window. |

Git Bash setting for Windows (`%USERPROFILE%\.claude\settings.json`):

```json
{
  "env": {
    "CLAUDE_CODE_GIT_BASH_PATH": "C:\\Program Files\\Git\\bin\\bash.exe"
  }
}
```
